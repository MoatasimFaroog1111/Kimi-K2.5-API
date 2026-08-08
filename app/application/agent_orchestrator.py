from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.audit_service import AgentAuditService
from app.application.change_validator import ChangeValidationService
from app.application.checkpoint_codec import AgentCheckpointCodec
from app.application.code_search_service import CodeSearchService
from app.application.context_manager import AgentContextManager
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.preapproval_validation_service import PreApprovalValidationService
from app.application.run_budget_service import RunBudgetService
from app.application.run_runtime_service import AgentRunRuntime
from app.application.security_service import AgentSecurityService
from app.application.semantic_search_service import SemanticCodeIntelligence
from app.application.workflow_service import RepositoryWorkflowCatalog, WorkflowSelectionService
from app.config import Settings
from app.core.exceptions import AgentValidationError
from app.domain.agent import ChangeProposal
from app.domain.agent_v4 import AgentRun, RunStage, RunStatus
from app.domain.ports import ProposalRepositoryPort, WorkspacePort


class AgentOrchestrator:
    def __init__(
        self,
        *,
        planner: PlannerAgent,
        coder: CoderAgent,
        reviewer: ReviewerAgent,
        tester: TesterAgent,
        workspace: WorkspacePort,
        proposals: ProposalRepositoryPort,
        validator: ChangeValidationService,
        security: AgentSecurityService,
        knowledge: ProjectKnowledgeService,
        audit: AgentAuditService,
        code_search: CodeSearchService,
        semantic: SemanticCodeIntelligence,
        preapproval: PreApprovalValidationService,
        workflows: RepositoryWorkflowCatalog,
        workflow_selection: WorkflowSelectionService,
        runtime: AgentRunRuntime,
        context: AgentContextManager,
        budget: RunBudgetService,
        config: Settings,
    ) -> None:
        self._planner = planner
        self._coder = coder
        self._reviewer = reviewer
        self._tester = tester
        self._workspace = workspace
        self._proposals = proposals
        self._validator = validator
        self._security = security
        self._knowledge = knowledge
        self._audit = audit
        self._code_search = code_search
        self._semantic = semantic
        self._preapproval = preapproval
        self._workflows = workflows
        self._workflow_selection = workflow_selection
        self._runtime = runtime
        self._context = context
        self._budget = budget
        self._config = config

    async def stream_run(self, run: AgentRun) -> AsyncIterator[dict[str, Any]]:
        run_id = run.id
        model = run.selected_model
        base_ref = run.base_branch
        task = run.task
        history = self._context.compact_history(list(run.history))
        status = await self._workspace.status()

        event_type = "run.resumed" if run.stage is not RunStage.CREATED else "run.started"
        self._audit.record(
            run_id=run_id,
            event_type=event_type,
            message=(
                "Agent Runtime V4 resumed from a persistent checkpoint."
                if event_type == "run.resumed"
                else "Agent Runtime V4 run started."
            ),
            metadata={
                "repository": status.repository or "",
                "model": model,
                "base_branch": base_ref,
                "stage": run.stage.value,
            },
        )
        yield {
            "type": "run",
            "run_id": run_id,
            "stage": run.stage.value,
            "message": (
                f"Agent Runtime V4 resumed from {run.stage.value}."
                if run.stage is not RunStage.CREATED
                else "Agent Runtime V4 started."
            ),
        }
        if run.route:
            yield {
                "type": "model_route",
                "stage": "routing",
                "route": {
                    "requested_model": run.route.requested_model,
                    "selected_model": run.route.selected_model,
                    "mode": run.route.mode,
                    "tier": run.route.tier,
                    "reason": run.route.reason,
                },
            }
        yield self._budget_event(run_id)

        raw_knowledge = (
            self._knowledge.retrieve(task, limit=self._config.agent_knowledge_limit)
            if self._config.agent_knowledge_enabled
            else []
        )
        knowledge_items = self._context.compact_knowledge(raw_knowledge)
        yield {
            "type": "knowledge",
            "stage": "memory",
            "items": self._knowledge.serialize(knowledge_items),
            "message": f"استرجع الوكيل {len(knowledge_items)} عنصر معرفة مضغوطًا ضمن ميزانية السياق.",
        }

        stage = run.stage
        payload = dict(run.checkpoint)

        if stage is RunStage.CREATED:
            yield {
                "type": "status",
                "stage": "discovery",
                "message": "Reading the selected branch and ranking relevant repository paths.",
            }
            tree = await self._workspace.list_files(ref=base_ref)
            if not tree:
                raise AgentValidationError("The selected repository branch contains no readable files.")
            candidates = self._code_search.rank_paths(
                task,
                tree,
                limit=max(
                    self._config.agent_semantic_candidate_files,
                    self._config.agent_max_read_files,
                ),
            )
            semantic_hits = []
            if self._config.agent_semantic_search_enabled:
                semantic_files = await self._workspace.read_files(
                    candidates[: self._config.agent_semantic_candidate_files],
                    ref=base_ref,
                )
                semantic_hits = await self._semantic.rank(
                    task=task,
                    files=semantic_files,
                    model=model,
                    limit=self._config.agent_semantic_top_k,
                    sample_chars=self._config.agent_semantic_sample_chars,
                )
            payload = {
                "tree": tree,
                "candidates": candidates,
                "semantic_hits": AgentCheckpointCodec.semantic_hits(semantic_hits),
            }
            run = self._runtime.checkpoint(
                run_id,
                stage=RunStage.DISCOVERY_READY,
                payload=payload,
            )
            self._audit.record(
                run_id=run_id,
                event_type="checkpoint.discovery",
                message="Discovery checkpoint persisted.",
                metadata={"candidate_count": len(candidates)},
            )
            yield {
                "type": "search",
                "stage": "discovery",
                "candidates": candidates[:16],
                "message": f"تم ترشيح {min(len(candidates), 16)} مسارًا مرتبطًا بالمهمة.",
            }
            yield {
                "type": "semantic",
                "stage": "semantic",
                "hits": self._semantic.serialize(semantic_hits),
                "message": f"حلل الوكيل {len(semantic_hits)} ملفًا دلاليًا.",
            }
            yield self._budget_event(run_id)
            stop = self._control_event(run)
            if stop:
                yield stop
                return
            stage = RunStage.DISCOVERY_READY

        if stage is RunStage.DISCOVERY_READY:
            tree = [str(path) for path in payload.get("tree") or []]
            candidates = [str(path) for path in payload.get("candidates") or []]
            semantic_hits = AgentCheckpointCodec.decode_semantic(payload.get("semantic_hits"))
            semantic_paths = [hit.path for hit in semantic_hits]
            planner_candidates = list(dict.fromkeys([*semantic_paths, *candidates]))
            plan = await self._planner.plan(
                task=task,
                history=history,
                tree=tree,
                search_candidates=planner_candidates,
                semantic_hits=semantic_hits,
                knowledge=knowledge_items,
                model=model,
                max_read_files=self._config.agent_max_read_files,
            )
            payload["plan"] = AgentCheckpointCodec.plan(plan)
            run = self._runtime.checkpoint(
                run_id,
                stage=RunStage.PLAN_READY,
                payload=payload,
            )
            self._audit.record(
                run_id=run_id,
                event_type="checkpoint.plan",
                message="Planner checkpoint persisted.",
                metadata={"files": list(plan.files_to_read)},
            )
            yield {
                "type": "plan",
                "summary": plan.summary,
                "steps": list(plan.steps),
                "files": list(plan.files_to_read),
            }
            yield self._budget_event(run_id)
            stop = self._control_event(run)
            if stop:
                yield stop
                return
            stage = RunStage.PLAN_READY

        if stage is RunStage.PLAN_READY:
            tree = [str(path) for path in payload.get("tree") or []]
            plan = AgentCheckpointCodec.decode_plan(payload.get("plan"))
            original_files = await self._workspace.read_files(
                list(plan.files_to_read),
                ref=base_ref,
            )
            files, dropped_paths = self._context.fit_files(original_files)
            report = self._context.report(
                original_history=list(run.history),
                prepared_history=history,
                original_knowledge=raw_knowledge,
                prepared_knowledge=knowledge_items,
                original_files=original_files,
                prepared_files=files,
                dropped_paths=dropped_paths,
            )
            self._runtime.set_context_report(run_id, report)
            yield {
                "type": "context",
                "stage": "context",
                "report": self._context.serialize(report),
                "message": (
                    "Context Manager compacted the run context."
                    if report.compacted
                    else "Context is within the configured budget without compaction."
                ),
            }
            if not files and plan.files_to_read:
                raise AgentValidationError("Context Manager could not retain any selected source file.")

            assistant_message, raw_changes = await self._coder.implement(
                task=task,
                plan=plan,
                tree=tree,
                files=files,
                knowledge=knowledge_items,
                review_feedback=(),
                model=model,
                max_tokens=self._config.agent_max_output_tokens,
            )
            changes = self._validator.validate(raw_changes, tree=tree, files=files)
            if not changes:
                self._audit.record(
                    run_id=run_id,
                    event_type="coder.no_changes",
                    message="Coder returned no justified file changes.",
                )
                self._runtime.complete(run_id)
                yield {"type": "delta", "content": assistant_message}
                yield self._budget_event(run_id)
                yield {"type": "done", "model": model, "proposal_id": None, "run_id": run_id}
                return

            risk = self._security.assess(task=task, changes=changes)
            yield {
                "type": "security",
                "stage": "security",
                "level": risk.level.value,
                "blocked": risk.blocked,
                "reasons": list(risk.reasons),
            }
            if risk.blocked:
                raise AgentValidationError("Security policy blocked the proposed changes.")

            review = await self._reviewer.review(
                task=task,
                plan=plan,
                files=files,
                changes=changes,
                risk=risk,
                knowledge=knowledge_items,
                model=model,
            )
            review_attempt = 0
            while (
                not review.approved
                and review.required_changes
                and review_attempt < self._config.agent_review_repair_attempts
            ):
                review_attempt += 1
                yield {
                    "type": "status",
                    "stage": "repair",
                    "message": f"Reviewer requested repair attempt {review_attempt}.",
                }
                assistant_message, raw_changes = await self._coder.implement(
                    task=task,
                    plan=plan,
                    tree=tree,
                    files=files,
                    knowledge=knowledge_items,
                    review_feedback=review.required_changes,
                    model=model,
                    max_tokens=self._config.agent_max_output_tokens,
                )
                changes = self._validator.validate(raw_changes, tree=tree, files=files)
                risk = self._security.assess(task=task, changes=changes)
                if risk.blocked:
                    raise AgentValidationError("Security policy blocked the repaired proposal.")
                review = await self._reviewer.review(
                    task=task,
                    plan=plan,
                    files=files,
                    changes=changes,
                    risk=risk,
                    knowledge=knowledge_items,
                    model=model,
                )

            yield {
                "type": "review",
                "stage": "review",
                "approved": review.approved,
                "score": review.score,
                "findings": list(review.findings),
                "required_changes": list(review.required_changes),
            }
            if not review.approved:
                self._runtime.complete(run_id)
                yield {"type": "delta", "content": assistant_message or "Independent review blocked the proposal."}
                yield self._budget_event(run_id)
                yield {
                    "type": "done",
                    "model": model,
                    "proposal_id": None,
                    "run_id": run_id,
                    "review_blocked": True,
                }
                return

            payload.update(
                {
                    "assistant_message": assistant_message,
                    "changes": AgentCheckpointCodec.changes(changes),
                    "risk": AgentCheckpointCodec.risk(risk),
                    "review": AgentCheckpointCodec.review(review),
                }
            )
            run = self._runtime.checkpoint(
                run_id,
                stage=RunStage.REVIEW_READY,
                payload=payload,
            )
            self._audit.record(
                run_id=run_id,
                event_type="checkpoint.review",
                message="Reviewed code checkpoint persisted.",
                metadata={"score": review.score, "files": [change.path for change in changes]},
            )
            yield self._budget_event(run_id)
            stop = self._control_event(run)
            if stop:
                yield stop
                return
            stage = RunStage.REVIEW_READY

        if stage is RunStage.REVIEW_READY:
            changes = AgentCheckpointCodec.decode_changes(payload.get("changes"))
            review = AgentCheckpointCodec.decode_review(payload.get("review"))
            changed_paths = [change.path for change in changes]
            suggested_profiles = self._workflow_selection.select_profiles(changed_paths)
            validation = await self._tester.validation_plan(
                task=task,
                changes=changes,
                review=review,
                suggested_profiles=suggested_profiles,
                model=model,
            )
            available_workflows = await self._workflows.list_workflows()
            payload["validation"] = AgentCheckpointCodec.validation(validation)
            run = self._runtime.checkpoint(
                run_id,
                stage=RunStage.VALIDATION_READY,
                payload=payload,
            )
            yield {
                "type": "validation",
                "stage": "testing",
                "checks": list(validation.checks),
                "workflow_profiles": list(validation.workflow_profiles),
                "browser_required": validation.browser_required,
                "available_workflows": [workflow.name for workflow in available_workflows],
                "runner": "pre-approval-sandbox + github-actions",
            }
            yield self._budget_event(run_id)
            stop = self._control_event(run)
            if stop:
                yield stop
                return
            stage = RunStage.VALIDATION_READY

        if stage is RunStage.VALIDATION_READY:
            tree = [str(path) for path in payload.get("tree") or []]
            plan = AgentCheckpointCodec.decode_plan(payload.get("plan"))
            changes = AgentCheckpointCodec.decode_changes(payload.get("changes"))
            review = AgentCheckpointCodec.decode_review(payload.get("review"))
            risk = AgentCheckpointCodec.decode_risk(payload.get("risk"))
            validation = AgentCheckpointCodec.decode_validation(payload.get("validation"))
            assistant_message = str(payload.get("assistant_message") or "")
            sandbox_result = None

            if self._config.agent_preapproval_validation_enabled:
                validation_attempt = 1
                while True:
                    yield {
                        "type": "status",
                        "stage": "sandbox",
                        "message": f"Running isolated pre-approval validation attempt {validation_attempt}.",
                    }
                    sandbox_result = await self._preapproval.validate(
                        changes=changes,
                        profiles=validation.workflow_profiles,
                        attempt=validation_attempt,
                        base_ref=base_ref,
                    )
                    yield {
                        "type": "sandbox_validation",
                        "stage": "sandbox",
                        **self._preapproval.serialize(sandbox_result),
                    }
                    if sandbox_result.passed:
                        break

                    feedback = self._preapproval.repair_feedback(sandbox_result)
                    if (
                        not feedback
                        or validation_attempt > self._config.agent_validation_repair_attempts
                    ):
                        self._runtime.complete(run_id)
                        yield {
                            "type": "delta",
                            "content": "Pre-approval validation still has blocking failures; no approval proposal was created.",
                        }
                        yield {
                            "type": "done",
                            "model": model,
                            "proposal_id": None,
                            "run_id": run_id,
                            "validation_blocked": True,
                        }
                        return

                    current_run = self._runtime.get(run_id)
                    if current_run.status in {RunStatus.PAUSE_REQUESTED, RunStatus.CANCEL_REQUESTED}:
                        run = self._runtime.checkpoint(
                            run_id,
                            stage=RunStage.VALIDATION_READY,
                            payload=payload,
                        )
                        stop = self._control_event(run)
                        if stop:
                            yield stop
                            return

                    files = await self._workspace.read_files(
                        list(plan.files_to_read),
                        ref=base_ref,
                    )
                    files, _ = self._context.fit_files(files)
                    yield {
                        "type": "status",
                        "stage": "auto-repair",
                        "message": f"Sandbox failed; Coder is repairing root causes ({validation_attempt}/{self._config.agent_validation_repair_attempts}).",
                    }
                    assistant_message, raw_changes = await self._coder.implement(
                        task=task,
                        plan=plan,
                        tree=tree,
                        files=files,
                        knowledge=knowledge_items,
                        review_feedback=feedback,
                        model=model,
                        max_tokens=self._config.agent_max_output_tokens,
                    )
                    changes = self._validator.validate(raw_changes, tree=tree, files=files)
                    risk = self._security.assess(task=task, changes=changes)
                    if risk.blocked:
                        raise AgentValidationError("Security policy blocked the validation repair.")
                    review = await self._reviewer.review(
                        task=task,
                        plan=plan,
                        files=files,
                        changes=changes,
                        risk=risk,
                        knowledge=knowledge_items,
                        model=model,
                    )
                    if not review.approved:
                        self._runtime.complete(run_id)
                        yield {
                            "type": "review",
                            "stage": "review",
                            "approved": False,
                            "score": review.score,
                            "findings": list(review.findings),
                            "required_changes": list(review.required_changes),
                        }
                        yield {"type": "done", "model": model, "proposal_id": None, "run_id": run_id, "review_blocked": True}
                        return
                    changed_paths = [change.path for change in changes]
                    validation = await self._tester.validation_plan(
                        task=task,
                        changes=changes,
                        review=review,
                        suggested_profiles=self._workflow_selection.select_profiles(changed_paths),
                        model=model,
                    )
                    payload.update(
                        {
                            "assistant_message": assistant_message,
                            "changes": AgentCheckpointCodec.changes(changes),
                            "risk": AgentCheckpointCodec.risk(risk),
                            "review": AgentCheckpointCodec.review(review),
                            "validation": AgentCheckpointCodec.validation(validation),
                        }
                    )
                    validation_attempt += 1

            if sandbox_result is None:
                from app.domain.agent_v3 import SandboxValidationResult
                sandbox_result = SandboxValidationResult(
                    passed=True,
                    attempt=0,
                    checks=(),
                    repairable=False,
                )

            payload["sandbox"] = AgentCheckpointCodec.sandbox(sandbox_result)
            run = self._runtime.checkpoint(
                run_id,
                stage=RunStage.SANDBOX_READY,
                payload=payload,
            )
            self._audit.record(
                run_id=run_id,
                event_type="checkpoint.sandbox",
                message="Sandbox-validated checkpoint persisted.",
                metadata={"passed": sandbox_result.passed},
            )
            yield self._budget_event(run_id)
            stop = self._control_event(run)
            if stop:
                yield stop
                return
            stage = RunStage.SANDBOX_READY

        if stage is RunStage.SANDBOX_READY:
            plan = AgentCheckpointCodec.decode_plan(payload.get("plan"))
            changes = AgentCheckpointCodec.decode_changes(payload.get("changes"))
            risk = AgentCheckpointCodec.decode_risk(payload.get("risk"))
            review = AgentCheckpointCodec.decode_review(payload.get("review"))
            validation = AgentCheckpointCodec.decode_validation(payload.get("validation"))
            sandbox_result = AgentCheckpointCodec.decode_sandbox(payload.get("sandbox"))
            assistant_message = str(payload.get("assistant_message") or plan.summary)

            proposal = ChangeProposal(
                id=uuid4().hex[:16],
                repository=status.repository or "",
                base_branch=base_ref,
                task=task,
                summary=assistant_message or plan.summary,
                plan=plan,
                changes=tuple(changes),
                run_id=run_id,
                review=review,
                validation=validation,
                risk=risk,
                knowledge_ids=tuple(item.id for item in knowledge_items),
                sandbox_validation=sandbox_result,
                approved_paths=(
                    ()
                    if self._config.agent_per_file_approval_enabled
                    else tuple(change.path for change in changes)
                ),
                parent_proposal_id=run.parent_proposal_id,
            )
            self._proposals.save(proposal)
            self._runtime.waiting_approval(run_id, proposal.id)
            self._audit.record(
                run_id=run_id,
                event_type="proposal.created",
                message="V4 proposal is waiting for explicit per-file approval.",
                metadata={
                    "proposal_id": proposal.id,
                    "files": [change.path for change in changes],
                    "parent_proposal_id": proposal.parent_proposal_id or "",
                },
            )
            yield {"type": "delta", "content": assistant_message}
            yield {"type": "approval_required", "proposal": proposal}
            yield self._budget_event(run_id)
            yield {
                "type": "done",
                "model": model,
                "proposal_id": proposal.id,
                "run_id": run_id,
                "waiting_approval": True,
            }

    def _budget_event(self, run_id: str) -> dict[str, object]:
        run = self._runtime.get(run_id)
        return {
            "type": "budget",
            "stage": "budget",
            "budget": self._budget.serialize(run.budget),
        }

    @staticmethod
    def _control_event(run: AgentRun) -> dict[str, object] | None:
        if run.status is RunStatus.PAUSED:
            return {
                "type": "run_control",
                "state": "paused",
                "run_id": run.id,
                "stage": run.stage.value,
                "message": "Run paused at a safe persistent checkpoint.",
            }
        if run.status is RunStatus.CANCELLED:
            return {
                "type": "run_control",
                "state": "cancelled",
                "run_id": run.id,
                "stage": run.stage.value,
                "message": "Run cancelled before the next stage started.",
            }
        return None

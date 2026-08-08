from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.audit_service import AgentAuditService
from app.application.change_validator import ChangeValidationService
from app.application.code_search_service import CodeSearchService
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.security_service import AgentSecurityService
from app.application.workflow_service import RepositoryWorkflowCatalog, WorkflowSelectionService
from app.config import Settings
from app.core.exceptions import AgentValidationError
from app.domain.agent import ChangeProposal
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
        workflows: RepositoryWorkflowCatalog,
        workflow_selection: WorkflowSelectionService,
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
        self._workflows = workflows
        self._workflow_selection = workflow_selection
        self._config = config

    async def stream_connected_task(
        self,
        *,
        task: str,
        model: str,
        history: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        run_id = f"run-{uuid4().hex[:16]}"
        status = await self._workspace.status()
        self._audit.record(
            run_id=run_id,
            event_type="run.started",
            message="Agent Core V2 run started.",
            metadata={"repository": status.repository or "", "model": model},
        )
        yield {
            "type": "run",
            "run_id": run_id,
            "stage": "started",
            "message": "Agent Core V2 started.",
        }

        knowledge_items = (
            self._knowledge.retrieve(task, limit=self._config.agent_knowledge_limit)
            if self._config.agent_knowledge_enabled
            else []
        )
        self._audit.record(
            run_id=run_id,
            event_type="knowledge.retrieved",
            message=f"Retrieved {len(knowledge_items)} relevant knowledge item(s).",
            metadata={"knowledge_ids": [item.id for item in knowledge_items]},
        )
        yield {
            "type": "knowledge",
            "stage": "memory",
            "items": self._knowledge.serialize(knowledge_items),
            "message": f"استرجع الوكيل {len(knowledge_items)} عنصر معرفة مرتبطًا بالمهمة.",
        }

        yield {
            "type": "status",
            "stage": "discovery",
            "message": "Reading the safe repository tree and ranking relevant paths.",
        }
        tree = await self._workspace.list_files()
        if not tree:
            raise AgentValidationError("The connected repository contains no readable files.")
        candidates = self._code_search.rank_paths(
            task,
            tree,
            limit=max(self._config.agent_max_read_files * 2, 12),
        )
        self._audit.record(
            run_id=run_id,
            event_type="search.completed",
            message="Repository path search completed.",
            metadata={"candidate_paths": candidates[:12], "tree_size": len(tree)},
        )
        yield {
            "type": "search",
            "stage": "discovery",
            "candidates": candidates[:12],
            "message": f"تم ترشيح {min(len(candidates), 12)} مسارًا مرتبطًا بالمهمة.",
        }

        plan = await self._planner.plan(
            task=task,
            history=history,
            tree=tree,
            search_candidates=candidates,
            knowledge=knowledge_items,
            model=model,
            max_read_files=self._config.agent_max_read_files,
        )
        self._audit.record(
            run_id=run_id,
            event_type="planner.completed",
            message="Planner completed the implementation plan.",
            metadata={"files": list(plan.files_to_read), "steps": len(plan.steps)},
        )
        yield {
            "type": "plan",
            "summary": plan.summary,
            "steps": list(plan.steps),
            "files": list(plan.files_to_read),
        }

        yield {
            "type": "status",
            "stage": "inspection",
            "message": f"Reading {len(plan.files_to_read)} selected file(s).",
        }
        files = await self._workspace.read_files(list(plan.files_to_read))

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
            yield {"type": "delta", "content": assistant_message}
            yield {"type": "done", "model": model, "proposal_id": None, "run_id": run_id}
            return

        risk = self._security.assess(task=task, changes=changes)
        self._audit.record(
            run_id=run_id,
            event_type="security.assessed",
            message=f"Security risk assessed as {risk.level.value}.",
            metadata={"level": risk.level.value, "blocked": risk.blocked},
        )
        yield {
            "type": "security",
            "stage": "security",
            "level": risk.level.value,
            "blocked": risk.blocked,
            "reasons": list(risk.reasons),
        }
        if risk.blocked:
            raise AgentValidationError(
                "Security policy blocked the proposed changes. Review the security findings before retrying."
            )

        review = await self._reviewer.review(
            task=task,
            plan=plan,
            files=files,
            changes=changes,
            risk=risk,
            knowledge=knowledge_items,
            model=model,
        )
        repair_attempt = 0
        while (
            not review.approved
            and review.required_changes
            and repair_attempt < self._config.agent_review_repair_attempts
        ):
            repair_attempt += 1
            self._audit.record(
                run_id=run_id,
                event_type="review.repair_requested",
                message=f"Reviewer requested repair attempt {repair_attempt}.",
                metadata={"required_changes": list(review.required_changes)},
            )
            yield {
                "type": "status",
                "stage": "repair",
                "message": f"Reviewer requested corrections; running repair attempt {repair_attempt}.",
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

        self._audit.record(
            run_id=run_id,
            event_type="review.completed",
            message=f"Independent review completed with score {review.score}/100.",
            metadata={"approved": review.approved, "score": review.score},
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
            yield {
                "type": "delta",
                "content": assistant_message or "The independent reviewer did not approve the proposed changes.",
            }
            yield {
                "type": "done",
                "model": model,
                "proposal_id": None,
                "run_id": run_id,
                "review_blocked": True,
            }
            return

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
        self._audit.record(
            run_id=run_id,
            event_type="tester.completed",
            message="Tester produced a validation plan.",
            metadata={
                "profiles": list(validation.workflow_profiles),
                "browser_required": validation.browser_required,
            },
        )
        yield {
            "type": "validation",
            "stage": "testing",
            "checks": list(validation.checks),
            "workflow_profiles": list(validation.workflow_profiles),
            "browser_required": validation.browser_required,
            "available_workflows": [workflow.name for workflow in available_workflows],
            "runner": self._config.agent_safe_runner_mode,
        }

        proposal = ChangeProposal(
            id=uuid4().hex[:16],
            repository=status.repository or "",
            base_branch=status.branch or self._config.agent_github_branch,
            task=task,
            summary=assistant_message or plan.summary,
            plan=plan,
            changes=tuple(changes),
            run_id=run_id,
            review=review,
            validation=validation,
            risk=risk,
            knowledge_ids=tuple(item.id for item in knowledge_items),
        )
        self._proposals.save(proposal)
        self._audit.record(
            run_id=run_id,
            event_type="proposal.created",
            message="Reviewed proposal is waiting for explicit user approval.",
            metadata={"proposal_id": proposal.id, "files": changed_paths},
        )

        yield {"type": "delta", "content": assistant_message}
        yield {
            "type": "approval_required",
            "proposal": proposal,
        }
        yield {
            "type": "done",
            "model": model,
            "proposal_id": proposal.id,
            "run_id": run_id,
        }

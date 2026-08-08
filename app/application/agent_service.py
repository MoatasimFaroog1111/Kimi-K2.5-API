import json
from collections.abc import AsyncIterator
from typing import Any

from app.application.agent_orchestrator import AgentOrchestrator
from app.application.audit_service import AgentAuditService
from app.application.ci_feedback_service import CiFeedbackService
from app.application.code_search_service import CodeSearchService
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.model_router import AgentModelRouter
from app.application.preapproval_validation_service import PreApprovalValidationService
from app.application.prompts import AGENT_STANDALONE_SYSTEM_PROMPT
from app.application.run_budget_service import RunBudgetService
from app.application.run_runtime_service import AgentRunRuntime
from app.application.workflow_service import RepositoryWorkflowCatalog
from app.config import Settings
from app.core.exceptions import ProposalNotFoundError, ProposalStateError
from app.domain.agent import ChangeProposal, ProposalStatus
from app.domain.agent_v4 import RunStatus
from app.domain.ports import LanguageModelPort, ProposalRepositoryPort, WorkspacePort


class AgentApplicationService:
    def __init__(
        self,
        *,
        model: LanguageModelPort,
        workspace: WorkspacePort,
        proposals: ProposalRepositoryPort,
        orchestrator: AgentOrchestrator,
        knowledge: ProjectKnowledgeService,
        audit: AgentAuditService,
        workflows: RepositoryWorkflowCatalog,
        code_search: CodeSearchService,
        ci_feedback: CiFeedbackService,
        runtime: AgentRunRuntime,
        router: AgentModelRouter,
        budget: RunBudgetService,
        config: Settings,
    ) -> None:
        self._model = model
        self._workspace = workspace
        self._proposals = proposals
        self._orchestrator = orchestrator
        self._knowledge = knowledge
        self._audit = audit
        self._workflows = workflows
        self._code_search = code_search
        self._ci_feedback = ci_feedback
        self._runtime = runtime
        self._router = router
        self._budget = budget
        self._config = config

    async def status(self) -> dict[str, Any]:
        status = await self._workspace.status()
        return {
            "configured": status.configured,
            "repository": status.repository,
            "branch": status.branch,
            "write_enabled": status.write_enabled,
            "mode": status.mode,
            "approval_required": True,
            "sandbox": "isolated-preapproval + github-pull-request",
            "agent_core_version": "4",
            "multi_agent": self._config.agent_v2_enabled,
            "semantic_intelligence": self._config.agent_semantic_search_enabled,
            "preapproval_validation": self._config.agent_preapproval_validation_enabled,
            "ci_feedback": self._config.agent_ci_feedback_enabled,
            "resumable_runtime": self._config.agent_v4_enabled,
            "model_router": self._config.agent_model_router_enabled,
            "per_file_approval": self._config.agent_per_file_approval_enabled,
            "ci_repair_proposals": self._config.agent_ci_repair_enabled,
            "roles": ["router", "semantic", "planner", "coder", "reviewer", "tester"],
            "memory": {
                "enabled": self._config.agent_knowledge_enabled,
                "backend": "sqlite",
                "path": self._config.agent_state_db_path,
            },
            "runtime": {
                "backend": "sqlite",
                "retention_days": self._config.agent_run_retention_days,
                "token_budget": self._config.agent_run_token_budget,
                "cost_budget_usd": self._config.agent_run_cost_budget_usd,
                "cost_tracking_configured": bool(self._config.model_pricing),
            },
            "safe_runner": "isolated-allowlist",
            "post_approval_runner": self._config.agent_safe_runner_mode,
            "browser_verification": self._config.agent_browser_verification_enabled,
            "capabilities": [
                "persistent-run-checkpoints",
                "pause-resume-cancel",
                "recent-run-reopen",
                "model-routing",
                "context-compaction",
                "token-budget",
                "optional-cost-budget",
                "per-file-approval",
                "ci-repair-proposal",
                "project-memory",
                "semantic-code-intelligence",
                "multi-agent-review",
                "security-risk-gate",
                "preapproval-sandbox",
                "automatic-validation-repair",
                "ci-feedback",
                "browser-smoke-planning",
                "audit-log",
            ],
        }

    async def stream_task(
        self,
        *,
        task: str,
        requested_model: str | None,
        auto_model: bool,
        history: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        workspace_status = await self._workspace.status()
        route = await self._router.route(
            task=task,
            requested_model=requested_model,
            auto=auto_model,
        )
        yield {
            "type": "status",
            "stage": "workspace",
            "message": (
                f"Connected to {workspace_status.repository}."
                if workspace_status.configured
                else "No repository is connected; running in planning-only mode."
            ),
            "workspace": await self.status(),
        }

        if not workspace_status.configured:
            yield {
                "type": "model_route",
                "stage": "routing",
                "route": AgentModelRouter.serialize(route),
            }
            yield {
                "type": "plan",
                "summary": "Planning-only mode",
                "steps": [
                    "Clarify the requested outcome",
                    "Design SOLID component boundaries",
                    "Identify implementation and validation steps",
                    "Connect a repository before proposing file changes",
                ],
                "files": [],
            }
            response = await self._model.complete(
                system_prompt=AGENT_STANDALONE_SYSTEM_PROMPT,
                user_prompt=json.dumps(
                    {"task": task, "recent_conversation": history[-8:]},
                    ensure_ascii=False,
                ),
                model=route.selected_model,
                max_tokens=2048,
            )
            yield {"type": "delta", "content": response}
            yield {"type": "done", "model": route.selected_model, "proposal_id": None}
            return

        run = self._runtime.create(
            task=task,
            requested_model=requested_model,
            route=route,
            base_branch=workspace_status.branch or self._config.agent_github_branch,
            history=history,
        )
        async for event in self._stream_persisted_run(run):
            yield event

    async def resume_run(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        run = self._runtime.begin_resume(run_id)
        async for event in self._stream_persisted_run(run):
            yield event

    def pause_run(self, run_id: str) -> dict[str, object]:
        run = self._runtime.request_pause(run_id)
        self._audit.record(
            run_id=run.id,
            event_type="run.pause_requested",
            message="User requested a safe checkpoint pause.",
        )
        return self._runtime.serialize(run)

    def cancel_run(self, run_id: str) -> dict[str, object]:
        run = self._runtime.request_cancel(run_id)
        self._audit.record(
            run_id=run.id,
            event_type="run.cancel_requested",
            message="User requested run cancellation.",
        )
        return self._runtime.serialize(run)

    def recent_runs(self, *, limit: int | None = None) -> list[dict[str, object]]:
        return [
            self._runtime.serialize(run)
            for run in self._runtime.recent(limit=limit)
        ]

    def run_detail(self, run_id: str) -> dict[str, object]:
        run = self._runtime.get(run_id)
        payload = self._runtime.serialize(run)
        if run.proposal_id:
            try:
                proposal = self._proposals.get(run.proposal_id)
            except ProposalNotFoundError:
                proposal = None
            if proposal:
                payload["proposal"] = self._serialize_proposal(
                    proposal,
                    can_approve=run.status is RunStatus.WAITING_APPROVAL,
                )
        return payload

    def set_file_approvals(
        self,
        proposal_id: str,
        paths: list[str],
    ) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalStateError("File approvals can only change on a pending proposal.")
        available = {change.path for change in proposal.changes}
        selected = tuple(dict.fromkeys(path for path in paths if path in available))
        if len(selected) != len(set(paths)):
            invalid = sorted(set(paths) - available)
            if invalid:
                raise ProposalStateError(
                    "Unknown proposal file(s): " + ", ".join(invalid[:6])
                )
        proposal.approved_paths = selected
        self._proposals.save(proposal)
        self._audit.record(
            run_id=proposal.run_id or proposal.id,
            event_type="proposal.file_approvals",
            message=f"User approved {len(selected)} of {len(proposal.changes)} proposed file(s).",
            metadata={"proposal_id": proposal.id, "approved_paths": list(selected)},
        )
        return self._serialize_proposal(proposal, can_approve=True)

    async def approve(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalStateError("Only pending proposals can be approved.")
        if proposal.review and not proposal.review.approved:
            raise ProposalStateError("Independent review has not approved this proposal.")
        if proposal.risk and proposal.risk.blocked:
            raise ProposalStateError("Security policy blocks this proposal.")
        if (
            self._config.agent_preapproval_validation_enabled
            and (not proposal.sandbox_validation or not proposal.sandbox_validation.passed)
        ):
            raise ProposalStateError(
                "Pre-approval sandbox validation has not passed this proposal."
            )
        if self._config.agent_per_file_approval_enabled and not proposal.approved_paths:
            raise ProposalStateError("Approve at least one proposed file first.")

        self._audit.record(
            run_id=proposal.run_id or proposal.id,
            event_type="proposal.approval_requested",
            message="User explicitly approved the selected sandbox-validated files.",
            metadata={
                "proposal_id": proposal.id,
                "approved_paths": list(proposal.approved_paths),
            },
        )
        try:
            applied = await self._workspace.apply_proposal(proposal)
        except Exception:
            proposal.status = ProposalStatus.PENDING
            self._proposals.save(proposal)
            self._audit.record(
                run_id=proposal.run_id or proposal.id,
                event_type="proposal.apply_failed",
                message="GitHub proposal application failed.",
                metadata={"proposal_id": proposal.id},
            )
            raise

        if self._config.agent_knowledge_enabled:
            item = self._knowledge.remember_proposal(
                applied,
                review=applied.review,
                validation=applied.validation,
            )
            applied.knowledge_ids = tuple(dict.fromkeys([*applied.knowledge_ids, item.id]))
        if self._config.agent_ci_feedback_enabled:
            applied.ci_feedback = await self._ci_feedback.feedback(applied)
        self._proposals.save(applied)
        self._runtime.after_proposal_action(applied.run_id)
        self._audit.record(
            run_id=applied.run_id or applied.id,
            event_type="proposal.applied",
            message="Pull Request created from explicitly approved files.",
            metadata={
                "proposal_id": applied.id,
                "pull_request_url": applied.pull_request_url or "",
                "applied_paths": list(applied.applied_paths),
                "ci_status": applied.ci_feedback.status if applied.ci_feedback else "disabled",
            },
        )
        return self._serialize_proposal(applied, can_approve=False)

    def reject(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalStateError("Only pending proposals can be rejected.")
        proposal.status = ProposalStatus.REJECTED
        self._proposals.save(proposal)
        self._runtime.after_proposal_action(proposal.run_id)
        self._audit.record(
            run_id=proposal.run_id or proposal.id,
            event_type="proposal.rejected",
            message="User rejected the proposal.",
            metadata={"proposal_id": proposal.id},
        )
        return self._serialize_proposal(proposal, can_approve=False)

    async def undo(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        undone = await self._workspace.undo_proposal(proposal)
        self._proposals.save(undone)
        self._audit.record(
            run_id=undone.run_id or undone.id,
            event_type="proposal.undone",
            message="Pull Request closed and agent branch removed.",
            metadata={"proposal_id": undone.id},
        )
        return self._serialize_proposal(undone, can_approve=False)

    async def proposal_ci(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.APPLIED:
            raise ProposalStateError("CI feedback is available only after a Pull Request exists.")
        feedback = await self._ci_feedback.feedback(proposal)
        proposal.ci_feedback = feedback
        self._proposals.save(proposal)
        self._audit.record(
            run_id=proposal.run_id or proposal.id,
            event_type="ci.feedback",
            message=f"CI feedback updated: {feedback.status}/{feedback.conclusion or 'pending'}.",
            metadata={
                "proposal_id": proposal.id,
                "status": feedback.status,
                "conclusion": feedback.conclusion,
            },
        )
        return self._ci_feedback.serialize(feedback)

    async def stream_ci_repair(
        self,
        proposal_id: str,
        *,
        requested_model: str | None,
        auto_model: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self._config.agent_ci_repair_enabled:
            raise ProposalStateError("CI repair proposals are disabled.")
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.APPLIED or not proposal.branch_name:
            raise ProposalStateError("A CI repair requires an existing applied Pull Request.")
        feedback = await self._ci_feedback.feedback(proposal)
        proposal.ci_feedback = feedback
        self._proposals.save(proposal)
        if feedback.status != "completed" or feedback.conclusion != "failure":
            raise ProposalStateError("CI repair can start only after CI has completed with failures.")

        failure_context = []
        for job in feedback.jobs:
            if job.conclusion != "failure":
                continue
            failure_context.append(
                {
                    "job": job.name,
                    "failed_steps": list(job.failed_steps),
                    "log_excerpt": job.log_excerpt[-3000:],
                }
            )
        task = (
            "Create a separate, reviewable fix proposal for the CI failures of an existing "
            "agent Pull Request. Do not modify the existing Pull Request branch directly. "
            "Fix only the root causes supported by the CI evidence.\n\n"
            f"Original task: {proposal.task}\n"
            f"Parent proposal: {proposal.id}\n"
            f"CI evidence: {json.dumps(failure_context, ensure_ascii=False)}"
        )
        route = await self._router.route(
            task=task,
            requested_model=requested_model,
            auto=auto_model,
        )
        run = self._runtime.create(
            task=task,
            requested_model=requested_model,
            route=route,
            base_branch=proposal.branch_name,
            history=[],
            parent_proposal_id=proposal.id,
        )
        self._audit.record(
            run_id=run.id,
            event_type="ci.repair_run_created",
            message="CI failure created a separate fix-proposal run.",
            metadata={
                "parent_proposal_id": proposal.id,
                "base_branch": proposal.branch_name,
            },
        )
        async for event in self._stream_persisted_run(run):
            yield event

    def memory(self, *, query: str = "", limit: int = 20) -> list[dict[str, object]]:
        items = (
            self._knowledge.retrieve(query, limit=limit)
            if query.strip()
            else self._knowledge.recent(limit=limit)
        )
        return self._knowledge.serialize(items)

    def audit_events(self, *, limit: int | None = None) -> list[dict[str, object]]:
        return self._audit.recent(limit=limit or self._config.agent_audit_limit)

    async def workflow_catalog(self) -> list[dict[str, object]]:
        workflows = await self._workflows.list_workflows()
        return [
            {
                "name": workflow.name,
                "description": workflow.description,
                "safe_to_auto_run": workflow.safe_to_auto_run,
                "steps": list(workflow.steps),
            }
            for workflow in workflows
        ]

    async def search_paths(self, query: str, *, limit: int = 24) -> list[str]:
        tree = await self._workspace.list_files()
        return self._code_search.rank_paths(query, tree, limit=limit)

    async def _stream_persisted_run(self, run) -> AsyncIterator[dict[str, Any]]:
        try:
            with self._budget.bind(run.id):
                async for event in self._orchestrator.stream_run(run):
                    if event.get("type") == "approval_required" and isinstance(
                        event.get("proposal"), ChangeProposal
                    ):
                        proposal = event["proposal"]
                        yield {
                            **event,
                            "proposal": self._serialize_proposal(
                                proposal,
                                can_approve=True,
                            ),
                        }
                    else:
                        yield event
        except Exception as exc:
            current = self._runtime.get(run.id)
            if current.status not in {RunStatus.CANCELLED, RunStatus.COMPLETED}:
                self._runtime.fail(run.id, str(exc))
            raise

    def _serialize_proposal(
        self,
        proposal: ChangeProposal,
        can_approve: bool,
    ) -> dict[str, Any]:
        review = proposal.review
        validation = proposal.validation
        risk = proposal.risk
        sandbox = proposal.sandbox_validation
        ci = proposal.ci_feedback
        sandbox_passed = sandbox.passed if sandbox else False
        file_gate = (
            bool(proposal.approved_paths)
            if self._config.agent_per_file_approval_enabled
            else True
        )
        approved_set = set(proposal.approved_paths)
        return {
            "id": proposal.id,
            "run_id": proposal.run_id,
            "repository": proposal.repository,
            "base_branch": proposal.base_branch,
            "summary": proposal.summary,
            "status": proposal.status.value,
            "can_approve": (
                can_approve
                and proposal.status is ProposalStatus.PENDING
                and (sandbox_passed or sandbox is None)
                and file_gate
            ),
            "can_select_files": proposal.status is ProposalStatus.PENDING,
            "requires_file_approval": self._config.agent_per_file_approval_enabled,
            "approved_paths": list(proposal.approved_paths),
            "applied_paths": list(proposal.applied_paths),
            "parent_proposal_id": proposal.parent_proposal_id,
            "branch_name": proposal.branch_name,
            "pull_request_url": proposal.pull_request_url,
            "knowledge_ids": list(proposal.knowledge_ids),
            "review": (
                {
                    "approved": review.approved,
                    "score": review.score,
                    "findings": list(review.findings),
                    "required_changes": list(review.required_changes),
                }
                if review
                else None
            ),
            "validation": (
                {
                    "checks": list(validation.checks),
                    "workflow_profiles": list(validation.workflow_profiles),
                    "browser_required": validation.browser_required,
                }
                if validation
                else None
            ),
            "sandbox_validation": (
                PreApprovalValidationService.serialize(sandbox)
                if sandbox
                else None
            ),
            "ci_feedback": (
                CiFeedbackService.serialize(ci)
                if ci
                else None
            ),
            "risk": (
                {
                    "level": risk.level.value,
                    "blocked": risk.blocked,
                    "reasons": list(risk.reasons),
                }
                if risk
                else None
            ),
            "changes": [
                {
                    "path": change.path,
                    "reason": change.reason,
                    "diff": change.diff,
                    "approved": change.path in approved_set,
                    "applied": change.path in set(proposal.applied_paths),
                }
                for change in proposal.changes
            ],
        }

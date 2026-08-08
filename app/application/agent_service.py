import json
from collections.abc import AsyncIterator
from typing import Any

from app.application.agent_orchestrator import AgentOrchestrator
from app.application.audit_service import AgentAuditService
from app.application.ci_feedback_service import CiFeedbackService
from app.application.code_search_service import CodeSearchService
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.prompts import AGENT_STANDALONE_SYSTEM_PROMPT
from app.application.workflow_service import RepositoryWorkflowCatalog
from app.config import Settings
from app.core.exceptions import ProposalStateError
from app.domain.agent import ChangeProposal, ProposalStatus
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
            "agent_core_version": "3",
            "multi_agent": self._config.agent_v2_enabled,
            "semantic_intelligence": self._config.agent_semantic_search_enabled,
            "preapproval_validation": self._config.agent_preapproval_validation_enabled,
            "ci_feedback": self._config.agent_ci_feedback_enabled,
            "roles": ["semantic", "planner", "coder", "reviewer", "tester"],
            "memory": {
                "enabled": self._config.agent_knowledge_enabled,
                "backend": "sqlite",
                "path": self._config.agent_state_db_path,
            },
            "safe_runner": "isolated-allowlist",
            "post_approval_runner": self._config.agent_safe_runner_mode,
            "browser_verification": self._config.agent_browser_verification_enabled,
            "capabilities": [
                "project-memory",
                "knowledge-retrieval",
                "codebase-path-search",
                "semantic-code-intelligence",
                "multi-agent-review",
                "security-risk-gate",
                "preapproval-sandbox",
                "automatic-validation-repair",
                "workflow-catalog",
                "ci-feedback",
                "browser-smoke-planning",
                "audit-log",
                "pull-request-approval",
            ],
        }

    async def stream_task(
        self,
        *,
        task: str,
        model: str,
        history: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        workspace_status = await self._workspace.status()
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
                model=model,
                max_tokens=2048,
            )
            yield {"type": "delta", "content": response}
            yield {"type": "done", "model": model, "proposal_id": None}
            return

        async for event in self._orchestrator.stream_connected_task(
            task=task,
            model=model,
            history=history,
        ):
            if event.get("type") == "approval_required" and isinstance(
                event.get("proposal"), ChangeProposal
            ):
                proposal = event["proposal"]
                yield {
                    **event,
                    "proposal": self._serialize_proposal(
                        proposal,
                        can_approve=workspace_status.write_enabled,
                    ),
                }
            else:
                yield event

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

        self._audit.record(
            run_id=proposal.run_id or proposal.id,
            event_type="proposal.approval_requested",
            message="User explicitly approved the sandbox-validated proposal.",
            metadata={"proposal_id": proposal.id},
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
        self._audit.record(
            run_id=applied.run_id or applied.id,
            event_type="proposal.applied",
            message="Pull Request created after user approval.",
            metadata={
                "proposal_id": applied.id,
                "pull_request_url": applied.pull_request_url or "",
                "knowledge_ids": list(applied.knowledge_ids),
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

    @staticmethod
    def _serialize_proposal(
        proposal: ChangeProposal,
        can_approve: bool,
    ) -> dict[str, Any]:
        review = proposal.review
        validation = proposal.validation
        risk = proposal.risk
        sandbox = proposal.sandbox_validation
        ci = proposal.ci_feedback
        sandbox_passed = sandbox.passed if sandbox else False
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
            ),
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
                }
                for change in proposal.changes
            ],
        }


from app.application.preapproval_validation_service import PreApprovalValidationService

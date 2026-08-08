from uuid import uuid4

from app.config import Settings
from app.core.exceptions import AgentRunStateError
from app.domain.agent_v4 import AgentRun, ModelRoute, RunBudget, RunStage, RunStatus
from app.domain.ports import RunRepositoryPort


class AgentRunRuntime:
    def __init__(self, runs: RunRepositoryPort, config: Settings) -> None:
        self._runs = runs
        self._config = config

    def create(
        self,
        *,
        task: str,
        requested_model: str | None,
        route: ModelRoute,
        base_branch: str,
        history: list[dict[str, str]],
        parent_proposal_id: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=f"run-{uuid4().hex[:16]}",
            task=task,
            requested_model=requested_model,
            selected_model=route.selected_model,
            base_branch=base_branch,
            history=tuple(history[-20:]),
            route=route,
            parent_proposal_id=parent_proposal_id,
            budget=RunBudget(
                token_limit=self._config.agent_run_token_budget,
                cost_limit_usd=self._config.agent_run_cost_budget_usd,
            ),
        )
        self._runs.save(run)
        return run

    def get(self, run_id: str) -> AgentRun:
        return self._runs.get(run_id)

    def recent(self, *, limit: int | None = None) -> list[AgentRun]:
        return self._runs.recent(limit=limit or self._config.agent_recent_runs_limit)

    def request_pause(self, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run.status is RunStatus.PAUSED:
            return run
        if run.status is not RunStatus.RUNNING:
            raise AgentRunStateError("Only a running agent run can be paused.")
        run.status = RunStatus.PAUSE_REQUESTED
        self._runs.save(run)
        return run

    def request_cancel(self, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run.status in {RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED}:
            return run
        if run.status is RunStatus.PAUSED:
            run.status = RunStatus.CANCELLED
        elif run.status in {RunStatus.RUNNING, RunStatus.PAUSE_REQUESTED}:
            run.status = RunStatus.CANCEL_REQUESTED
        elif run.status is RunStatus.WAITING_APPROVAL:
            run.status = RunStatus.CANCELLED
        else:
            raise AgentRunStateError("This run cannot be cancelled from its current state.")
        self._runs.save(run)
        return run

    def begin_resume(self, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run.status is not RunStatus.PAUSED:
            raise AgentRunStateError("Only a paused agent run can be resumed.")
        run.status = RunStatus.RUNNING
        run.error = ""
        self._runs.save(run)
        return run

    def checkpoint(
        self,
        run_id: str,
        *,
        stage: RunStage,
        payload: dict[str, object],
    ) -> AgentRun:
        run = self._runs.get(run_id)
        run.stage = stage
        run.checkpoint = payload
        if run.status is RunStatus.PAUSE_REQUESTED:
            run.status = RunStatus.PAUSED
        elif run.status is RunStatus.CANCEL_REQUESTED:
            run.status = RunStatus.CANCELLED
        self._runs.save(run)
        return run

    def set_context_report(self, run_id: str, report) -> AgentRun:
        run = self._runs.get(run_id)
        run.context_report = report
        self._runs.save(run)
        return run

    def waiting_approval(self, run_id: str, proposal_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        run.status = RunStatus.WAITING_APPROVAL
        run.stage = RunStage.WAITING_APPROVAL
        run.proposal_id = proposal_id
        self._runs.save(run)
        return run

    def complete(self, run_id: str, proposal_id: str | None = None) -> AgentRun:
        run = self._runs.get(run_id)
        run.status = RunStatus.COMPLETED
        run.stage = RunStage.COMPLETED
        if proposal_id:
            run.proposal_id = proposal_id
        self._runs.save(run)
        return run

    def fail(self, run_id: str, error: str) -> AgentRun:
        run = self._runs.get(run_id)
        run.status = RunStatus.FAILED
        run.error = error[:2000]
        self._runs.save(run)
        return run

    def after_proposal_action(self, run_id: str | None) -> None:
        if not run_id:
            return
        run = self._runs.get(run_id)
        if run.status is RunStatus.WAITING_APPROVAL:
            run.status = RunStatus.COMPLETED
            run.stage = RunStage.COMPLETED
            self._runs.save(run)

    @staticmethod
    def should_stop(run: AgentRun) -> bool:
        return run.status in {RunStatus.PAUSED, RunStatus.CANCELLED}

    @staticmethod
    def serialize(run: AgentRun) -> dict[str, object]:
        return {
            "id": run.id,
            "task": run.task,
            "requested_model": run.requested_model,
            "selected_model": run.selected_model,
            "base_branch": run.base_branch,
            "status": run.status.value,
            "stage": run.stage.value,
            "parent_proposal_id": run.parent_proposal_id,
            "proposal_id": run.proposal_id,
            "route": (
                {
                    "requested_model": run.route.requested_model,
                    "selected_model": run.route.selected_model,
                    "mode": run.route.mode,
                    "tier": run.route.tier,
                    "reason": run.route.reason,
                }
                if run.route
                else None
            ),
            "budget": {
                "token_limit": run.budget.token_limit,
                "estimated_tokens_used": run.budget.estimated_tokens_used,
                "remaining_tokens": run.budget.remaining_tokens,
                "cost_limit_usd": run.budget.cost_limit_usd,
                "estimated_cost_usd": run.budget.estimated_cost_usd,
                "cost_tracking": run.budget.cost_tracking,
            },
            "context_report": (
                {
                    "original_chars": run.context_report.original_chars,
                    "prepared_chars": run.context_report.prepared_chars,
                    "estimated_tokens": run.context_report.estimated_tokens,
                    "history_messages": run.context_report.history_messages,
                    "knowledge_items": run.context_report.knowledge_items,
                    "file_count": run.context_report.file_count,
                    "dropped_paths": list(run.context_report.dropped_paths),
                    "compacted": run.context_report.compacted,
                }
                if run.context_report
                else None
            ),
            "error": run.error,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "resumable": run.status is RunStatus.PAUSED,
            "cancellable": run.status in {
                RunStatus.RUNNING,
                RunStatus.PAUSE_REQUESTED,
                RunStatus.PAUSED,
                RunStatus.WAITING_APPROVAL,
            },
        }

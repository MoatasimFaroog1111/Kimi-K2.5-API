import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from app.core.exceptions import AgentRunNotFoundError
from app.domain.agent_v4 import (
    AgentRun,
    ContextReport,
    ModelRoute,
    RunBudget,
    RunStage,
    RunStatus,
)


class SQLiteRunStore:
    def __init__(self, database_path: str, retention_days: int) -> None:
        self._path = database_path
        self._retention = timedelta(days=retention_days)
        self._lock = RLock()
        self._prepare_parent()
        self._initialize()

    def save(self, run: AgentRun) -> None:
        run.updated_at = datetime.now(timezone.utc)
        payload = json.dumps(self._serialize(run), ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id, status, stage, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    stage=excluded.stage,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    run.id,
                    run.status.value,
                    run.stage.value,
                    payload,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )
        self._remove_expired()

    def get(self, run_id: str) -> AgentRun:
        self._remove_expired()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM agent_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise AgentRunNotFoundError("Agent run was not found or has expired.")
        try:
            return self._deserialize(json.loads(row[0]))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise AgentRunNotFoundError("Stored agent run is invalid.") from exc

    def recent(self, *, limit: int = 50) -> list[AgentRun]:
        self._remove_expired()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM agent_runs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        runs: list[AgentRun] = []
        for row in rows:
            try:
                runs.append(self._deserialize(json.loads(row[0])))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return runs

    def _remove_expired(self) -> None:
        cutoff = (datetime.now(timezone.utc) - self._retention).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM agent_runs WHERE updated_at < ?", (cutoff,))

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_updated ON agent_runs(updated_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _prepare_parent(self) -> None:
        if self._path == ":memory:":
            return
        Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _serialize(run: AgentRun) -> dict[str, object]:
        return {
            "id": run.id,
            "task": run.task,
            "requested_model": run.requested_model,
            "selected_model": run.selected_model,
            "base_branch": run.base_branch,
            "history": list(run.history),
            "status": run.status.value,
            "stage": run.stage.value,
            "checkpoint": run.checkpoint,
            "parent_proposal_id": run.parent_proposal_id,
            "proposal_id": run.proposal_id,
            "budget": {
                "token_limit": run.budget.token_limit,
                "estimated_tokens_used": run.budget.estimated_tokens_used,
                "cost_limit_usd": run.budget.cost_limit_usd,
                "estimated_cost_usd": run.budget.estimated_cost_usd,
                "cost_tracking": run.budget.cost_tracking,
            },
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
        }

    @staticmethod
    def _deserialize(payload: dict) -> AgentRun:
        budget_payload = payload.get("budget") or {}
        budget = RunBudget(
            token_limit=int(budget_payload.get("token_limit") or 60_000),
            estimated_tokens_used=int(budget_payload.get("estimated_tokens_used") or 0),
            cost_limit_usd=float(budget_payload.get("cost_limit_usd") or 0.0),
            estimated_cost_usd=(
                float(budget_payload["estimated_cost_usd"])
                if budget_payload.get("estimated_cost_usd") is not None
                else None
            ),
            cost_tracking=bool(budget_payload.get("cost_tracking")),
        )

        route_payload = payload.get("route")
        route = None
        if isinstance(route_payload, dict):
            route = ModelRoute(
                requested_model=route_payload.get("requested_model"),
                selected_model=str(route_payload.get("selected_model") or ""),
                mode=str(route_payload.get("mode") or "auto"),
                tier=str(route_payload.get("tier") or "balanced"),
                reason=str(route_payload.get("reason") or ""),
            )

        context_payload = payload.get("context_report")
        context = None
        if isinstance(context_payload, dict):
            context = ContextReport(
                original_chars=int(context_payload.get("original_chars") or 0),
                prepared_chars=int(context_payload.get("prepared_chars") or 0),
                estimated_tokens=int(context_payload.get("estimated_tokens") or 0),
                history_messages=int(context_payload.get("history_messages") or 0),
                knowledge_items=int(context_payload.get("knowledge_items") or 0),
                file_count=int(context_payload.get("file_count") or 0),
                dropped_paths=tuple(context_payload.get("dropped_paths") or []),
                compacted=bool(context_payload.get("compacted")),
            )

        def parse_time(value: object) -> datetime:
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                return datetime.now(timezone.utc)

        try:
            status = RunStatus(str(payload.get("status") or RunStatus.RUNNING.value))
        except ValueError:
            status = RunStatus.RUNNING
        try:
            stage = RunStage(str(payload.get("stage") or RunStage.CREATED.value))
        except ValueError:
            stage = RunStage.CREATED

        history = tuple(
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in payload.get("history") or []
            if isinstance(item, dict)
        )

        return AgentRun(
            id=str(payload.get("id") or ""),
            task=str(payload.get("task") or ""),
            requested_model=payload.get("requested_model"),
            selected_model=str(payload.get("selected_model") or ""),
            base_branch=str(payload.get("base_branch") or "main"),
            history=history,
            status=status,
            stage=stage,
            checkpoint=(
                dict(payload.get("checkpoint") or {})
                if isinstance(payload.get("checkpoint") or {}, dict)
                else {}
            ),
            parent_proposal_id=payload.get("parent_proposal_id"),
            proposal_id=payload.get("proposal_id"),
            budget=budget,
            route=route,
            context_report=context,
            error=str(payload.get("error") or ""),
            created_at=parse_time(payload.get("created_at")),
            updated_at=parse_time(payload.get("updated_at")),
        )

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.domain.agent_v2 import AuditEvent

logger = logging.getLogger("kimi.agent.audit")


class SQLiteAuditLog:
    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._lock = RLock()
        self._prepare_parent()
        self._initialize()

    def record(self, event: AuditEvent) -> None:
        payload = json.dumps(event.metadata, ensure_ascii=False, default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    id, run_id, event_type, message, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.event_type,
                    event.message,
                    payload,
                    event.created_at.isoformat(),
                ),
            )
        logger.info(
            "agent_audit run_id=%s type=%s message=%s metadata=%s",
            event.run_id,
            event.event_type,
            event.message,
            payload,
        )

    def recent(self, *, limit: int = 100) -> list[AuditEvent]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, event_type, message, metadata_json, created_at
                FROM audit_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id)"
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
    def _row_to_event(row) -> AuditEvent:
        try:
            created_at = datetime.fromisoformat(row[5])
        except ValueError:
            created_at = datetime.now(timezone.utc)
        try:
            metadata = json.loads(row[4])
        except json.JSONDecodeError:
            metadata = {}
        return AuditEvent(
            id=row[0],
            run_id=row[1],
            event_type=row[2],
            message=row[3],
            metadata=metadata if isinstance(metadata, dict) else {},
            created_at=created_at,
        )

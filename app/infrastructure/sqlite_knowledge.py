import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.domain.agent_v2 import KnowledgeItem


class SQLiteKnowledgeRepository:
    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._lock = RLock()
        self._prepare_parent()
        self._initialize()

    def save(self, item: KnowledgeItem) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    id, title, summary, tags_json, paths_json, source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    summary=excluded.summary,
                    tags_json=excluded.tags_json,
                    paths_json=excluded.paths_json,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    item.id,
                    item.title,
                    item.summary,
                    json.dumps(item.tags, ensure_ascii=False),
                    json.dumps(item.paths, ensure_ascii=False),
                    item.source,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeItem]:
        terms = self._terms(query)
        candidates = self.recent(limit=200)
        if not terms:
            return candidates[:limit]

        scored: list[tuple[int, KnowledgeItem]] = []
        for item in candidates:
            title = item.title.casefold()
            summary = item.summary.casefold()
            tags = " ".join(item.tags).casefold()
            paths = " ".join(item.paths).casefold()
            score = 0
            for term in terms:
                score += 5 if term in title else 0
                score += 3 if term in tags else 0
                score += 2 if term in paths else 0
                score += 1 if term in summary else 0
            if score:
                scored.append((score, item))

        scored.sort(
            key=lambda pair: (pair[0], pair[1].updated_at),
            reverse=True,
        )
        return [item for _, item in scored[:limit]]

    def recent(self, *, limit: int = 20) -> list[KnowledgeItem]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, summary, tags_json, paths_json, source,
                       created_at, updated_at
                FROM knowledge_items
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    paths_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_updated ON knowledge_items(updated_at)"
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
    def _terms(value: str) -> tuple[str, ...]:
        tokens = re.findall(r"[\w./-]{3,}", value.casefold(), flags=re.UNICODE)
        return tuple(dict.fromkeys(tokens))[:24]

    @staticmethod
    def _row_to_item(row) -> KnowledgeItem:
        def parse_date(value: str) -> datetime:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return datetime.now(timezone.utc)

        return KnowledgeItem(
            id=row[0],
            title=row[1],
            summary=row[2],
            tags=tuple(json.loads(row[3]) or []),
            paths=tuple(json.loads(row[4]) or []),
            source=row[5],
            created_at=parse_date(row[6]),
            updated_at=parse_date(row[7]),
        )

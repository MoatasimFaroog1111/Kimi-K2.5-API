from dataclasses import replace

from app.config import Settings
from app.domain.agent import WorkspaceFile
from app.domain.agent_v2 import KnowledgeItem
from app.domain.agent_v4 import ContextReport


class AgentContextManager:
    def __init__(self, config: Settings) -> None:
        self._config = config

    def compact_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        budget = self._config.agent_context_history_chars
        selected: list[dict[str, str]] = []
        used = 0
        for item in reversed(history[-40:]):
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            remaining = budget - used
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[-remaining:]
            selected.append({"role": role, "content": content})
            used += len(content)
        selected.reverse()
        return selected

    def compact_knowledge(self, items: list[KnowledgeItem]) -> list[KnowledgeItem]:
        budget = self._config.agent_context_knowledge_chars
        selected: list[KnowledgeItem] = []
        used = 0
        for item in items:
            remaining = budget - used
            if remaining <= 0:
                break
            summary = item.summary.strip()
            if len(summary) > remaining:
                summary = summary[: max(0, remaining - 1)] + "…"
            selected.append(replace(item, summary=summary))
            used += len(summary) + len(item.title)
        return selected

    def fit_files(
        self,
        files: list[WorkspaceFile],
    ) -> tuple[list[WorkspaceFile], tuple[str, ...]]:
        target = min(
            self._config.agent_context_target_chars,
            self._config.agent_max_context_bytes,
        )
        selected: list[WorkspaceFile] = []
        dropped: list[str] = []
        used = 0
        for file in files:
            size = len(file.content)
            if selected and used + size > target:
                dropped.append(file.path)
                continue
            selected.append(file)
            used += size
        return selected, tuple(dropped)

    def report(
        self,
        *,
        original_history: list[dict[str, str]],
        prepared_history: list[dict[str, str]],
        original_knowledge: list[KnowledgeItem],
        prepared_knowledge: list[KnowledgeItem],
        original_files: list[WorkspaceFile],
        prepared_files: list[WorkspaceFile],
        dropped_paths: tuple[str, ...],
    ) -> ContextReport:
        original_chars = (
            sum(len(str(item.get("content") or "")) for item in original_history)
            + sum(len(item.summary) for item in original_knowledge)
            + sum(len(file.content) for file in original_files)
        )
        prepared_chars = (
            sum(len(str(item.get("content") or "")) for item in prepared_history)
            + sum(len(item.summary) for item in prepared_knowledge)
            + sum(len(file.content) for file in prepared_files)
        )
        return ContextReport(
            original_chars=original_chars,
            prepared_chars=prepared_chars,
            estimated_tokens=self.estimate_tokens(prepared_chars),
            history_messages=len(prepared_history),
            knowledge_items=len(prepared_knowledge),
            file_count=len(prepared_files),
            dropped_paths=dropped_paths,
            compacted=prepared_chars < original_chars or bool(dropped_paths),
        )

    @staticmethod
    def estimate_tokens(chars: int) -> int:
        return max(1, (max(0, chars) + 3) // 4)

    @staticmethod
    def serialize(report: ContextReport) -> dict[str, object]:
        return {
            "original_chars": report.original_chars,
            "prepared_chars": report.prepared_chars,
            "estimated_tokens": report.estimated_tokens,
            "history_messages": report.history_messages,
            "knowledge_items": report.knowledge_items,
            "file_count": report.file_count,
            "dropped_paths": list(report.dropped_paths),
            "compacted": report.compacted,
        }

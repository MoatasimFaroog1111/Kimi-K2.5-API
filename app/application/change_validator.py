from difflib import unified_diff
from typing import Any

from app.config import Settings
from app.core.exceptions import AgentValidationError
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ProposedFileChange, WorkspaceFile


class ChangeValidationService:
    def __init__(self, policy: WorkspacePolicy, config: Settings) -> None:
        self._policy = policy
        self._config = config

    def validate(
        self,
        raw_changes: list[dict[str, Any]],
        *,
        tree: list[str],
        files: list[WorkspaceFile],
    ) -> list[ProposedFileChange]:
        self._policy.validate_change_count(len(raw_changes))
        existing = {file.path: file for file in files}
        tree_set = set(tree)
        seen: set[str] = set()
        validated: list[ProposedFileChange] = []

        for item in raw_changes:
            path = self._policy.validate_path(str(item.get("path") or ""))
            if path in seen:
                raise AgentValidationError(f"Duplicate proposed file: {path}")
            if path in tree_set and path not in existing:
                raise AgentValidationError(
                    f"Agent attempted to modify an unread existing file: {path}"
                )
            content = item.get("content")
            if not isinstance(content, str):
                raise AgentValidationError(f"Complete content is required for {path}.")
            self._policy.validate_content(path, content)
            if len(content.encode("utf-8")) > self._config.agent_max_file_bytes:
                raise AgentValidationError(f"Proposed file exceeds size limit: {path}")
            reason = str(item.get("reason") or "Agent implementation").strip()
            original = existing.get(path)
            validated.append(
                ProposedFileChange(
                    path=path,
                    content=content,
                    reason=reason,
                    original_sha=original.sha if original else None,
                    original_content=original.content if original else None,
                    diff=self._build_diff(
                        path,
                        original.content if original else "",
                        content,
                    ),
                )
            )
            seen.add(path)

        return validated

    @staticmethod
    def _build_diff(path: str, before: str, after: str) -> str:
        return "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )[:30_000]

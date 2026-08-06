from pathlib import PurePosixPath

from app.core.exceptions import AgentValidationError


class WorkspacePolicy:
    _BLOCKED_NAMES = {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
        "authorized_keys",
    }
    _BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks"}
    _BLOCKED_PARTS = {".git", "node_modules", ".venv", "venv", "dist", "build"}

    def __init__(
        self,
        *,
        allowed_prefixes: tuple[str, ...],
        max_file_bytes: int,
        max_change_files: int,
    ) -> None:
        self._allowed_prefixes = allowed_prefixes
        self._max_file_bytes = max_file_bytes
        self._max_change_files = max_change_files

    def validate_path(self, raw_path: str) -> str:
        normalized = raw_path.replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)

        if not normalized or normalized in {".", ".."}:
            raise AgentValidationError("File path is empty or invalid.")
        if path.is_absolute() or ".." in path.parts:
            raise AgentValidationError(f"Unsafe path: {raw_path}")
        if any(part in self._BLOCKED_PARTS for part in path.parts):
            raise AgentValidationError(f"Blocked path: {normalized}")
        if path.name.lower() in self._BLOCKED_NAMES:
            raise AgentValidationError(f"Sensitive file is blocked: {normalized}")
        if path.suffix.lower() in self._BLOCKED_SUFFIXES:
            raise AgentValidationError(f"Sensitive file type is blocked: {normalized}")
        if self._allowed_prefixes and not any(
            normalized == prefix or normalized.startswith(f"{prefix}/")
            for prefix in self._allowed_prefixes
        ):
            raise AgentValidationError(f"Path is outside the allowed workspace: {normalized}")

        return normalized

    def validate_content(self, path: str, content: str) -> None:
        size = len(content.encode("utf-8"))
        if size > self._max_file_bytes:
            raise AgentValidationError(
                f"Generated file exceeds the size limit: {path} ({size} bytes)."
            )

    def validate_change_count(self, count: int) -> None:
        if count > self._max_change_files:
            raise AgentValidationError(
                f"Agent proposed {count} files; maximum is {self._max_change_files}."
            )

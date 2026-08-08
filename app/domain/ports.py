from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from app.domain.agent import ChangeProposal, ProposedFileChange, WorkspaceFile, WorkspaceStatus
from app.domain.agent_v2 import AuditEvent, KnowledgeItem, WorkflowDefinition
from app.domain.agent_v3 import CiFeedback, SandboxValidationResult


class LanguageModelPort(Protocol):
    async def list_models(self, *, refresh: bool = False) -> list[str]: ...

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str: ...

    async def chat(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str: ...

    def chat_stream(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]: ...


class WorkspacePort(Protocol):
    async def status(self) -> WorkspaceStatus: ...

    async def list_files(self) -> list[str]: ...

    async def read_files(self, paths: list[str]) -> list[WorkspaceFile]: ...

    async def apply_proposal(self, proposal: ChangeProposal) -> ChangeProposal: ...

    async def undo_proposal(self, proposal: ChangeProposal) -> ChangeProposal: ...


class WorkspaceSnapshotPort(Protocol):
    async def materialize_snapshot(self, destination: Path) -> None: ...


class ProposalRepositoryPort(Protocol):
    def save(self, proposal: ChangeProposal) -> None: ...

    def get(self, proposal_id: str) -> ChangeProposal: ...


class KnowledgeRepositoryPort(Protocol):
    def save(self, item: KnowledgeItem) -> None: ...

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeItem]: ...

    def recent(self, *, limit: int = 20) -> list[KnowledgeItem]: ...


class AuditLogPort(Protocol):
    def record(self, event: AuditEvent) -> None: ...

    def recent(self, *, limit: int = 100) -> list[AuditEvent]: ...


class WorkflowCatalogPort(Protocol):
    async def list_workflows(self) -> list[WorkflowDefinition]: ...


class CodeSearchPort(Protocol):
    def rank_paths(
        self,
        query: str,
        paths: list[str],
        *,
        limit: int = 24,
    ) -> list[str]: ...


class ValidationRunnerPort(Protocol):
    async def validate(
        self,
        *,
        changes: list[ProposedFileChange],
        profiles: tuple[str, ...],
        attempt: int,
    ) -> SandboxValidationResult: ...


class CiFeedbackPort(Protocol):
    async def feedback(self, proposal: ChangeProposal) -> CiFeedback: ...

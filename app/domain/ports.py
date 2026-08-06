from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.agent import ChangeProposal, WorkspaceFile, WorkspaceStatus


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


class ProposalRepositoryPort(Protocol):
    def save(self, proposal: ChangeProposal) -> None: ...

    def get(self, proposal_id: str) -> ChangeProposal: ...

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    UNDONE = "undone"


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    path: str
    content: str
    sha: str | None


@dataclass(frozen=True, slots=True)
class AgentPlan:
    summary: str
    steps: tuple[str, ...]
    files_to_read: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposedFileChange:
    path: str
    content: str
    reason: str
    original_sha: str | None = None
    original_content: str | None = None
    diff: str = ""


@dataclass(slots=True)
class ChangeProposal:
    id: str
    repository: str
    base_branch: str
    task: str
    summary: str
    plan: AgentPlan
    changes: tuple[ProposedFileChange, ...]
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    branch_name: str | None = None
    pull_request_url: str | None = None
    pull_request_number: int | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    configured: bool
    repository: str | None
    branch: str | None
    write_enabled: bool
    mode: str

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class RunStatus(StrEnum):
    RUNNING = "running"
    PAUSE_REQUESTED = "pause-requested"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel-requested"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting-approval"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStage(StrEnum):
    CREATED = "created"
    DISCOVERY_READY = "discovery-ready"
    PLAN_READY = "plan-ready"
    REVIEW_READY = "review-ready"
    VALIDATION_READY = "validation-ready"
    SANDBOX_READY = "sandbox-ready"
    WAITING_APPROVAL = "waiting-approval"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    requested_model: str | None
    selected_model: str
    mode: str
    tier: str
    reason: str


@dataclass(frozen=True, slots=True)
class ContextReport:
    original_chars: int
    prepared_chars: int
    estimated_tokens: int
    history_messages: int
    knowledge_items: int
    file_count: int
    dropped_paths: tuple[str, ...] = ()
    compacted: bool = False


@dataclass(frozen=True, slots=True)
class RunBudget:
    token_limit: int
    estimated_tokens_used: int = 0
    cost_limit_usd: float = 0.0
    estimated_cost_usd: float | None = None
    cost_tracking: bool = False

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.token_limit - self.estimated_tokens_used)


@dataclass(slots=True)
class AgentRun:
    id: str
    task: str
    requested_model: str | None
    selected_model: str
    base_branch: str
    history: tuple[dict[str, str], ...] = ()
    status: RunStatus = RunStatus.RUNNING
    stage: RunStage = RunStage.CREATED
    checkpoint: dict[str, object] = field(default_factory=dict)
    parent_proposal_id: str | None = None
    proposal_id: str | None = None
    budget: RunBudget = field(default_factory=lambda: RunBudget(token_limit=60_000))
    route: ModelRoute | None = None
    context_report: ContextReport | None = None
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

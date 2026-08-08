from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class AgentRole(StrEnum):
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    id: str
    title: str
    summary: str
    tags: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    source: str = "agent"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class ReviewResult:
    approved: bool
    score: int
    findings: tuple[str, ...] = ()
    required_changes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    checks: tuple[str, ...]
    workflow_profiles: tuple[str, ...] = ()
    browser_required: bool = False


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    reasons: tuple[str, ...] = ()
    blocked: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    name: str
    description: str
    safe_to_auto_run: bool
    steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    run_id: str
    event_type: str
    message: str
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

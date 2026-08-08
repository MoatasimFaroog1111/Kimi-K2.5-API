from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class ValidationCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class SemanticCodeHit:
    path: str
    score: int
    rationale: str
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationCheckResult:
    name: str
    status: ValidationCheckStatus
    command: tuple[str, ...] = ()
    output: str = ""
    return_code: int | None = None
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class SandboxValidationResult:
    passed: bool
    attempt: int
    checks: tuple[ValidationCheckResult, ...]
    repairable: bool = True

    @property
    def failed_checks(self) -> tuple[ValidationCheckResult, ...]:
        return tuple(
            check for check in self.checks
            if check.status is ValidationCheckStatus.FAILED
        )


@dataclass(frozen=True, slots=True)
class CiJobFeedback:
    name: str
    status: str
    conclusion: str | None
    url: str | None = None
    failed_steps: tuple[str, ...] = ()
    log_excerpt: str = ""


@dataclass(frozen=True, slots=True)
class CiFeedback:
    status: str
    conclusion: str | None
    jobs: tuple[CiJobFeedback, ...] = ()
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

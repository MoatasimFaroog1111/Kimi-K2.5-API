from app.domain.agent import ProposedFileChange
from app.domain.agent_v3 import SandboxValidationResult, ValidationCheckStatus
from app.domain.ports import ValidationRunnerPort


class PreApprovalValidationService:
    def __init__(self, runner: ValidationRunnerPort) -> None:
        self._runner = runner

    async def validate(
        self,
        *,
        changes: list[ProposedFileChange],
        profiles: tuple[str, ...],
        attempt: int,
        base_ref: str | None = None,
    ) -> SandboxValidationResult:
        return await self._runner.validate(
            changes=changes,
            profiles=profiles,
            attempt=attempt,
            base_ref=base_ref,
        )

    @staticmethod
    def repair_feedback(result: SandboxValidationResult) -> tuple[str, ...]:
        feedback: list[str] = []
        for check in result.checks:
            if check.status is not ValidationCheckStatus.FAILED:
                continue
            excerpt = check.output[-4000:].strip()
            feedback.append(
                f"Pre-approval validation failed: {check.name}. "
                f"Fix the root cause shown in this output:\n{excerpt}"
            )
        return tuple(feedback)

    @staticmethod
    def serialize(result: SandboxValidationResult) -> dict[str, object]:
        return {
            "passed": result.passed,
            "attempt": result.attempt,
            "repairable": result.repairable,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "command": list(check.command),
                    "output": check.output,
                    "return_code": check.return_code,
                    "duration_ms": check.duration_ms,
                }
                for check in result.checks
            ],
        }

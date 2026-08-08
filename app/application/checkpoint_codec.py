from app.domain.agent import AgentPlan, ProposedFileChange
from app.domain.agent_v2 import ReviewResult, RiskAssessment, RiskLevel, ValidationPlan
from app.domain.agent_v3 import (
    SandboxValidationResult,
    SemanticCodeHit,
    ValidationCheckResult,
    ValidationCheckStatus,
)


class AgentCheckpointCodec:
    @staticmethod
    def semantic_hits(items: list[SemanticCodeHit]) -> list[dict[str, object]]:
        return [
            {
                "path": item.path,
                "score": item.score,
                "rationale": item.rationale,
                "symbols": list(item.symbols),
            }
            for item in items
        ]

    @staticmethod
    def decode_semantic(items: object) -> list[SemanticCodeHit]:
        if not isinstance(items, list):
            return []
        result: list[SemanticCodeHit] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            result.append(
                SemanticCodeHit(
                    path=str(item.get("path") or ""),
                    score=int(item.get("score") or 0),
                    rationale=str(item.get("rationale") or ""),
                    symbols=tuple(item.get("symbols") or []),
                )
            )
        return result

    @staticmethod
    def plan(plan: AgentPlan) -> dict[str, object]:
        return {
            "summary": plan.summary,
            "steps": list(plan.steps),
            "files_to_read": list(plan.files_to_read),
        }

    @staticmethod
    def decode_plan(payload: object) -> AgentPlan:
        data = payload if isinstance(payload, dict) else {}
        return AgentPlan(
            summary=str(data.get("summary") or ""),
            steps=tuple(data.get("steps") or []),
            files_to_read=tuple(data.get("files_to_read") or []),
        )

    @staticmethod
    def changes(changes: list[ProposedFileChange]) -> list[dict[str, object]]:
        return [
            {
                "path": change.path,
                "content": change.content,
                "reason": change.reason,
                "original_sha": change.original_sha,
                "original_content": change.original_content,
                "diff": change.diff,
            }
            for change in changes
        ]

    @staticmethod
    def decode_changes(payload: object) -> list[ProposedFileChange]:
        if not isinstance(payload, list):
            return []
        return [
            ProposedFileChange(
                path=str(item.get("path") or ""),
                content=str(item.get("content") or ""),
                reason=str(item.get("reason") or ""),
                original_sha=item.get("original_sha"),
                original_content=item.get("original_content"),
                diff=str(item.get("diff") or ""),
            )
            for item in payload
            if isinstance(item, dict)
        ]

    @staticmethod
    def risk(risk: RiskAssessment) -> dict[str, object]:
        return {
            "level": risk.level.value,
            "reasons": list(risk.reasons),
            "blocked": risk.blocked,
        }

    @staticmethod
    def decode_risk(payload: object) -> RiskAssessment:
        data = payload if isinstance(payload, dict) else {}
        try:
            level = RiskLevel(str(data.get("level") or RiskLevel.LOW.value))
        except ValueError:
            level = RiskLevel.LOW
        return RiskAssessment(
            level=level,
            reasons=tuple(data.get("reasons") or []),
            blocked=bool(data.get("blocked")),
        )

    @staticmethod
    def review(review: ReviewResult) -> dict[str, object]:
        return {
            "approved": review.approved,
            "score": review.score,
            "findings": list(review.findings),
            "required_changes": list(review.required_changes),
        }

    @staticmethod
    def decode_review(payload: object) -> ReviewResult:
        data = payload if isinstance(payload, dict) else {}
        return ReviewResult(
            approved=bool(data.get("approved")),
            score=int(data.get("score") or 0),
            findings=tuple(data.get("findings") or []),
            required_changes=tuple(data.get("required_changes") or []),
        )

    @staticmethod
    def validation(validation: ValidationPlan) -> dict[str, object]:
        return {
            "checks": list(validation.checks),
            "workflow_profiles": list(validation.workflow_profiles),
            "browser_required": validation.browser_required,
        }

    @staticmethod
    def decode_validation(payload: object) -> ValidationPlan:
        data = payload if isinstance(payload, dict) else {}
        return ValidationPlan(
            checks=tuple(data.get("checks") or []),
            workflow_profiles=tuple(data.get("workflow_profiles") or []),
            browser_required=bool(data.get("browser_required")),
        )

    @staticmethod
    def sandbox(result: SandboxValidationResult) -> dict[str, object]:
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

    @staticmethod
    def decode_sandbox(payload: object) -> SandboxValidationResult:
        data = payload if isinstance(payload, dict) else {}
        checks: list[ValidationCheckResult] = []
        for item in data.get("checks") or []:
            if not isinstance(item, dict):
                continue
            try:
                status = ValidationCheckStatus(str(item.get("status") or "skipped"))
            except ValueError:
                status = ValidationCheckStatus.SKIPPED
            checks.append(
                ValidationCheckResult(
                    name=str(item.get("name") or "check"),
                    status=status,
                    command=tuple(item.get("command") or []),
                    output=str(item.get("output") or ""),
                    return_code=item.get("return_code"),
                    duration_ms=int(item.get("duration_ms") or 0),
                )
            )
        return SandboxValidationResult(
            passed=bool(data.get("passed")),
            attempt=int(data.get("attempt") or 1),
            checks=tuple(checks),
            repairable=bool(data.get("repairable", True)),
        )

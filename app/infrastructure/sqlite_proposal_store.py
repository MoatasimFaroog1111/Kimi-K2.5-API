import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from app.core.exceptions import ProposalNotFoundError
from app.domain.agent import (
    AgentPlan,
    ChangeProposal,
    ProposalStatus,
    ProposedFileChange,
)
from app.domain.agent_v2 import ReviewResult, RiskAssessment, RiskLevel, ValidationPlan
from app.domain.agent_v3 import (
    CiFeedback,
    CiJobFeedback,
    SandboxValidationResult,
    ValidationCheckResult,
    ValidationCheckStatus,
)


class SQLiteProposalStore:
    def __init__(self, database_path: str, ttl_seconds: int) -> None:
        self._path = database_path
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = RLock()
        self._prepare_parent()
        self._initialize()

    def save(self, proposal: ChangeProposal) -> None:
        payload = json.dumps(self._serialize(proposal), ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO proposals (id, payload_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (proposal.id, payload, proposal.created_at.isoformat()),
            )
        self._remove_expired()

    def get(self, proposal_id: str) -> ChangeProposal:
        self._remove_expired()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise ProposalNotFoundError("Proposal was not found or has expired.")
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError as exc:
            raise ProposalNotFoundError("Stored proposal is invalid.") from exc
        return self._deserialize(payload)

    def recent(self, *, limit: int = 50) -> list[ChangeProposal]:
        self._remove_expired()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM proposals ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        proposals: list[ChangeProposal] = []
        for row in rows:
            try:
                proposals.append(self._deserialize(json.loads(row[0])))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return proposals

    def _remove_expired(self) -> None:
        cutoff = (datetime.now(timezone.utc) - self._ttl).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM proposals WHERE created_at < ?", (cutoff,))

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _prepare_parent(self) -> None:
        if self._path == ":memory:":
            return
        Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _serialize(proposal: ChangeProposal) -> dict[str, object]:
        return {
            "id": proposal.id,
            "repository": proposal.repository,
            "base_branch": proposal.base_branch,
            "task": proposal.task,
            "summary": proposal.summary,
            "status": proposal.status.value,
            "created_at": proposal.created_at.isoformat(),
            "branch_name": proposal.branch_name,
            "pull_request_url": proposal.pull_request_url,
            "pull_request_number": proposal.pull_request_number,
            "run_id": proposal.run_id,
            "knowledge_ids": list(proposal.knowledge_ids),
            "approved_paths": list(proposal.approved_paths),
            "applied_paths": list(proposal.applied_paths),
            "parent_proposal_id": proposal.parent_proposal_id,
            "plan": {
                "summary": proposal.plan.summary,
                "steps": list(proposal.plan.steps),
                "files_to_read": list(proposal.plan.files_to_read),
            },
            "changes": [
                {
                    "path": change.path,
                    "content": change.content,
                    "reason": change.reason,
                    "original_sha": change.original_sha,
                    "original_content": change.original_content,
                    "diff": change.diff,
                }
                for change in proposal.changes
            ],
            "review": (
                {
                    "approved": proposal.review.approved,
                    "score": proposal.review.score,
                    "findings": list(proposal.review.findings),
                    "required_changes": list(proposal.review.required_changes),
                }
                if proposal.review else None
            ),
            "validation": (
                {
                    "checks": list(proposal.validation.checks),
                    "workflow_profiles": list(proposal.validation.workflow_profiles),
                    "browser_required": proposal.validation.browser_required,
                }
                if proposal.validation else None
            ),
            "risk": (
                {
                    "level": proposal.risk.level.value,
                    "reasons": list(proposal.risk.reasons),
                    "blocked": proposal.risk.blocked,
                }
                if proposal.risk else None
            ),
            "sandbox_validation": (
                {
                    "passed": proposal.sandbox_validation.passed,
                    "attempt": proposal.sandbox_validation.attempt,
                    "repairable": proposal.sandbox_validation.repairable,
                    "checks": [
                        {
                            "name": check.name,
                            "status": check.status.value,
                            "command": list(check.command),
                            "output": check.output,
                            "return_code": check.return_code,
                            "duration_ms": check.duration_ms,
                        }
                        for check in proposal.sandbox_validation.checks
                    ],
                }
                if proposal.sandbox_validation else None
            ),
            "ci_feedback": (
                {
                    "status": proposal.ci_feedback.status,
                    "conclusion": proposal.ci_feedback.conclusion,
                    "checked_at": proposal.ci_feedback.checked_at.isoformat(),
                    "jobs": [
                        {
                            "name": job.name,
                            "status": job.status,
                            "conclusion": job.conclusion,
                            "url": job.url,
                            "failed_steps": list(job.failed_steps),
                            "log_excerpt": job.log_excerpt,
                        }
                        for job in proposal.ci_feedback.jobs
                    ],
                }
                if proposal.ci_feedback else None
            ),
        }

    @staticmethod
    def _deserialize(payload: dict) -> ChangeProposal:
        plan_payload = payload.get("plan") or {}
        plan = AgentPlan(
            summary=str(plan_payload.get("summary") or ""),
            steps=tuple(plan_payload.get("steps") or []),
            files_to_read=tuple(plan_payload.get("files_to_read") or []),
        )
        changes = tuple(
            ProposedFileChange(
                path=str(item.get("path") or ""),
                content=str(item.get("content") or ""),
                reason=str(item.get("reason") or ""),
                original_sha=item.get("original_sha"),
                original_content=item.get("original_content"),
                diff=str(item.get("diff") or ""),
            )
            for item in payload.get("changes") or []
            if isinstance(item, dict)
        )

        review_payload = payload.get("review")
        review = None
        if isinstance(review_payload, dict):
            review = ReviewResult(
                approved=bool(review_payload.get("approved")),
                score=int(review_payload.get("score") or 0),
                findings=tuple(review_payload.get("findings") or []),
                required_changes=tuple(review_payload.get("required_changes") or []),
            )

        validation_payload = payload.get("validation")
        validation = None
        if isinstance(validation_payload, dict):
            validation = ValidationPlan(
                checks=tuple(validation_payload.get("checks") or []),
                workflow_profiles=tuple(validation_payload.get("workflow_profiles") or []),
                browser_required=bool(validation_payload.get("browser_required")),
            )

        risk_payload = payload.get("risk")
        risk = None
        if isinstance(risk_payload, dict):
            raw_level = str(risk_payload.get("level") or RiskLevel.LOW.value)
            try:
                level = RiskLevel(raw_level)
            except ValueError:
                level = RiskLevel.LOW
            risk = RiskAssessment(
                level=level,
                reasons=tuple(risk_payload.get("reasons") or []),
                blocked=bool(risk_payload.get("blocked")),
            )

        sandbox_payload = payload.get("sandbox_validation")
        sandbox = None
        if isinstance(sandbox_payload, dict):
            sandbox_checks: list[ValidationCheckResult] = []
            for item in sandbox_payload.get("checks") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    status_value = ValidationCheckStatus(str(item.get("status") or "skipped"))
                except ValueError:
                    status_value = ValidationCheckStatus.SKIPPED
                sandbox_checks.append(
                    ValidationCheckResult(
                        name=str(item.get("name") or "check"),
                        status=status_value,
                        command=tuple(item.get("command") or []),
                        output=str(item.get("output") or ""),
                        return_code=item.get("return_code"),
                        duration_ms=int(item.get("duration_ms") or 0),
                    )
                )
            sandbox = SandboxValidationResult(
                passed=bool(sandbox_payload.get("passed")),
                attempt=int(sandbox_payload.get("attempt") or 1),
                checks=tuple(sandbox_checks),
                repairable=bool(sandbox_payload.get("repairable", True)),
            )

        ci_payload = payload.get("ci_feedback")
        ci_feedback = None
        if isinstance(ci_payload, dict):
            jobs = tuple(
                CiJobFeedback(
                    name=str(item.get("name") or "job"),
                    status=str(item.get("status") or "queued"),
                    conclusion=item.get("conclusion"),
                    url=item.get("url"),
                    failed_steps=tuple(item.get("failed_steps") or []),
                    log_excerpt=str(item.get("log_excerpt") or ""),
                )
                for item in ci_payload.get("jobs") or []
                if isinstance(item, dict)
            )
            checked_raw = str(ci_payload.get("checked_at") or "")
            try:
                checked_at = datetime.fromisoformat(checked_raw)
            except ValueError:
                checked_at = datetime.now(timezone.utc)
            ci_feedback = CiFeedback(
                status=str(ci_payload.get("status") or "queued"),
                conclusion=ci_payload.get("conclusion"),
                jobs=jobs,
                checked_at=checked_at,
            )

        created_raw = str(payload.get("created_at") or "")
        try:
            created_at = datetime.fromisoformat(created_raw)
        except ValueError:
            created_at = datetime.now(timezone.utc)
        try:
            status = ProposalStatus(str(payload.get("status") or "pending"))
        except ValueError:
            status = ProposalStatus.PENDING

        return ChangeProposal(
            id=str(payload.get("id") or ""),
            repository=str(payload.get("repository") or ""),
            base_branch=str(payload.get("base_branch") or "main"),
            task=str(payload.get("task") or ""),
            summary=str(payload.get("summary") or ""),
            plan=plan,
            changes=changes,
            status=status,
            created_at=created_at,
            branch_name=payload.get("branch_name"),
            pull_request_url=payload.get("pull_request_url"),
            pull_request_number=payload.get("pull_request_number"),
            run_id=payload.get("run_id"),
            review=review,
            validation=validation,
            risk=risk,
            knowledge_ids=tuple(payload.get("knowledge_ids") or []),
            sandbox_validation=sandbox,
            ci_feedback=ci_feedback,
            approved_paths=tuple(payload.get("approved_paths") or []),
            applied_paths=tuple(payload.get("applied_paths") or []),
            parent_proposal_id=payload.get("parent_proposal_id"),
        )

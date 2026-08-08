import re
from pathlib import PurePosixPath

from app.domain.agent import ProposedFileChange
from app.domain.agent_v2 import RiskAssessment, RiskLevel


class AgentSecurityService:
    _SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)\s*[=:]\s*['\"][^'\"]{16,}['\"]"),
    )
    _HIGH_RISK_PREFIXES = (
        ".github/workflows/",
        "app/core/",
        "app/security/",
        "app/middleware/",
        "infra/",
        "infrastructure/",
        "deploy/",
    )
    _HIGH_RISK_NAMES = {
        "dockerfile",
        "railway.json",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
    }

    def assess(
        self,
        *,
        task: str,
        changes: list[ProposedFileChange],
    ) -> RiskAssessment:
        reasons: list[str] = []
        blocked = False

        for change in changes:
            path = change.path.casefold()
            name = PurePosixPath(path).name
            if path.startswith(self._HIGH_RISK_PREFIXES) or name in self._HIGH_RISK_NAMES:
                reasons.append(f"Sensitive execution/configuration surface: {change.path}")
            for pattern in self._SECRET_PATTERNS:
                if pattern.search(change.content):
                    reasons.append(f"Potential embedded secret detected in {change.path}")
                    blocked = True
                    break

        normalized_task = task.casefold()
        suspicious_pairs = (
            (".env", "send"),
            (".env", "upload"),
            ("secret", "exfiltrate"),
            ("token", "exfiltrate"),
            ("private key", "send"),
            ("ignore previous", "secret"),
        )
        if any(left in normalized_task and right in normalized_task for left, right in suspicious_pairs):
            reasons.append("Task contains a potential prompt-injection or secret-exfiltration pattern.")
            blocked = True

        if blocked:
            level = RiskLevel.BLOCKED
        elif reasons or len(changes) >= 5:
            level = RiskLevel.HIGH
        elif len(changes) >= 3:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        if not reasons:
            reasons.append("No elevated-risk patterns detected by deterministic policy.")

        return RiskAssessment(
            level=level,
            reasons=tuple(dict.fromkeys(reasons)),
            blocked=blocked,
        )

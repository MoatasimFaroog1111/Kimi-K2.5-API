import asyncio
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from app.config import Settings
from app.core.exceptions import WorkspaceError
from app.domain.agent import ProposedFileChange
from app.domain.agent_v3 import (
    SandboxValidationResult,
    ValidationCheckResult,
    ValidationCheckStatus,
)
from app.domain.ports import WorkspaceSnapshotPort


class IsolatedValidationRunner:
    def __init__(
        self,
        snapshot: WorkspaceSnapshotPort,
        config: Settings,
    ) -> None:
        self._snapshot = snapshot
        self._config = config

    async def validate(
        self,
        *,
        changes: list[ProposedFileChange],
        profiles: tuple[str, ...],
        attempt: int,
    ) -> SandboxValidationResult:
        with TemporaryDirectory(prefix="kimi-agent-v3-") as temp_dir:
            root = Path(temp_dir).resolve()
            await self._snapshot.materialize_snapshot(root)
            self._apply_changes(root, changes)
            checks: list[ValidationCheckResult] = []

            selected = set(profiles)
            changed_paths = [change.path for change in changes]
            python_relevant = any(path.endswith(".py") for path in changed_paths)
            frontend_relevant = any(
                path.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"))
                for path in changed_paths
            )

            if python_relevant or {"python-tests", "repository-smoke"} & selected:
                checks.append(
                    await self._run(
                        "python-compile",
                        (sys.executable, "-m", "compileall", "-q", "app", "tests"),
                        cwd=root,
                    )
                )
                if (root / "tests").exists():
                    checks.append(
                        await self._run(
                            "python-unit-tests",
                            (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
                            cwd=root,
                        )
                    )

            if frontend_relevant or "frontend-check" in selected:
                node = shutil.which("node")
                if not node:
                    checks.append(
                        ValidationCheckResult(
                            name="javascript-syntax",
                            status=ValidationCheckStatus.SKIPPED,
                            output="Node.js is not available in the Railway validation process; GitHub CI will run this check.",
                        )
                    )
                else:
                    js_files = sorted(
                        path for path in root.rglob("*.js")
                        if "node_modules" not in path.parts
                    )[:200]
                    if not js_files:
                        checks.append(
                            ValidationCheckResult(
                                name="javascript-syntax",
                                status=ValidationCheckStatus.SKIPPED,
                                output="No JavaScript files were found in the snapshot.",
                            )
                        )
                    for path in js_files:
                        checks.append(
                            await self._run(
                                f"node-check:{path.relative_to(root)}",
                                (node, "--check", str(path)),
                                cwd=root,
                            )
                        )
                        if checks[-1].status is ValidationCheckStatus.FAILED:
                            break

            if "security-review" in selected:
                checks.append(
                    ValidationCheckResult(
                        name="deterministic-security-gate",
                        status=ValidationCheckStatus.PASSED,
                        output="Deterministic secret and sensitive-surface validation already passed before sandbox execution.",
                    )
                )

            if "browser-smoke" in selected:
                checks.append(
                    ValidationCheckResult(
                        name="browser-smoke",
                        status=ValidationCheckStatus.SKIPPED,
                        output="Real Chromium verification is intentionally deferred to isolated GitHub Actions after Pull Request creation.",
                    )
                )

            if not checks:
                checks.append(
                    ValidationCheckResult(
                        name="repository-snapshot",
                        status=ValidationCheckStatus.PASSED,
                        output="The proposed files were applied successfully to an isolated repository snapshot.",
                    )
                )

            passed = not any(
                check.status is ValidationCheckStatus.FAILED for check in checks
            )
            return SandboxValidationResult(
                passed=passed,
                attempt=attempt,
                checks=tuple(checks),
                repairable=True,
            )

    @staticmethod
    def _apply_changes(root: Path, changes: list[ProposedFileChange]) -> None:
        for change in changes:
            target = (root / change.path).resolve()
            if root not in target.parents:
                raise WorkspaceError("Proposed change escaped the isolated workspace.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    async def _run(
        self,
        name: str,
        command: tuple[str, ...],
        *,
        cwd: Path,
    ) -> ValidationCheckResult:
        started = monotonic()
        environment = os.environ.copy()
        environment.update(
            {
                "KIMI_API_KEY": "test-key",
                "GATEWAY_API_KEY": "test-gateway",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._config.agent_validation_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                duration = int((monotonic() - started) * 1000)
                return ValidationCheckResult(
                    name=name,
                    status=ValidationCheckStatus.FAILED,
                    command=command,
                    output=f"Validation timed out after {self._config.agent_validation_timeout_seconds}s.",
                    return_code=None,
                    duration_ms=duration,
                )
        except OSError as exc:
            duration = int((monotonic() - started) * 1000)
            return ValidationCheckResult(
                name=name,
                status=ValidationCheckStatus.FAILED,
                command=command,
                output=f"Could not start validation process: {exc}",
                return_code=None,
                duration_ms=duration,
            )

        duration = int((monotonic() - started) * 1000)
        output = stdout.decode("utf-8", errors="replace")
        output = output[-self._config.agent_validation_log_chars :]
        return ValidationCheckResult(
            name=name,
            status=(
                ValidationCheckStatus.PASSED
                if process.returncode == 0
                else ValidationCheckStatus.FAILED
            ),
            command=command,
            output=output,
            return_code=process.returncode,
            duration_ms=duration,
        )

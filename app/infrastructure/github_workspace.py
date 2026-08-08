import base64
import io
import zipfile
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import Settings
from app.core.exceptions import AgentConfigurationError, WorkspaceError
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ChangeProposal, ProposalStatus, WorkspaceFile, WorkspaceStatus
from app.domain.agent_v3 import CiFeedback, CiJobFeedback


class GitHubWorkspace:
    _API_BASE = "https://api.github.com"

    def __init__(self, config: Settings, policy: WorkspacePolicy) -> None:
        self._config = config
        self._policy = policy
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Kimi-Coding-Workspace-Agent",
        }
        if config.agent_github_token:
            headers["Authorization"] = f"Bearer {config.agent_github_token}"
        self._client = httpx.AsyncClient(
            base_url=self._API_BASE,
            headers=headers,
            timeout=45.0,
            follow_redirects=True,
        )

    async def status(self) -> WorkspaceStatus:
        repository = self._config.agent_github_repository.strip() or None
        if not repository:
            return WorkspaceStatus(
                configured=False,
                repository=None,
                branch=None,
                write_enabled=False,
                mode="not-configured",
            )

        await self._request("GET", f"/repos/{repository}")
        write_enabled = bool(
            self._config.agent_write_enabled
            and self._config.agent_github_token.strip()
        )
        return WorkspaceStatus(
            configured=True,
            repository=repository,
            branch=self._config.agent_github_branch,
            write_enabled=write_enabled,
            mode="pull-request" if write_enabled else "read-only",
        )

    async def list_files(self) -> list[str]:
        repository = self._require_repository()
        branch = quote(self._config.agent_github_branch, safe="")
        payload = await self._request(
            "GET",
            f"/repos/{repository}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        paths: list[str] = []
        for item in payload.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item.get("path")
            size = int(item.get("size") or 0)
            if not isinstance(path, str) or size > self._config.agent_max_file_bytes:
                continue
            try:
                paths.append(self._policy.validate_path(path))
            except Exception:
                continue
            if len(paths) >= self._config.agent_max_tree_files:
                break
        return paths

    async def read_files(self, paths: list[str]) -> list[WorkspaceFile]:
        return await self._read_files_at_ref(paths, self._config.agent_github_branch)

    async def materialize_snapshot(self, destination: Path) -> None:
        repository = self._require_repository()
        branch = quote(self._config.agent_github_branch, safe="")
        try:
            response = await self._client.get(f"/repos/{repository}/zipball/{branch}")
        except httpx.HTTPError as exc:
            raise WorkspaceError("Could not download the GitHub workspace snapshot.") from exc
        if response.status_code >= 400:
            raise WorkspaceError(
                f"GitHub snapshot download returned {response.status_code}."
            )
        archive_bytes = response.content
        if len(archive_bytes) > self._config.agent_snapshot_max_download_bytes:
            raise WorkspaceError("Repository snapshot exceeds the configured download limit.")

        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()
        extracted_bytes = 0
        extracted_files = 0
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as exc:
            raise WorkspaceError("GitHub returned an invalid repository snapshot.") from exc

        with archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                parts = Path(member.filename).parts
                if len(parts) < 2:
                    continue
                relative = "/".join(parts[1:])
                try:
                    safe_path = self._policy.validate_path(relative)
                except Exception:
                    continue
                if member.file_size > self._config.agent_max_file_bytes:
                    continue
                extracted_bytes += member.file_size
                if extracted_bytes > self._config.agent_snapshot_max_download_bytes * 4:
                    raise WorkspaceError("Expanded repository snapshot exceeds the safety limit.")
                target = (root / safe_path).resolve()
                if root not in target.parents:
                    raise WorkspaceError("Unsafe path detected in repository snapshot.")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
                extracted_files += 1
                if extracted_files >= self._config.agent_max_tree_files:
                    break

    async def feedback(self, proposal: ChangeProposal) -> CiFeedback:
        if not proposal.branch_name:
            return CiFeedback(status="not-started", conclusion=None)
        repository = self._require_repository()
        payload = await self._request(
            "GET",
            f"/repos/{repository}/actions/runs",
            params={"branch": proposal.branch_name, "per_page": 20},
        )
        runs = [
            run for run in payload.get("workflow_runs", [])
            if run.get("head_branch") == proposal.branch_name
        ][:6]
        if not runs:
            return CiFeedback(status="queued", conclusion=None)

        jobs: list[CiJobFeedback] = []
        statuses: list[str] = []
        conclusions: list[str | None] = []
        for run in runs:
            statuses.append(str(run.get("status") or "queued"))
            conclusions.append(run.get("conclusion"))
            run_id = run.get("id")
            if not run_id:
                continue
            job_payload = await self._request(
                "GET",
                f"/repos/{repository}/actions/runs/{run_id}/jobs",
                params={"per_page": 100},
            )
            for job in job_payload.get("jobs", [])[:30]:
                failed_steps = tuple(
                    str(step.get("name") or "")
                    for step in job.get("steps", [])
                    if step.get("conclusion") == "failure"
                )
                conclusion = job.get("conclusion")
                log_excerpt = ""
                if conclusion == "failure" and job.get("id"):
                    log_excerpt = await self._job_log_excerpt(repository, int(job["id"]))
                jobs.append(
                    CiJobFeedback(
                        name=str(job.get("name") or "job"),
                        status=str(job.get("status") or "queued"),
                        conclusion=conclusion,
                        url=job.get("html_url"),
                        failed_steps=failed_steps,
                        log_excerpt=log_excerpt,
                    )
                )

        if any(status != "completed" for status in statuses):
            return CiFeedback(status="in_progress", conclusion=None, jobs=tuple(jobs))
        failed = any(
            conclusion not in {"success", "neutral", "skipped"}
            for conclusion in conclusions
            if conclusion is not None
        )
        return CiFeedback(
            status="completed",
            conclusion="failure" if failed else "success",
            jobs=tuple(jobs),
        )

    async def apply_proposal(self, proposal: ChangeProposal) -> ChangeProposal:
        status = await self.status()
        if not status.write_enabled:
            raise AgentConfigurationError(
                "Agent write access is disabled. Configure AGENT_GITHUB_TOKEN "
                "and set AGENT_WRITE_ENABLED=true."
            )
        if proposal.status is not ProposalStatus.PENDING:
            raise WorkspaceError("Only pending proposals can be applied.")

        repository = self._require_repository()
        branch_name = f"kimi-agent/{proposal.id}"
        base_ref = await self._request(
            "GET",
            f"/repos/{repository}/git/ref/heads/{quote(proposal.base_branch, safe='/')}",
        )
        base_sha = base_ref.get("object", {}).get("sha")
        if not base_sha:
            raise WorkspaceError("Could not resolve the base branch commit.")

        await self._request(
            "POST",
            f"/repos/{repository}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )

        try:
            for change in proposal.changes:
                path = self._policy.validate_path(change.path)
                self._policy.validate_content(path, change.content)
                payload = {
                    "message": f"Kimi agent: {change.reason[:120]}",
                    "content": base64.b64encode(change.content.encode("utf-8")).decode("ascii"),
                    "branch": branch_name,
                }
                if change.original_sha:
                    payload["sha"] = change.original_sha
                await self._request(
                    "PUT",
                    f"/repos/{repository}/contents/{quote(path, safe='/')}",
                    json=payload,
                )

            pull_request = await self._request(
                "POST",
                f"/repos/{repository}/pulls",
                json={
                    "title": f"Kimi Agent: {proposal.summary[:120]}",
                    "head": branch_name,
                    "base": proposal.base_branch,
                    "body": self._build_pull_request_body(proposal),
                },
            )
        except Exception:
            await self._delete_branch(repository, branch_name, ignore_errors=True)
            raise

        proposal.status = ProposalStatus.APPLIED
        proposal.branch_name = branch_name
        proposal.pull_request_url = pull_request.get("html_url")
        proposal.pull_request_number = pull_request.get("number")
        return proposal

    async def undo_proposal(self, proposal: ChangeProposal) -> ChangeProposal:
        if proposal.status is not ProposalStatus.APPLIED:
            raise WorkspaceError("Only applied proposals can be undone.")
        repository = self._require_repository()
        if proposal.pull_request_number:
            await self._request(
                "PATCH",
                f"/repos/{repository}/pulls/{proposal.pull_request_number}",
                json={"state": "closed"},
            )
        if proposal.branch_name:
            await self._delete_branch(repository, proposal.branch_name, ignore_errors=True)
        proposal.status = ProposalStatus.UNDONE
        return proposal

    async def _read_files_at_ref(self, paths: list[str], ref: str) -> list[WorkspaceFile]:
        repository = self._require_repository()
        files: list[WorkspaceFile] = []
        total_bytes = 0
        for raw_path in paths[: self._config.agent_max_read_files]:
            path = self._policy.validate_path(raw_path)
            encoded_path = quote(path, safe="/")
            payload = await self._request(
                "GET",
                f"/repos/{repository}/contents/{encoded_path}",
                params={"ref": ref},
            )
            if payload.get("type") != "file":
                continue
            encoded = str(payload.get("content") or "").replace("\n", "")
            try:
                content = base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise WorkspaceError(f"Could not decode UTF-8 file: {path}") from exc
            self._policy.validate_content(path, content)
            content_bytes = len(content.encode("utf-8"))
            if total_bytes + content_bytes > self._config.agent_max_context_bytes:
                break
            total_bytes += content_bytes
            files.append(
                WorkspaceFile(
                    path=path,
                    content=content,
                    sha=payload.get("sha"),
                )
            )
        return files

    async def _job_log_excerpt(self, repository: str, job_id: int) -> str:
        try:
            response = await self._client.get(
                f"/repos/{repository}/actions/jobs/{job_id}/logs",
                headers={"Accept": "application/vnd.github+json"},
            )
        except httpx.HTTPError:
            return ""
        if response.status_code >= 400:
            return ""
        text = response.text
        return text[-self._config.agent_ci_log_chars :]

    def _require_repository(self) -> str:
        repository = self._config.agent_github_repository.strip()
        if not repository or "/" not in repository:
            raise AgentConfigurationError(
                "AGENT_GITHUB_REPOSITORY must be configured as owner/repository."
            )
        return repository

    async def _delete_branch(
        self,
        repository: str,
        branch_name: str,
        *,
        ignore_errors: bool,
    ) -> None:
        try:
            await self._request(
                "DELETE",
                f"/repos/{repository}/git/refs/heads/{quote(branch_name, safe='/')}",
            )
        except WorkspaceError:
            if not ignore_errors:
                raise

    async def _request(self, method: str, url: str, **kwargs):
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise WorkspaceError("Could not connect to GitHub.") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("message")
            except ValueError:
                detail = response.text[:300]
            raise WorkspaceError(
                f"GitHub API returned {response.status_code}: {detail or 'Unknown error'}"
            )
        if response.status_code == 204:
            return {}
        return response.json()

    @staticmethod
    def _build_pull_request_body(proposal: ChangeProposal) -> str:
        steps = "\n".join(f"- {step}" for step in proposal.plan.steps)
        files = "\n".join(
            f"- `{change.path}` — {change.reason}" for change in proposal.changes
        )
        return (
            "## Summary\n"
            f"{proposal.summary}\n\n"
            "## Plan\n"
            f"{steps}\n\n"
            "## Files\n"
            f"{files}\n\n"
            "Generated by Kimi Coding Workspace after explicit user approval."
        )

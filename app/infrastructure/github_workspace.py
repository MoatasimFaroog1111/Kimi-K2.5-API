import base64
from urllib.parse import quote

import httpx

from app.config import Settings
from app.core.exceptions import AgentConfigurationError, WorkspaceError
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ChangeProposal, ProposalStatus, WorkspaceFile, WorkspaceStatus


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
        repository = self._require_repository()
        files: list[WorkspaceFile] = []
        total_bytes = 0
        for raw_path in paths[: self._config.agent_max_read_files]:
            path = self._policy.validate_path(raw_path)
            encoded_path = quote(path, safe="/")
            payload = await self._request(
                "GET",
                f"/repos/{repository}/contents/{encoded_path}",
                params={"ref": self._config.agent_github_branch},
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

import json
from collections.abc import AsyncIterator
from difflib import unified_diff
from typing import Any
from uuid import uuid4

from app.application.prompts import (
    AGENT_IMPLEMENTER_SYSTEM_PROMPT,
    AGENT_PLANNER_SYSTEM_PROMPT,
    AGENT_STANDALONE_SYSTEM_PROMPT,
)
from app.config import Settings
from app.core.exceptions import AgentValidationError, ProposalStateError
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import (
    AgentPlan,
    ChangeProposal,
    ProposalStatus,
    ProposedFileChange,
)
from app.domain.ports import (
    LanguageModelPort,
    ProposalRepositoryPort,
    WorkspacePort,
)


class AgentApplicationService:
    def __init__(
        self,
        *,
        model: LanguageModelPort,
        workspace: WorkspacePort,
        proposals: ProposalRepositoryPort,
        policy: WorkspacePolicy,
        config: Settings,
    ) -> None:
        self._model = model
        self._workspace = workspace
        self._proposals = proposals
        self._policy = policy
        self._config = config

    async def status(self) -> dict[str, Any]:
        status = await self._workspace.status()
        return {
            "configured": status.configured,
            "repository": status.repository,
            "branch": status.branch,
            "write_enabled": status.write_enabled,
            "mode": status.mode,
            "approval_required": True,
            "sandbox": "github-pull-request",
        }

    async def stream_task(
        self,
        *,
        task: str,
        model: str,
        history: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        workspace_status = await self._workspace.status()
        yield {
            "type": "status",
            "stage": "workspace",
            "message": (
                f"Connected to {workspace_status.repository}."
                if workspace_status.configured
                else "No repository is connected; running in planning-only mode."
            ),
            "workspace": await self.status(),
        }

        if not workspace_status.configured:
            yield {
                "type": "plan",
                "summary": "Planning-only mode",
                "steps": [
                    "Clarify the requested outcome",
                    "Design SOLID component boundaries",
                    "Identify implementation and validation steps",
                    "Connect a repository before proposing file changes",
                ],
                "files": [],
            }
            response = await self._model.complete(
                system_prompt=AGENT_STANDALONE_SYSTEM_PROMPT,
                user_prompt=self._standalone_prompt(task, history),
                model=model,
                max_tokens=2048,
            )
            yield {"type": "delta", "content": response}
            yield {"type": "done", "model": model, "proposal_id": None}
            return

        yield {
            "type": "status",
            "stage": "discovery",
            "message": "Reading the safe repository tree.",
        }
        tree = await self._workspace.list_files()
        if not tree:
            raise AgentValidationError("The connected repository contains no readable files.")

        planner_raw = await self._model.complete(
            system_prompt=AGENT_PLANNER_SYSTEM_PROMPT,
            user_prompt=self._planner_prompt(task, history, tree),
            model=model,
            max_tokens=2048,
        )
        plan = self._parse_plan(planner_raw, tree)
        yield {
            "type": "plan",
            "summary": plan.summary,
            "steps": list(plan.steps),
            "files": list(plan.files_to_read),
        }

        yield {
            "type": "status",
            "stage": "inspection",
            "message": f"Reading {len(plan.files_to_read)} relevant file(s).",
        }
        files = await self._workspace.read_files(list(plan.files_to_read))

        implementer_raw = await self._model.complete(
            system_prompt=AGENT_IMPLEMENTER_SYSTEM_PROMPT,
            user_prompt=self._implementation_prompt(task, plan, tree, files),
            model=model,
            max_tokens=self._config.agent_max_output_tokens,
        )
        assistant_message, raw_changes = self._parse_implementation(implementer_raw)
        changes = self._validate_changes(raw_changes, tree, files)

        if not changes:
            yield {"type": "delta", "content": assistant_message}
            yield {"type": "done", "model": model, "proposal_id": None}
            return

        proposal = ChangeProposal(
            id=uuid4().hex[:16],
            repository=workspace_status.repository or "",
            base_branch=workspace_status.branch or self._config.agent_github_branch,
            task=task,
            summary=assistant_message or plan.summary,
            plan=plan,
            changes=tuple(changes),
        )
        self._proposals.save(proposal)

        yield {"type": "delta", "content": assistant_message}
        yield {
            "type": "approval_required",
            "proposal": self._serialize_proposal(proposal, workspace_status.write_enabled),
        }
        yield {"type": "done", "model": model, "proposal_id": proposal.id}

    async def approve(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalStateError("Only pending proposals can be approved.")
        try:
            applied = await self._workspace.apply_proposal(proposal)
        except Exception:
            proposal.status = ProposalStatus.PENDING
            self._proposals.save(proposal)
            raise
        self._proposals.save(applied)
        return self._serialize_proposal(applied, can_approve=False)

    def reject(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalStateError("Only pending proposals can be rejected.")
        proposal.status = ProposalStatus.REJECTED
        self._proposals.save(proposal)
        return self._serialize_proposal(proposal, can_approve=False)

    async def undo(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        undone = await self._workspace.undo_proposal(proposal)
        self._proposals.save(undone)
        return self._serialize_proposal(undone, can_approve=False)

    def _parse_plan(self, raw: str, tree: list[str]) -> AgentPlan:
        payload = self._parse_json_object(raw)
        summary = str(payload.get("summary") or "Implementation plan").strip()
        steps = tuple(
            str(step).strip()
            for step in payload.get("steps", [])[:8]
            if str(step).strip()
        )
        selected: list[str] = []
        tree_set = set(tree)
        for raw_path in payload.get("files_to_read", [])[: self._config.agent_max_read_files]:
            path = str(raw_path).strip()
            if path in tree_set and path not in selected:
                selected.append(path)
        if not steps:
            raise AgentValidationError("The agent planner returned no actionable steps.")
        return AgentPlan(summary=summary, steps=steps, files_to_read=tuple(selected))

    def _parse_implementation(self, raw: str) -> tuple[str, list[dict[str, Any]]]:
        payload = self._parse_json_object(raw)
        message = str(payload.get("assistant_message") or "").strip()
        changes = payload.get("changes") or []
        if not isinstance(changes, list):
            raise AgentValidationError("Agent changes must be a list.")
        return message, [item for item in changes if isinstance(item, dict)]

    def _validate_changes(
        self,
        raw_changes: list[dict[str, Any]],
        tree: list[str],
        files,
    ) -> list[ProposedFileChange]:
        self._policy.validate_change_count(len(raw_changes))
        existing = {file.path: file for file in files}
        tree_set = set(tree)
        seen: set[str] = set()
        validated: list[ProposedFileChange] = []

        for item in raw_changes:
            path = self._policy.validate_path(str(item.get("path") or ""))
            if path in seen:
                raise AgentValidationError(f"Duplicate proposed file: {path}")
            if path in tree_set and path not in existing:
                raise AgentValidationError(
                    f"Agent attempted to modify an unread existing file: {path}"
                )
            content = item.get("content")
            if not isinstance(content, str):
                raise AgentValidationError(f"Complete content is required for {path}.")
            self._policy.validate_content(path, content)
            reason = str(item.get("reason") or "Agent implementation").strip()
            original = existing.get(path)
            validated.append(
                ProposedFileChange(
                    path=path,
                    content=content,
                    reason=reason,
                    original_sha=original.sha if original else None,
                    original_content=original.content if original else None,
                    diff=self._build_diff(path, original.content if original else "", content),
                )
            )
            seen.add(path)
        return validated

    @staticmethod
    def _parse_json_object(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise AgentValidationError("Agent returned invalid structured output.")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AgentValidationError("Agent returned invalid JSON output.") from exc
        if not isinstance(payload, dict):
            raise AgentValidationError("Agent output must be a JSON object.")
        return payload

    @staticmethod
    def _build_diff(path: str, before: str, after: str) -> str:
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return diff[:30_000]

    @staticmethod
    def _serialize_proposal(
        proposal: ChangeProposal,
        can_approve: bool,
    ) -> dict[str, Any]:
        return {
            "id": proposal.id,
            "repository": proposal.repository,
            "base_branch": proposal.base_branch,
            "summary": proposal.summary,
            "status": proposal.status.value,
            "can_approve": can_approve and proposal.status is ProposalStatus.PENDING,
            "branch_name": proposal.branch_name,
            "pull_request_url": proposal.pull_request_url,
            "changes": [
                {
                    "path": change.path,
                    "reason": change.reason,
                    "diff": change.diff,
                }
                for change in proposal.changes
            ],
        }

    @staticmethod
    def _planner_prompt(
        task: str,
        history: list[dict[str, str]],
        tree: list[str],
    ) -> str:
        return json.dumps(
            {
                "task": task,
                "recent_conversation": history[-8:],
                "repository_tree": tree,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _implementation_prompt(task: str, plan: AgentPlan, tree: list[str], files) -> str:
        return json.dumps(
            {
                "task": task,
                "plan": {
                    "summary": plan.summary,
                    "steps": list(plan.steps),
                },
                "repository_tree": tree,
                "files": [
                    {"path": file.path, "content": file.content}
                    for file in files
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _standalone_prompt(task: str, history: list[dict[str, str]]) -> str:
        return json.dumps(
            {"task": task, "recent_conversation": history[-8:]},
            ensure_ascii=False,
        )

import json
import unittest

from app.application.agent_service import AgentApplicationService
from app.config import Settings
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ProposalStatus, WorkspaceFile, WorkspaceStatus
from app.infrastructure.proposal_store import InMemoryProposalStore


class FakeModel:
    def __init__(self) -> None:
        self.responses = [
            json.dumps(
                {
                    "summary": "Add a health helper",
                    "steps": ["Inspect service", "Add helper", "Verify behavior"],
                    "files_to_read": ["app/service.py"],
                }
            ),
            json.dumps(
                {
                    "assistant_message": "Prepared a focused helper change.",
                    "changes": [
                        {
                            "path": "app/service.py",
                            "reason": "Expose explicit health state",
                            "content": "def health():\n    return {'status': 'ok'}\n",
                        }
                    ],
                }
            ),
        ]

    async def complete(self, **_kwargs):
        return self.responses.pop(0)


class FakeWorkspace:
    def __init__(self) -> None:
        self.applied = False

    async def status(self):
        return WorkspaceStatus(
            configured=True,
            repository="owner/repo",
            branch="main",
            write_enabled=True,
            mode="pull-request",
        )

    async def list_files(self):
        return ["app/service.py", "tests/test_service.py"]

    async def read_files(self, _paths):
        return [
            WorkspaceFile(
                path="app/service.py",
                content="def health():\n    return {}\n",
                sha="abc123",
            )
        ]

    async def apply_proposal(self, proposal):
        self.applied = True
        proposal.status = ProposalStatus.APPLIED
        proposal.branch_name = f"kimi-agent/{proposal.id}"
        proposal.pull_request_url = "https://github.com/owner/repo/pull/1"
        proposal.pull_request_number = 1
        return proposal

    async def undo_proposal(self, proposal):
        proposal.status = ProposalStatus.UNDONE
        return proposal


class AgentApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_approval_proposal_and_applies_it(self):
        config = Settings(
            kimi_api_key="test",
            agent_github_repository="owner/repo",
            agent_write_enabled=True,
            agent_github_token="token",
        )
        policy = WorkspacePolicy(
            allowed_prefixes=(),
            max_file_bytes=120_000,
            max_change_files=6,
        )
        store = InMemoryProposalStore(ttl_seconds=3600)
        workspace = FakeWorkspace()
        service = AgentApplicationService(
            model=FakeModel(),
            workspace=workspace,
            proposals=store,
            policy=policy,
            config=config,
        )

        events = [
            event
            async for event in service.stream_task(
                task="Add health helper",
                model="kimi-k2.7-code",
                history=[],
            )
        ]

        approval = next(event for event in events if event["type"] == "approval_required")
        proposal_id = approval["proposal"]["id"]
        self.assertTrue(approval["proposal"]["can_approve"])
        self.assertIn("app/service.py", approval["proposal"]["changes"][0]["path"])

        applied = await service.approve(proposal_id)
        self.assertTrue(workspace.applied)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["pull_request_url"], "https://github.com/owner/repo/pull/1")

    def test_blocks_sensitive_paths(self):
        policy = WorkspacePolicy(
            allowed_prefixes=(),
            max_file_bytes=120_000,
            max_change_files=6,
        )
        with self.assertRaises(Exception):
            policy.validate_path(".env")


if __name__ == "__main__":
    unittest.main()

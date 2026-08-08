import json
import tempfile
import unittest
from pathlib import Path

from app.application.agent_orchestrator import AgentOrchestrator
from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.agent_service import AgentApplicationService
from app.application.audit_service import AgentAuditService
from app.application.change_validator import ChangeValidationService
from app.application.code_search_service import CodeSearchService
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.security_service import AgentSecurityService
from app.application.workflow_service import RepositoryWorkflowCatalog, WorkflowSelectionService
from app.config import Settings
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ProposalStatus, WorkspaceFile, WorkspaceStatus
from app.infrastructure.sqlite_audit import SQLiteAuditLog
from app.infrastructure.sqlite_knowledge import SQLiteKnowledgeRepository
from app.infrastructure.sqlite_proposal_store import SQLiteProposalStore


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
            json.dumps(
                {
                    "approved": True,
                    "score": 96,
                    "findings": ["Focused root-cause change"],
                    "required_changes": [],
                }
            ),
            json.dumps(
                {
                    "checks": ["Run Python unit tests"],
                    "workflow_profiles": ["python-tests"],
                    "browser_required": False,
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

    async def read_files(self, paths):
        results = []
        if "app/service.py" in paths:
            results.append(
                WorkspaceFile(
                    path="app/service.py",
                    content="def health():\n    return {}\n",
                    sha="abc123",
                )
            )
        return results

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
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "agent.db")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def build_service(self):
        config = Settings(
            kimi_api_key="test",
            agent_github_repository="owner/repo",
            agent_write_enabled=True,
            agent_github_token="token",
            agent_state_db_path=self.db_path,
        )
        policy = WorkspacePolicy(
            allowed_prefixes=(),
            max_file_bytes=120_000,
            max_change_files=6,
        )
        workspace = FakeWorkspace()
        model = FakeModel()
        proposals = SQLiteProposalStore(self.db_path, ttl_seconds=3600)
        knowledge = ProjectKnowledgeService(SQLiteKnowledgeRepository(self.db_path))
        audit = AgentAuditService(SQLiteAuditLog(self.db_path))
        code_search = CodeSearchService()
        security = AgentSecurityService()
        validator = ChangeValidationService(policy, config)
        workflows = RepositoryWorkflowCatalog(workspace)
        workflow_selection = WorkflowSelectionService()

        orchestrator = AgentOrchestrator(
            planner=PlannerAgent(model),
            coder=CoderAgent(model),
            reviewer=ReviewerAgent(model),
            tester=TesterAgent(model),
            workspace=workspace,
            proposals=proposals,
            validator=validator,
            security=security,
            knowledge=knowledge,
            audit=audit,
            code_search=code_search,
            workflows=workflows,
            workflow_selection=workflow_selection,
            config=config,
        )
        service = AgentApplicationService(
            model=model,
            workspace=workspace,
            proposals=proposals,
            orchestrator=orchestrator,
            knowledge=knowledge,
            audit=audit,
            workflows=workflows,
            code_search=code_search,
            config=config,
        )
        return service, workspace, knowledge

    async def test_v2_creates_reviewed_proposal_and_remembers_after_approval(self):
        service, workspace, knowledge = self.build_service()
        events = [
            event
            async for event in service.stream_task(
                task="Add health helper",
                model="kimi-k2.7-code",
                history=[],
            )
        ]

        event_types = [event["type"] for event in events]
        self.assertIn("knowledge", event_types)
        self.assertIn("search", event_types)
        self.assertIn("review", event_types)
        self.assertIn("validation", event_types)
        self.assertIn("approval_required", event_types)

        approval = next(event for event in events if event["type"] == "approval_required")
        self.assertEqual(approval["proposal"]["review"]["score"], 96)
        self.assertEqual(approval["proposal"]["risk"]["level"], "low")
        self.assertTrue(approval["proposal"]["can_approve"])

        applied = await service.approve(approval["proposal"]["id"])
        self.assertTrue(workspace.applied)
        self.assertEqual(applied["status"], "applied")
        self.assertTrue(applied["knowledge_ids"])
        self.assertEqual(len(knowledge.recent(limit=10)), 1)

    def test_security_blocks_embedded_secret(self):
        service = AgentSecurityService()
        from app.domain.agent import ProposedFileChange

        risk = service.assess(
            task="Add provider configuration",
            changes=[
                ProposedFileChange(
                    path="app/configuration.py",
                    reason="test",
                    content='API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n',
                )
            ],
        )
        self.assertTrue(risk.blocked)
        self.assertEqual(risk.level.value, "blocked")

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

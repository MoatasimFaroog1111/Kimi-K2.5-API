import json
import tempfile
import unittest
from pathlib import Path

from app.application.agent_orchestrator import AgentOrchestrator
from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.agent_service import AgentApplicationService
from app.application.audit_service import AgentAuditService
from app.application.budgeted_model import BudgetedLanguageModel
from app.application.change_validator import ChangeValidationService
from app.application.ci_feedback_service import CiFeedbackService
from app.application.code_search_service import CodeSearchService
from app.application.code_structure import CodeStructureExtractor
from app.application.context_manager import AgentContextManager
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.model_router import AgentModelRouter
from app.application.preapproval_validation_service import PreApprovalValidationService
from app.application.run_budget_service import RunBudgetService
from app.application.run_runtime_service import AgentRunRuntime
from app.application.security_service import AgentSecurityService
from app.application.semantic_search_service import SemanticCodeIntelligence
from app.application.workflow_service import RepositoryWorkflowCatalog, WorkflowSelectionService
from app.config import Settings
from app.core.workspace_policy import WorkspacePolicy
from app.domain.agent import ProposalStatus, WorkspaceFile, WorkspaceStatus
from app.domain.agent_v3 import (
    CiFeedback,
    SandboxValidationResult,
    ValidationCheckResult,
    ValidationCheckStatus,
)
from app.infrastructure.sqlite_audit import SQLiteAuditLog
from app.infrastructure.sqlite_knowledge import SQLiteKnowledgeRepository
from app.infrastructure.sqlite_proposal_store import SQLiteProposalStore
from app.infrastructure.sqlite_run_store import SQLiteRunStore


class FakeModel:
    def __init__(self) -> None:
        self.responses = [
            json.dumps(
                {
                    "hits": [
                        {
                            "path": "app/service.py",
                            "score": 99,
                            "rationale": "Contains the health behavior requested by the task",
                        }
                    ]
                }
            ),
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

    async def list_models(self, *, refresh=False):
        return ["kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k3"]

    async def complete(self, **_kwargs):
        return self.responses.pop(0)


class FakeValidationRunner:
    async def validate(self, *, changes, profiles, attempt, base_ref=None):
        return SandboxValidationResult(
            passed=True,
            attempt=attempt,
            checks=(
                ValidationCheckResult(
                    name="python-unit-tests",
                    status=ValidationCheckStatus.PASSED,
                    command=("python", "-m", "unittest"),
                    output="OK",
                    return_code=0,
                    duration_ms=10,
                ),
            ),
        )


class FakeWorkspace:
    def __init__(self) -> None:
        self.applied = False
        self.last_ref = None

    async def status(self):
        return WorkspaceStatus(
            configured=True,
            repository="owner/repo",
            branch="main",
            write_enabled=True,
            mode="pull-request",
        )

    async def list_files(self, *, ref=None):
        self.last_ref = ref
        return ["app/service.py", "tests/test_service.py"]

    async def read_files(self, paths, *, ref=None):
        self.last_ref = ref
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
        proposal.applied_paths = proposal.approved_paths or tuple(
            change.path for change in proposal.changes
        )
        return proposal

    async def undo_proposal(self, proposal):
        proposal.status = ProposalStatus.UNDONE
        return proposal

    async def feedback(self, _proposal):
        return CiFeedback(status="queued", conclusion=None)


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
            agent_semantic_search_enabled=True,
            agent_preapproval_validation_enabled=True,
            agent_ci_feedback_enabled=True,
            agent_per_file_approval_enabled=True,
            agent_run_token_budget=100_000,
        )
        policy = WorkspacePolicy(
            allowed_prefixes=(),
            max_file_bytes=120_000,
            max_change_files=6,
        )
        workspace = FakeWorkspace()
        base_model = FakeModel()
        proposals = SQLiteProposalStore(self.db_path, ttl_seconds=3600)
        runs = SQLiteRunStore(self.db_path, retention_days=30)
        runtime = AgentRunRuntime(runs, config)
        budget = RunBudgetService(runs, config)
        model = BudgetedLanguageModel(base_model, budget)
        router = AgentModelRouter(base_model, config)
        context = AgentContextManager(config)
        knowledge = ProjectKnowledgeService(SQLiteKnowledgeRepository(self.db_path))
        audit = AgentAuditService(SQLiteAuditLog(self.db_path))
        code_search = CodeSearchService()
        security = AgentSecurityService()
        validator = ChangeValidationService(policy, config)
        workflows = RepositoryWorkflowCatalog(workspace)
        workflow_selection = WorkflowSelectionService()
        semantic = SemanticCodeIntelligence(model, CodeStructureExtractor())
        preapproval = PreApprovalValidationService(FakeValidationRunner())
        ci_feedback = CiFeedbackService(workspace)

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
            semantic=semantic,
            preapproval=preapproval,
            workflows=workflows,
            workflow_selection=workflow_selection,
            runtime=runtime,
            context=context,
            budget=budget,
            config=config,
        )
        service = AgentApplicationService(
            model=base_model,
            workspace=workspace,
            proposals=proposals,
            orchestrator=orchestrator,
            knowledge=knowledge,
            audit=audit,
            workflows=workflows,
            code_search=code_search,
            ci_feedback=ci_feedback,
            runtime=runtime,
            router=router,
            budget=budget,
            config=config,
        )
        return service, workspace, knowledge, runtime

    async def test_v4_creates_persistent_run_and_requires_per_file_approval(self):
        service, workspace, knowledge, runtime = self.build_service()
        events = [
            event
            async for event in service.stream_task(
                task="Add health helper",
                requested_model="kimi-k2.7-code",
                auto_model=False,
                history=[],
            )
        ]

        event_types = [event["type"] for event in events]
        self.assertIn("model_route", event_types)
        self.assertIn("budget", event_types)
        self.assertIn("semantic", event_types)
        self.assertIn("context", event_types)
        self.assertIn("sandbox_validation", event_types)
        self.assertIn("approval_required", event_types)

        approval = next(event for event in events if event["type"] == "approval_required")
        proposal = approval["proposal"]
        self.assertEqual(proposal["review"]["score"], 96)
        self.assertTrue(proposal["sandbox_validation"]["passed"])
        self.assertFalse(proposal["can_approve"])
        self.assertEqual(proposal["approved_paths"], [])

        selected = service.set_file_approvals(proposal["id"], ["app/service.py"])
        self.assertTrue(selected["can_approve"])
        self.assertEqual(selected["approved_paths"], ["app/service.py"])

        applied = await service.approve(proposal["id"])
        self.assertTrue(workspace.applied)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["applied_paths"], ["app/service.py"])
        self.assertEqual(applied["ci_feedback"]["status"], "queued")
        self.assertEqual(len(knowledge.recent(limit=10)), 1)

        run_id = approval["proposal"]["run_id"]
        stored_run = runtime.get(run_id)
        self.assertEqual(stored_run.status.value, "completed")
        self.assertGreater(stored_run.budget.estimated_tokens_used, 0)
        self.assertTrue(service.recent_runs(limit=10))

    def test_security_still_blocks_sensitive_paths(self):
        policy = WorkspacePolicy(
            allowed_prefixes=(),
            max_file_bytes=120_000,
            max_change_files=6,
        )
        with self.assertRaises(Exception):
            policy.validate_path(".env")


if __name__ == "__main__":
    unittest.main()

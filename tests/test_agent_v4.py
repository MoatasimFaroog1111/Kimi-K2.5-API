import tempfile
import unittest
from pathlib import Path

from app.application.context_manager import AgentContextManager
from app.application.model_router import AgentModelRouter
from app.application.run_budget_service import RunBudgetService
from app.application.run_runtime_service import AgentRunRuntime
from app.config import Settings
from app.core.exceptions import AgentBudgetExceededError
from app.domain.agent import WorkspaceFile
from app.domain.agent_v4 import ModelRoute, RunStage, RunStatus
from app.infrastructure.sqlite_run_store import SQLiteRunStore


class RouterModel:
    async def list_models(self, *, refresh=False):
        return ["kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k3"]


class AgentV4Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "agent.db")
        self.config = Settings(
            kimi_api_key="test",
            agent_state_db_path=self.db_path,
            agent_run_token_budget=20_000,
            agent_context_target_chars=20_000,
        )
        self.store = SQLiteRunStore(self.db_path, retention_days=30)
        self.runtime = AgentRunRuntime(self.store, self.config)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_model_router_selects_fast_balanced_and_deep_models(self):
        router = AgentModelRouter(RouterModel(), self.config)
        fast = await router.route(
            task="Fix a simple typo",
            requested_model=None,
            auto=True,
        )
        balanced = await router.route(
            task="Add pagination to this API endpoint",
            requested_model=None,
            auto=True,
        )
        deep = await router.route(
            task="Refactor the architecture and security boundaries",
            requested_model=None,
            auto=True,
        )
        self.assertEqual(fast.selected_model, "kimi-k2.7-code-highspeed")
        self.assertEqual(balanced.selected_model, "kimi-k2.7-code")
        self.assertEqual(deep.selected_model, "kimi-k3")

    def test_run_pause_resume_cancel_are_persisted(self):
        route = ModelRoute(
            requested_model=None,
            selected_model="kimi-k2.7-code",
            mode="auto",
            tier="balanced",
            reason="test",
        )
        run = self.runtime.create(
            task="test task",
            requested_model=None,
            route=route,
            base_branch="main",
            history=[],
        )
        self.assertEqual(self.store.get(run.id).status, RunStatus.RUNNING)

        self.runtime.request_pause(run.id)
        paused = self.runtime.checkpoint(
            run.id,
            stage=RunStage.DISCOVERY_READY,
            payload={"tree": ["app/main.py"]},
        )
        self.assertEqual(paused.status, RunStatus.PAUSED)
        self.assertEqual(self.store.get(run.id).stage, RunStage.DISCOVERY_READY)

        resumed = self.runtime.begin_resume(run.id)
        self.assertEqual(resumed.status, RunStatus.RUNNING)
        self.runtime.request_cancel(run.id)
        cancelled = self.runtime.checkpoint(
            run.id,
            stage=RunStage.PLAN_READY,
            payload={"plan": {"summary": "test"}},
        )
        self.assertEqual(cancelled.status, RunStatus.CANCELLED)

    def test_budget_guard_rejects_projected_overrun(self):
        route = ModelRoute(
            requested_model=None,
            selected_model="kimi-k2.7-code",
            mode="auto",
            tier="balanced",
            reason="test",
        )
        run = self.runtime.create(
            task="budget",
            requested_model=None,
            route=route,
            base_branch="main",
            history=[],
        )
        budget = RunBudgetService(self.store, self.config)
        with budget.bind(run.id):
            with self.assertRaises(AgentBudgetExceededError):
                budget.authorize(
                    model="kimi-k2.7-code",
                    input_chars=60_000,
                    max_output_tokens=10_000,
                )

    def test_context_manager_keeps_whole_files_and_drops_overflow(self):
        context = AgentContextManager(self.config)
        files = [
            WorkspaceFile(path="app/a.py", content="a" * 12_000, sha="a"),
            WorkspaceFile(path="app/b.py", content="b" * 12_000, sha="b"),
        ]
        selected, dropped = context.fit_files(files)
        self.assertEqual([file.path for file in selected], ["app/a.py"])
        self.assertEqual(dropped, ("app/b.py",))
        self.assertEqual(len(selected[0].content), 12_000)


if __name__ == "__main__":
    unittest.main()

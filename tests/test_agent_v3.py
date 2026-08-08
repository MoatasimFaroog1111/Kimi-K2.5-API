import unittest
from pathlib import Path

from app.application.code_structure import CodeStructureExtractor
from app.config import Settings
from app.domain.agent import ProposedFileChange, WorkspaceFile
from app.domain.agent_v3 import ValidationCheckStatus
from app.infrastructure.isolated_validation_runner import IsolatedValidationRunner


class FakeSnapshot:
    async def materialize_snapshot(self, destination: Path, *, ref=None) -> None:
        (destination / "app").mkdir(parents=True, exist_ok=True)
        (destination / "tests").mkdir(parents=True, exist_ok=True)
        (destination / "app" / "__init__.py").write_text("", encoding="utf-8")
        (destination / "app" / "sample.py").write_text(
            "def value():\n    return 1\n",
            encoding="utf-8",
        )
        (destination / "tests" / "test_sample.py").write_text(
            "import unittest\n"
            "from app.sample import value\n\n"
            "class SampleTests(unittest.TestCase):\n"
            "    def test_value(self):\n"
            "        self.assertEqual(value(), 2)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )


class AgentV3Tests(unittest.IsolatedAsyncioTestCase):
    async def test_isolated_runner_executes_real_python_validation(self):
        config = Settings(
            kimi_api_key="test",
            agent_validation_timeout_seconds=30,
            agent_validation_log_chars=4000,
        )
        runner = IsolatedValidationRunner(FakeSnapshot(), config)
        result = await runner.validate(
            changes=[
                ProposedFileChange(
                    path="app/sample.py",
                    reason="update value",
                    content="def value():\n    return 2\n",
                )
            ],
            profiles=("python-tests",),
            attempt=1,
            base_ref="main",
        )
        self.assertTrue(result.passed)
        self.assertTrue(result.checks)
        self.assertFalse(
            any(check.status is ValidationCheckStatus.FAILED for check in result.checks)
        )

    async def test_isolated_runner_reports_compile_failure(self):
        config = Settings(
            kimi_api_key="test",
            agent_validation_timeout_seconds=30,
            agent_validation_log_chars=4000,
        )
        runner = IsolatedValidationRunner(FakeSnapshot(), config)
        result = await runner.validate(
            changes=[
                ProposedFileChange(
                    path="app/sample.py",
                    reason="introduce invalid syntax for validation test",
                    content="def value(:\n    return 2\n",
                )
            ],
            profiles=("python-tests",),
            attempt=1,
            base_ref="main",
        )
        self.assertFalse(result.passed)
        self.assertTrue(result.failed_checks)
        self.assertEqual(result.failed_checks[0].name, "python-compile")

    def test_code_structure_extracts_python_symbols(self):
        extractor = CodeStructureExtractor()
        descriptor = extractor.describe(
            WorkspaceFile(
                path="app/example.py",
                content=(
                    '\"\"\"Example module.\"\"\"\n'
                    "import json\n\n"
                    "class Worker:\n"
                    "    def run(self):\n"
                    "        return json.dumps({})\n"
                ),
                sha="abc",
            ),
            sample_chars=1000,
        )
        self.assertIn("class:Worker", descriptor["symbols"])
        self.assertIn("function:run", descriptor["symbols"])
        self.assertIn("json", descriptor["imports"])
        self.assertEqual(descriptor["summary"], "Example module.")


if __name__ == "__main__":
    unittest.main()

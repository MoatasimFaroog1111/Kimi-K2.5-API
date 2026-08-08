import re

from app.domain.agent_v2 import WorkflowDefinition
from app.domain.ports import WorkspacePort


class RepositoryWorkflowCatalog:
    def __init__(self, workspace: WorkspacePort, prefix: str = ".agent/workflows/") -> None:
        self._workspace = workspace
        self._prefix = prefix.strip("/") + "/"

    async def list_workflows(self) -> list[WorkflowDefinition]:
        tree = await self._workspace.list_files()
        paths = [
            path for path in tree
            if path.startswith(self._prefix) and path.endswith(".md")
        ][:30]
        if not paths:
            return []
        files = await self._workspace.read_files(paths)
        return [self._parse(file.path, file.content) for file in files]

    def _parse(self, path: str, content: str) -> WorkflowDefinition:
        description = "Reusable agent workflow"
        match = re.search(r"(?m)^description:\s*(.+?)\s*$", content)
        if match:
            description = match.group(1).strip().strip("'\"")

        steps: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
            if numbered:
                steps.append(numbered.group(1).strip())
        if not steps:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("- "):
                    steps.append(stripped[2:].strip())

        name = path.rsplit("/", 1)[-1].removesuffix(".md")
        return WorkflowDefinition(
            name=name,
            description=description,
            safe_to_auto_run="// turbo-all" in content,
            steps=tuple(steps[:20]),
        )


class WorkflowSelectionService:
    def select_profiles(self, changed_paths: list[str]) -> tuple[str, ...]:
        profiles: list[str] = []
        lowered = [path.casefold() for path in changed_paths]

        if any(path.endswith(".py") for path in lowered):
            profiles.append("python-tests")
        if any(path.endswith((".js", ".css", ".html")) for path in lowered):
            profiles.append("frontend-check")
        if any(
            path.startswith(("app/api/", "app/core/", "app/security/", ".github/"))
            or "auth" in path
            for path in lowered
        ):
            profiles.append("security-review")
        if any(path.endswith((".html", ".css", ".js")) for path in lowered):
            profiles.append("browser-smoke")

        if not profiles:
            profiles.append("repository-smoke")
        return tuple(dict.fromkeys(profiles))

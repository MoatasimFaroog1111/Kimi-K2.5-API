from app.application.agent_service import AgentApplicationService
from app.application.chat_service import ChatApplicationService
from app.config import settings
from app.core.workspace_policy import WorkspacePolicy
from app.infrastructure.github_workspace import GitHubWorkspace
from app.infrastructure.proposal_store import InMemoryProposalStore
from app.services.kimi_client import KimiService


class ApplicationContainer:
    def __init__(self) -> None:
        self.model = KimiService(settings)
        self.policy = WorkspacePolicy(
            allowed_prefixes=settings.allowed_path_prefixes,
            max_file_bytes=settings.agent_max_file_bytes,
            max_change_files=settings.agent_max_change_files,
        )
        self.workspace = GitHubWorkspace(settings, self.policy)
        self.proposals = InMemoryProposalStore(settings.agent_proposal_ttl_seconds)
        self.chat = ChatApplicationService(self.model, settings)
        self.agent = AgentApplicationService(
            model=self.model,
            workspace=self.workspace,
            proposals=self.proposals,
            policy=self.policy,
            config=settings,
        )


container = ApplicationContainer()

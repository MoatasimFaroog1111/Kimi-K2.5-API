from app.application.agent_orchestrator import AgentOrchestrator
from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.agent_service import AgentApplicationService
from app.application.audit_service import AgentAuditService
from app.application.change_validator import ChangeValidationService
from app.application.chat_service import ChatApplicationService
from app.application.code_search_service import CodeSearchService
from app.application.knowledge_service import ProjectKnowledgeService
from app.application.security_service import AgentSecurityService
from app.application.workflow_service import RepositoryWorkflowCatalog, WorkflowSelectionService
from app.config import settings
from app.core.workspace_policy import WorkspacePolicy
from app.infrastructure.github_workspace import GitHubWorkspace
from app.infrastructure.sqlite_audit import SQLiteAuditLog
from app.infrastructure.sqlite_knowledge import SQLiteKnowledgeRepository
from app.infrastructure.sqlite_proposal_store import SQLiteProposalStore
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

        self.proposals = SQLiteProposalStore(
            settings.agent_state_db_path,
            settings.agent_proposal_ttl_seconds,
        )
        self.knowledge_repository = SQLiteKnowledgeRepository(settings.agent_state_db_path)
        self.audit_repository = SQLiteAuditLog(settings.agent_state_db_path)

        self.knowledge = ProjectKnowledgeService(self.knowledge_repository)
        self.audit = AgentAuditService(self.audit_repository)
        self.code_search = CodeSearchService()
        self.security = AgentSecurityService()
        self.validator = ChangeValidationService(self.policy, settings)
        self.workflows = RepositoryWorkflowCatalog(
            self.workspace,
            prefix=settings.agent_workflow_prefix,
        )
        self.workflow_selection = WorkflowSelectionService()

        self.planner = PlannerAgent(self.model)
        self.coder = CoderAgent(self.model)
        self.reviewer = ReviewerAgent(self.model)
        self.tester = TesterAgent(self.model)

        self.orchestrator = AgentOrchestrator(
            planner=self.planner,
            coder=self.coder,
            reviewer=self.reviewer,
            tester=self.tester,
            workspace=self.workspace,
            proposals=self.proposals,
            validator=self.validator,
            security=self.security,
            knowledge=self.knowledge,
            audit=self.audit,
            code_search=self.code_search,
            workflows=self.workflows,
            workflow_selection=self.workflow_selection,
            config=settings,
        )

        self.chat = ChatApplicationService(self.model, settings)
        self.agent = AgentApplicationService(
            model=self.model,
            workspace=self.workspace,
            proposals=self.proposals,
            orchestrator=self.orchestrator,
            knowledge=self.knowledge,
            audit=self.audit,
            workflows=self.workflows,
            code_search=self.code_search,
            config=settings,
        )


container = ApplicationContainer()

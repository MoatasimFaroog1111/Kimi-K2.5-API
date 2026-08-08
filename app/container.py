from app.application.agent_orchestrator import AgentOrchestrator
from app.application.agent_roles import CoderAgent, PlannerAgent, ReviewerAgent, TesterAgent
from app.application.agent_service import AgentApplicationService
from app.application.audit_service import AgentAuditService
from app.application.budgeted_model import BudgetedLanguageModel
from app.application.change_validator import ChangeValidationService
from app.application.chat_service import ChatApplicationService
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
from app.config import settings
from app.core.workspace_policy import WorkspacePolicy
from app.infrastructure.github_workspace import GitHubWorkspace
from app.infrastructure.isolated_validation_runner import IsolatedValidationRunner
from app.infrastructure.sqlite_audit import SQLiteAuditLog
from app.infrastructure.sqlite_knowledge import SQLiteKnowledgeRepository
from app.infrastructure.sqlite_proposal_store import SQLiteProposalStore
from app.infrastructure.sqlite_run_store import SQLiteRunStore
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
        self.runs_repository = SQLiteRunStore(
            settings.agent_state_db_path,
            settings.agent_run_retention_days,
        )
        self.knowledge_repository = SQLiteKnowledgeRepository(settings.agent_state_db_path)
        self.audit_repository = SQLiteAuditLog(settings.agent_state_db_path)

        self.runtime = AgentRunRuntime(self.runs_repository, settings)
        self.budget = RunBudgetService(self.runs_repository, settings)
        self.agent_model = BudgetedLanguageModel(self.model, self.budget)
        self.router = AgentModelRouter(self.model, settings)
        self.context = AgentContextManager(settings)

        self.knowledge = ProjectKnowledgeService(self.knowledge_repository)
        self.audit = AgentAuditService(self.audit_repository)
        self.code_search = CodeSearchService()
        self.code_structure = CodeStructureExtractor()
        self.semantic = SemanticCodeIntelligence(self.agent_model, self.code_structure)
        self.security = AgentSecurityService()
        self.validator = ChangeValidationService(self.policy, settings)
        self.workflows = RepositoryWorkflowCatalog(
            self.workspace,
            prefix=settings.agent_workflow_prefix,
        )
        self.workflow_selection = WorkflowSelectionService()
        self.validation_runner = IsolatedValidationRunner(self.workspace, settings)
        self.preapproval = PreApprovalValidationService(self.validation_runner)
        self.ci_feedback = CiFeedbackService(self.workspace)

        self.planner = PlannerAgent(self.agent_model)
        self.coder = CoderAgent(self.agent_model)
        self.reviewer = ReviewerAgent(self.agent_model)
        self.tester = TesterAgent(self.agent_model)

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
            semantic=self.semantic,
            preapproval=self.preapproval,
            workflows=self.workflows,
            workflow_selection=self.workflow_selection,
            runtime=self.runtime,
            context=self.context,
            budget=self.budget,
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
            ci_feedback=self.ci_feedback,
            runtime=self.runtime,
            router=self.router,
            budget=self.budget,
            config=settings,
        )


container = ApplicationContainer()

class AgentError(Exception):
    """Base exception for agent application errors."""


class AgentConfigurationError(AgentError):
    """Raised when the agent workspace is not configured."""


class AgentValidationError(AgentError):
    """Raised when generated agent output violates policy."""


class AgentBudgetExceededError(AgentValidationError):
    """Raised when a run would exceed its configured token or cost budget."""


class AgentRunNotFoundError(AgentError):
    """Raised when a persisted agent run cannot be found."""


class AgentRunStateError(AgentError):
    """Raised when a runtime state transition is invalid."""


class ProposalNotFoundError(AgentError):
    """Raised when a proposal is missing or expired."""


class ProposalStateError(AgentError):
    """Raised when a proposal transition is invalid."""


class WorkspaceError(AgentError):
    """Raised when the remote workspace operation fails."""

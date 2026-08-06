import secrets

from fastapi import Header, HTTPException

from app.application.agent_service import AgentApplicationService
from app.application.chat_service import ChatApplicationService
from app.config import settings
from app.container import container


def require_gateway_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    configured_key = settings.gateway_api_key.strip()
    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="API protection is not configured.",
        )
    if x_api_key is None or not secrets.compare_digest(x_api_key, configured_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )


def get_chat_service() -> ChatApplicationService:
    return container.chat


def get_agent_service() -> AgentApplicationService:
    return container.agent

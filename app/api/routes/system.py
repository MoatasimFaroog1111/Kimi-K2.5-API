from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service, require_gateway_api_key
from app.application.chat_service import ChatApplicationService
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.kimi_model,
        "version": "3.0.0",
    }


@router.get("/models", dependencies=[Depends(require_gateway_api_key)])
async def models(
    service: ChatApplicationService = Depends(get_chat_service),
) -> dict[str, list[str]]:
    return {"models": await service.list_models()}

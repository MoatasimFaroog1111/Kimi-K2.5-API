import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.kimi_client import KimiService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kimi K2.5 API Gateway",
    version="1.0.0",
)

kimi_service = KimiService()


def require_gateway_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    configured_key = settings.gateway_api_key.strip()

    if not configured_key:
        logger.error("GATEWAY_API_KEY is not configured.")
        raise HTTPException(
            status_code=503,
            detail="API protection is not configured.",
        )

    if x_api_key is None or not secrets.compare_digest(
        x_api_key,
        configured_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.kimi_model,
    }


@app.get("/models", dependencies=[Depends(require_gateway_api_key)])
async def models() -> dict[str, list[str]]:
    try:
        return {"models": await kimi_service.list_models()}
    except APITimeoutError as exc:
        logger.exception("Kimi models request timed out.")
        raise HTTPException(
            status_code=504,
            detail="Kimi models request timed out.",
        ) from exc
    except APIConnectionError as exc:
        logger.exception("Could not connect to Kimi models API.")
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Kimi models API.",
        ) from exc
    except APIStatusError as exc:
        logger.exception("Kimi models API returned status %s.", exc.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"Kimi models API returned status {exc.status_code}.",
        ) from exc


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_gateway_api_key)],
)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        response = await kimi_service.chat(request.message)

        if not response:
            raise HTTPException(
                status_code=502,
                detail="Kimi returned an empty response.",
            )

        return ChatResponse(
            response=response,
            model=settings.kimi_model,
        )

    except APITimeoutError as exc:
        logger.exception("Kimi API request timed out.")
        raise HTTPException(
            status_code=504,
            detail="Kimi API request timed out.",
        ) from exc

    except APIConnectionError as exc:
        logger.exception("Could not connect to Kimi API.")
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Kimi API.",
        ) from exc

    except APIStatusError as exc:
        logger.exception("Kimi API returned status %s.", exc.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"Kimi API returned status {exc.status_code}.",
        ) from exc

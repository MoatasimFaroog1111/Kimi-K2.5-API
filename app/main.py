import logging

from fastapi import FastAPI, HTTPException
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.kimi_model,
    }


@app.post("/chat", response_model=ChatResponse)
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

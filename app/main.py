import json
import logging
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.kimi_client import KimiService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Kimi Coding Workspace API",
    version="2.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def workspace() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.kimi_model,
        "version": app.version,
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
    "/chat/stream",
    dependencies=[Depends(require_gateway_api_key)],
)
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    selected_model = request.model or settings.kimi_model

    try:
        available_models = await kimi_service.list_models()

        if selected_model not in available_models:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model '{selected_model}' "
                    "is not available for this account."
                ),
            )

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
        logger.exception(
            "Kimi models API returned status %s.",
            exc.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Kimi models API returned status {exc.status_code}.",
        ) from exc

    history = [
        message.model_dump()
        for message in request.history
    ]

    async def generate():
        try:
            async for content in kimi_service.chat_stream(
                request.message,
                model=selected_model,
                history=history,
            ):
                yield json.dumps(
                    {
                        "type": "delta",
                        "content": content,
                    },
                    ensure_ascii=False,
                ) + "\n"

            yield json.dumps(
                {
                    "type": "done",
                    "model": selected_model,
                },
                ensure_ascii=False,
            ) + "\n"

        except APITimeoutError:
            logger.exception("Kimi streaming request timed out.")
            yield json.dumps(
                {
                    "type": "error",
                    "detail": "Kimi API request timed out.",
                },
                ensure_ascii=False,
            ) + "\n"

        except APIConnectionError:
            logger.exception(
                "Could not connect to Kimi streaming API."
            )
            yield json.dumps(
                {
                    "type": "error",
                    "detail": "Could not connect to Kimi API.",
                },
                ensure_ascii=False,
            ) + "\n"

        except APIStatusError as exc:
            logger.exception(
                "Kimi streaming API returned status %s.",
                exc.status_code,
            )
            yield json.dumps(
                {
                    "type": "error",
                    "detail": (
                        f"Kimi API returned status "
                        f"{exc.status_code}."
                    ),
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )



@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_gateway_api_key)],
)
async def chat(request: ChatRequest) -> ChatResponse:
    selected_model = request.model or settings.kimi_model

    try:
        available_models = await kimi_service.list_models()
        if selected_model not in available_models:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{selected_model}' is not available for this account.",
            )

        response = await kimi_service.chat(
            request.message,
            model=selected_model,
            history=[message.model_dump() for message in request.history],
        )

        if not response:
            raise HTTPException(
                status_code=502,
                detail="Kimi returned an empty response.",
            )

        return ChatResponse(
            response=response,
            model=selected_model,
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

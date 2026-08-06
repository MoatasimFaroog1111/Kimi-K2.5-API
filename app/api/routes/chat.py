import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.api.dependencies import get_chat_service, require_gateway_api_key
from app.application.chat_service import ChatApplicationService
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_gateway_api_key)])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ChatResponse:
    response, selected_model = await service.chat(
        message=request.message,
        model=request.model,
        history=[message.model_dump() for message in request.history],
    )
    return ChatResponse(response=response, model=selected_model)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatApplicationService = Depends(get_chat_service),
) -> StreamingResponse:
    selected_model, content_stream = await service.stream(
        message=request.message,
        model=request.model,
        history=[message.model_dump() for message in request.history],
    )

    async def generate():
        try:
            async for content in content_stream:
                yield _event({"type": "delta", "content": content})
            yield _event({"type": "done", "model": selected_model})
        except APITimeoutError:
            logger.exception("Kimi streaming request timed out.")
            yield _event({"type": "error", "detail": "Kimi API request timed out."})
        except APIConnectionError:
            logger.exception("Could not connect to Kimi streaming API.")
            yield _event({"type": "error", "detail": "Could not connect to Kimi API."})
        except APIStatusError as exc:
            logger.exception("Kimi streaming API returned status %s.", exc.status_code)
            yield _event(
                {
                    "type": "error",
                    "detail": f"Kimi API returned status {exc.status_code}.",
                }
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"

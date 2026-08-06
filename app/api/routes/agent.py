import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.api.dependencies import (
    get_agent_service,
    get_chat_service,
    require_gateway_api_key,
)
from app.application.agent_service import AgentApplicationService
from app.application.chat_service import ChatApplicationService
from app.core.exceptions import AgentError
from app.schemas import AgentRequest, ProposalResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(require_gateway_api_key)],
)


@router.get("/status")
async def agent_status(
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return await service.status()


@router.post("/stream")
async def agent_stream(
    request: AgentRequest,
    agent: AgentApplicationService = Depends(get_agent_service),
    chat: ChatApplicationService = Depends(get_chat_service),
) -> StreamingResponse:
    selected_model = await chat.resolve_model(request.model)
    events = agent.stream_task(
        task=request.message,
        model=selected_model,
        history=[message.model_dump() for message in request.history],
    )

    async def generate():
        try:
            async for event in events:
                yield _event(event)
        except AgentError as exc:
            yield _event({"type": "error", "detail": str(exc)})
        except APITimeoutError:
            logger.exception("Kimi agent request timed out.")
            yield _event({"type": "error", "detail": "Kimi API request timed out."})
        except APIConnectionError:
            logger.exception("Could not connect to Kimi agent API.")
            yield _event({"type": "error", "detail": "Could not connect to Kimi API."})
        except APIStatusError as exc:
            logger.exception("Kimi agent API returned status %s.", exc.status_code)
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


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(
    proposal_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> ProposalResponse:
    return ProposalResponse(proposal=await service.approve(proposal_id))


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> ProposalResponse:
    return ProposalResponse(proposal=service.reject(proposal_id))


@router.post("/proposals/{proposal_id}/undo", response_model=ProposalResponse)
async def undo_proposal(
    proposal_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> ProposalResponse:
    return ProposalResponse(proposal=await service.undo(proposal_id))


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.api.dependencies import get_agent_service, require_gateway_api_key
from app.application.agent_service import AgentApplicationService
from app.core.exceptions import AgentError
from app.schemas import AgentRequest, CiRepairRequest, FileApprovalRequest, ProposalResponse

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


@router.get("/memory")
async def agent_memory(
    q: str = Query(default="", max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"items": service.memory(query=q, limit=limit)}


@router.get("/audit")
async def agent_audit(
    limit: int = Query(default=100, ge=1, le=500),
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"events": service.audit_events(limit=limit)}


@router.get("/workflows")
async def agent_workflows(
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"workflows": await service.workflow_catalog()}


@router.get("/search")
async def agent_search(
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=24, ge=1, le=100),
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"query": q, "paths": await service.search_paths(q, limit=limit)}


@router.get("/runs")
async def recent_runs(
    limit: int = Query(default=30, ge=1, le=200),
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"runs": service.recent_runs(limit=limit)}


@router.get("/runs/{run_id}")
async def run_detail(
    run_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"run": service.run_detail(run_id)}


@router.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"run": service.pause_run(run_id)}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    before = service.run_detail(run_id)
    cancelled = service.cancel_run(run_id)
    proposal = before.get("proposal")
    if before.get("status") == "waiting-approval" and isinstance(proposal, dict):
        proposal_id = proposal.get("id")
        if proposal_id:
            service.reject(str(proposal_id))
    return {"run": service.run_detail(run_id) if cancelled.get("status") == "cancelled" else cancelled}


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> StreamingResponse:
    return _stream_response(service.resume_run(run_id))


@router.post("/stream")
async def agent_stream(
    request: AgentRequest,
    agent: AgentApplicationService = Depends(get_agent_service),
) -> StreamingResponse:
    events = agent.stream_task(
        task=request.message,
        requested_model=request.model,
        auto_model=request.auto_model,
        history=[message.model_dump() for message in request.history],
    )
    return _stream_response(events)


@router.put("/proposals/{proposal_id}/file-approvals", response_model=ProposalResponse)
async def set_file_approvals(
    proposal_id: str,
    request: FileApprovalRequest,
    service: AgentApplicationService = Depends(get_agent_service),
) -> ProposalResponse:
    return ProposalResponse(
        proposal=service.set_file_approvals(proposal_id, request.paths)
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


@router.get("/proposals/{proposal_id}/ci")
async def proposal_ci_feedback(
    proposal_id: str,
    service: AgentApplicationService = Depends(get_agent_service),
) -> dict:
    return {"ci": await service.proposal_ci(proposal_id)}


@router.post("/proposals/{proposal_id}/ci/repair/stream")
async def proposal_ci_repair(
    proposal_id: str,
    request: CiRepairRequest,
    service: AgentApplicationService = Depends(get_agent_service),
) -> StreamingResponse:
    events = service.stream_ci_repair(
        proposal_id,
        requested_model=request.model,
        auto_model=request.auto_model,
    )
    return _stream_response(events)


def _stream_response(events: AsyncIterator[dict[str, object]]) -> StreamingResponse:
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


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"

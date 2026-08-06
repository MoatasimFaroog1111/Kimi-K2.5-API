import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.core.exceptions import (
    AgentConfigurationError,
    AgentValidationError,
    ProposalNotFoundError,
    ProposalStateError,
    WorkspaceError,
)

logger = logging.getLogger(__name__)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgentValidationError)
    async def validation_error(_: Request, exc: AgentValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ProposalNotFoundError)
    async def proposal_not_found(_: Request, exc: ProposalNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ProposalStateError)
    async def proposal_state(_: Request, exc: ProposalStateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(AgentConfigurationError)
    async def configuration_error(
        _: Request,
        exc: AgentConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(WorkspaceError)
    async def workspace_error(_: Request, exc: WorkspaceError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(APITimeoutError)
    async def model_timeout(_: Request, exc: APITimeoutError) -> JSONResponse:
        logger.exception("Kimi API request timed out.", exc_info=exc)
        return JSONResponse(
            status_code=504,
            content={"detail": "Kimi API request timed out."},
        )

    @app.exception_handler(APIConnectionError)
    async def model_connection(_: Request, exc: APIConnectionError) -> JSONResponse:
        logger.exception("Could not connect to Kimi API.", exc_info=exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "Could not connect to Kimi API."},
        )

    @app.exception_handler(APIStatusError)
    async def model_status(_: Request, exc: APIStatusError) -> JSONResponse:
        logger.exception("Kimi API returned status %s.", exc.status_code)
        return JSONResponse(
            status_code=502,
            content={"detail": f"Kimi API returned status {exc.status_code}."},
        )

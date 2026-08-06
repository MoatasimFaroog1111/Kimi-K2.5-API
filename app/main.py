import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import install_exception_handlers
from app.api.routes import agent, chat, system

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    application = FastAPI(
        title="Kimi Coding Workspace API",
        version="3.0.0",
    )
    install_exception_handlers(application)
    application.include_router(system.router)
    application.include_router(chat.router)
    application.include_router(agent.router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False, response_class=FileResponse)
    async def workspace() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()

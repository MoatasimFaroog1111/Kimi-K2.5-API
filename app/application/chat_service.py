from collections.abc import AsyncIterator

from app.config import Settings
from app.core.exceptions import AgentValidationError
from app.domain.ports import LanguageModelPort


class ChatApplicationService:
    def __init__(self, model: LanguageModelPort, config: Settings) -> None:
        self._model = model
        self._config = config

    async def list_models(self) -> list[str]:
        return await self._model.list_models()

    async def resolve_model(self, requested_model: str | None) -> str:
        selected = requested_model or self._config.kimi_model
        models = await self.list_models()
        if selected not in models:
            raise AgentValidationError(
                f"Model '{selected}' is not available for this account."
            )
        return selected

    async def chat(
        self,
        *,
        message: str,
        model: str | None,
        history: list[dict[str, str]],
    ) -> tuple[str, str]:
        selected = await self.resolve_model(model)
        response = await self._model.chat(
            message,
            model=selected,
            history=history,
        )
        if not response:
            raise AgentValidationError("Kimi returned an empty response.")
        return response, selected

    async def stream(
        self,
        *,
        message: str,
        model: str | None,
        history: list[dict[str, str]],
    ) -> tuple[str, AsyncIterator[str]]:
        selected = await self.resolve_model(model)
        return selected, self._model.chat_stream(
            message,
            model=selected,
            history=history,
        )

from collections.abc import AsyncIterator

from app.application.run_budget_service import RunBudgetService
from app.domain.ports import LanguageModelPort


class BudgetedLanguageModel:
    """Decorates agent-only model calls with estimated token/cost accounting."""

    def __init__(self, model: LanguageModelPort, budget: RunBudgetService) -> None:
        self._model = model
        self._budget = budget

    async def list_models(self, *, refresh: bool = False) -> list[str]:
        return await self._model.list_models(refresh=refresh)

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        selected = model or ""
        output_limit = max_tokens or 8192
        input_chars = len(system_prompt) + len(user_prompt)
        self._budget.authorize(
            model=selected,
            input_chars=input_chars,
            max_output_tokens=output_limit,
        )
        response = await self._model.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
        )
        self._budget.record(
            model=selected,
            input_chars=input_chars,
            output_chars=len(response),
        )
        return response

    async def chat(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return await self._model.chat(message, model=model, history=history)

    def chat_stream(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        return self._model.chat_stream(message, model=model, history=history)

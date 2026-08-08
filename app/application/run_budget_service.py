from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Iterator

from app.config import Settings
from app.core.exceptions import AgentBudgetExceededError
from app.domain.agent_v4 import RunBudget
from app.domain.ports import RunRepositoryPort


_CURRENT_RUN_ID: ContextVar[str | None] = ContextVar("agent_current_run_id", default=None)


class RunBudgetService:
    def __init__(self, runs: RunRepositoryPort, config: Settings) -> None:
        self._runs = runs
        self._config = config

    @contextmanager
    def bind(self, run_id: str) -> Iterator[None]:
        token = _CURRENT_RUN_ID.set(run_id)
        try:
            yield
        finally:
            _CURRENT_RUN_ID.reset(token)

    @property
    def current_run_id(self) -> str | None:
        return _CURRENT_RUN_ID.get()

    def authorize(
        self,
        *,
        model: str,
        input_chars: int,
        max_output_tokens: int,
    ) -> None:
        run_id = self.current_run_id
        if not run_id:
            return
        run = self._runs.get(run_id)
        input_tokens = self.estimate_tokens(input_chars)
        projected_tokens = run.budget.estimated_tokens_used + input_tokens + max_output_tokens
        if projected_tokens > run.budget.token_limit:
            raise AgentBudgetExceededError(
                "Agent run token budget would be exceeded before the next model call."
            )

        rates = self._config.model_pricing.get(model)
        if rates and run.budget.cost_limit_usd > 0:
            current = run.budget.estimated_cost_usd or 0.0
            projected_cost = current + self._cost(
                rates,
                input_tokens=input_tokens,
                output_tokens=max_output_tokens,
            )
            if projected_cost > run.budget.cost_limit_usd:
                raise AgentBudgetExceededError(
                    "Agent run cost budget would be exceeded before the next model call."
                )

    def record(
        self,
        *,
        model: str,
        input_chars: int,
        output_chars: int,
    ) -> RunBudget | None:
        run_id = self.current_run_id
        if not run_id:
            return None
        run = self._runs.get(run_id)
        input_tokens = self.estimate_tokens(input_chars)
        output_tokens = self.estimate_tokens(output_chars)
        used = run.budget.estimated_tokens_used + input_tokens + output_tokens

        rates = self._config.model_pricing.get(model)
        cost_tracking = bool(rates)
        cost = run.budget.estimated_cost_usd
        if rates:
            cost = (cost or 0.0) + self._cost(
                rates,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        run.budget = replace(
            run.budget,
            estimated_tokens_used=used,
            estimated_cost_usd=cost,
            cost_tracking=cost_tracking,
        )
        self._runs.save(run)
        return run.budget

    def serialize(self, budget: RunBudget) -> dict[str, object]:
        return {
            "token_limit": budget.token_limit,
            "estimated_tokens_used": budget.estimated_tokens_used,
            "remaining_tokens": budget.remaining_tokens,
            "cost_limit_usd": budget.cost_limit_usd,
            "estimated_cost_usd": budget.estimated_cost_usd,
            "cost_tracking": budget.cost_tracking,
        }

    @staticmethod
    def estimate_tokens(chars: int) -> int:
        return max(1, (max(0, chars) + 3) // 4)

    @staticmethod
    def _cost(
        rates: dict[str, float],
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        return (
            input_tokens * float(rates.get("input", 0.0))
            + output_tokens * float(rates.get("output", 0.0))
        ) / 1_000_000

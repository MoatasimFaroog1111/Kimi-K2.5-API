import re

from app.config import Settings
from app.core.exceptions import AgentValidationError
from app.domain.agent_v4 import ModelRoute
from app.domain.ports import LanguageModelPort


class AgentModelRouter:
    _DEEP_HINTS = {
        "architecture", "architectural", "refactor", "migration", "security",
        "concurrency", "distributed", "multi-agent", "root cause", "complex",
        "معمارية", "إعادة هيكلة", "ترحيل", "أمان", "معقد", "جذري",
    }
    _FAST_HINTS = {
        "rename", "typo", "syntax", "format", "explain", "small", "simple",
        "quick", "تعليق", "تنسيق", "بسيط", "سريع", "شرح", "اسم",
    }

    def __init__(self, model: LanguageModelPort, config: Settings) -> None:
        self._model = model
        self._config = config

    async def route(
        self,
        *,
        task: str,
        requested_model: str | None,
        auto: bool,
    ) -> ModelRoute:
        available = await self._model.list_models()
        if not available:
            raise AgentValidationError("No Kimi models are available for this account.")

        if not auto or not self._config.agent_model_router_enabled:
            selected = requested_model or self._config.kimi_model
            if selected not in available:
                raise AgentValidationError(
                    f"Model '{selected}' is not available for this account."
                )
            return ModelRoute(
                requested_model=requested_model,
                selected_model=selected,
                mode="manual",
                tier="manual",
                reason="The user-selected model was preserved.",
            )

        normalized = " ".join(task.casefold().split())
        words = set(re.findall(r"[\w-]+", normalized, flags=re.UNICODE))
        deep = any(hint in normalized or hint in words for hint in self._DEEP_HINTS)
        fast = any(hint in normalized or hint in words for hint in self._FAST_HINTS)
        task_size = len(normalized)

        if deep or task_size > 1400:
            preferred = self._config.agent_model_router_deep
            tier = "deep"
            reason = "Architecture/complexity signals require deeper reasoning."
        elif fast and task_size < 500:
            preferred = self._config.agent_model_router_fast
            tier = "fast"
            reason = "The task is narrow and latency-sensitive."
        else:
            preferred = self._config.agent_model_router_default
            tier = "balanced"
            reason = "The task fits the balanced coding route."

        fallback_order = [
            preferred,
            requested_model,
            self._config.agent_model_router_default,
            self._config.kimi_model,
            self._config.agent_model_router_fast,
            self._config.agent_model_router_deep,
            *available,
        ]
        selected = next(
            (model for model in fallback_order if model and model in available),
            available[0],
        )
        if selected != preferred:
            reason += f" Preferred model was unavailable; routed to {selected}."

        return ModelRoute(
            requested_model=requested_model,
            selected_model=selected,
            mode="auto",
            tier=tier,
            reason=reason,
        )

    @staticmethod
    def serialize(route: ModelRoute) -> dict[str, object]:
        return {
            "requested_model": route.requested_model,
            "selected_model": route.selected_model,
            "mode": route.mode,
            "tier": route.tier,
            "reason": route.reason,
        }

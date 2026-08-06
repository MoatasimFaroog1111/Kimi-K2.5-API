from time import monotonic

from openai import AsyncOpenAI

from app.config import settings


class KimiService:
    _MODEL_CACHE_SECONDS = 600

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
            timeout=180.0,
            max_retries=2,
        )
        self._model_cache: list[str] = []
        self._model_cache_expires_at = 0.0

    async def list_models(self, *, refresh: bool = False) -> list[str]:
        now = monotonic()
        if (
            not refresh
            and self._model_cache
            and now < self._model_cache_expires_at
        ):
            return list(self._model_cache)

        models = await self._client.models.list()
        self._model_cache = sorted(model.id for model in models.data)
        self._model_cache_expires_at = now + self._MODEL_CACHE_SECONDS
        return list(self._model_cache)

    async def chat(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        selected_model = model or settings.kimi_model
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are Kimi, a precise and practical software engineering "
                    "assistant provided by Moonshot AI. Respond in the user's "
                    "language. Prefer production-ready code, clear file paths, "
                    "safe defaults, and concise explanations."
                ),
            }
        ]

        for item in (history or [])[-40:]:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        completion = await self._client.chat.completions.create(
            model=selected_model,
            messages=messages,
            max_tokens=4096,
        )

        content = completion.choices[0].message.content
        return content or ""

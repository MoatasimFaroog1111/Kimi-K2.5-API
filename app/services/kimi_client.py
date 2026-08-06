from collections.abc import AsyncIterator
from time import monotonic

from openai import AsyncOpenAI

from app.config import Settings, settings


class KimiService:
    _MODEL_CACHE_SECONDS = 600
    _CHAT_SYSTEM_PROMPT = (
        "You are Kimi, a precise and practical software engineering assistant. "
        "Respond in the user's language. Prefer production-ready code, clear file "
        "paths, safe defaults, root-cause fixes, and concise explanations."
    )

    def __init__(self, config: Settings = settings) -> None:
        self._config = config
        self._client = AsyncOpenAI(
            api_key=config.kimi_api_key,
            base_url=config.kimi_base_url,
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

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        completion = await self._client.chat.completions.create(
            model=model or self._config.kimi_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens or self._config.agent_max_output_tokens,
        )
        return completion.choices[0].message.content or ""

    async def chat(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        completion = await self._client.chat.completions.create(
            model=model or self._config.kimi_model,
            messages=self._build_chat_messages(message, history),
            max_tokens=4096,
        )
        return completion.choices[0].message.content or ""

    async def chat_stream(
        self,
        message: str,
        *,
        model: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=model or self._config.kimi_model,
            messages=self._build_chat_messages(message, history),
            max_tokens=4096,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content

    def _build_chat_messages(
        self,
        message: str,
        history: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._CHAT_SYSTEM_PROMPT}
        ]
        for item in (history or [])[-40:]:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        return messages

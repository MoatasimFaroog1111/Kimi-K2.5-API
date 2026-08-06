from openai import AsyncOpenAI

from app.config import settings


class KimiService:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
            timeout=180.0,
            max_retries=2,
        )

    async def list_models(self) -> list[str]:
        models = await self._client.models.list()
        return sorted(model.id for model in models.data)

    async def chat(self, message: str) -> str:
        completion = await self._client.chat.completions.create(
            model=settings.kimi_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Kimi, a helpful and accurate AI assistant "
                        "provided by Moonshot AI."
                    ),
                },
                {
                    "role": "user",
                    "content": message,
                },
            ],
            max_tokens=4096,
        )

        content = completion.choices[0].message.content
        return content or ""

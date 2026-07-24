"""OpenAI Responses API adapter."""

from typing import Any, cast

from openai import AsyncOpenAI

from wingman.config import Settings


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key is not configured")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0, max_retries=2)
        self.model = settings.openai_main_model

    async def reply(
        self,
        messages: list[tuple[str, str]],
        user_name: str,
        person_name: str,
        context: str = "",
    ) -> str:
        prompt = (
            "You are a thoughtful private relationship wingman. Be natural and concise. "
            "Do not recommend manipulation, pressure, surveillance, or deception. "
            f"The user's name is {user_name or 'the user'}. The person discussed is "
            f"{person_name or 'someone important to the user'}. "
            f"{context}"
        )
        response = await self.client.responses.create(
            model=self.model,
            instructions=prompt,
            input=cast(Any, [{"role": role, "content": text} for role, text in messages[-20:]]),
        )
        return response.output_text.strip()

    async def embed(
        self, text: str, embedding_model: str = "text-embedding-3-small"
    ) -> list[float]:
        response = await self.client.embeddings.create(model=embedding_model, input=text)
        return response.data[0].embedding

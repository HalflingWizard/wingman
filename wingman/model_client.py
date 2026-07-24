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
        self.summary_model = settings.openai_summary_model
        self.last_usage: tuple[int | None, int | None] = (None, None)

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
        usage = response.usage
        self.last_usage = (
            getattr(usage, "input_tokens", None) if usage else None,
            getattr(usage, "output_tokens", None) if usage else None,
        )
        return response.output_text.strip()

    async def summarize(self, existing_summary: str, messages: list[tuple[str, str]]) -> str:
        input_text = "\n".join(f"{sender}: {text}" for sender, text in messages)
        response = await self.client.responses.create(
            model=self.summary_model,
            instructions=(
                "Update a concise rolling conversation summary. Keep current topic, user goal, "
                "emotional context, decisions, corrections, open questions, commitments, and "
                "temporary details. Do not repeat durable memories unnecessarily."
            ),
            input=f"Existing summary\n{existing_summary}\n\nMessages\n{input_text}",
        )
        usage = response.usage
        self.last_usage = (
            getattr(usage, "input_tokens", None) if usage else None,
            getattr(usage, "output_tokens", None) if usage else None,
        )
        return response.output_text.strip()

    async def embed(
        self, text: str, embedding_model: str = "text-embedding-3-small"
    ) -> list[float]:
        response = await self.client.embeddings.create(model=embedding_model, input=text)
        return response.data[0].embedding

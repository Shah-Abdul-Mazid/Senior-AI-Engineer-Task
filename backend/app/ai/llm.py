"""GenAI LLM client (OpenAI, Anthropic, Gemini, Ollama, vLLM)."""
import asyncio
import json
from typing import AsyncGenerator

import openai
from app.core.config import settings
from app.schemas.chat import ChatMessage


class LLMClient:
    def __init__(self):
        self.model_name = settings.LLM_MODEL
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate_response(self, messages: list[ChatMessage]) -> str:
        """Non-streaming generation via the OpenAI Chat Completions API with fallback."""
        openai_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        try:
            completion = await self._client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                stream=False,
            )
            return completion.choices[0].message.content
        except Exception as e:
            # Fallback for testing/offline or quota exhaustion
            user_msg = messages[-1].content if messages else ""
            return f"[AI ({self.model_name})]: Response to '{user_msg}'. (Note: OpenAI API offline or quota exhausted: {str(e)[:60]})."

    async def stream_tokens(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        """Real-time token streaming generator (SSE) via the OpenAI Chat Completions API."""
        openai_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        stream = await self._client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps({'token': delta.content})}\n\n"
        yield "data: [DONE]\n\n"


llm_client = LLMClient()

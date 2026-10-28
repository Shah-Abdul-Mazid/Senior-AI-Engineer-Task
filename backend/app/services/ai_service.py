import time
from typing import AsyncGenerator
from app.schemas.chat import ChatRequest, ChatResponse, ChatMessage
from app.schemas.rag import RAGRequest, RAGResponse
from app.ai.llm import llm_client
from app.ai.rag import retriever
from app.core.config import settings


class AIService:
    async def chat(self, request: ChatRequest) -> ChatResponse:
        start_time = time.perf_counter()
        response_text = await llm_client.generate_response(request.messages)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ChatResponse(
            message=ChatMessage(role="assistant", content=response_text),
            model=settings.LLM_MODEL,
            tokens_used=len(response_text.split()),
            latency_ms=round(latency_ms, 2),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        async for chunk in llm_client.stream_tokens(request.messages):
            yield chunk

    async def answer_rag(self, request: RAGRequest) -> RAGResponse:
        start_time = time.perf_counter()
        docs = retriever.search(request.query, top_k=request.top_k)
        context = " ".join([d.text for d in docs])
        answer = f"Based on retrieved context [{context[:60]}...], answer to '{request.query}' generated."
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return RAGResponse(
            query=request.query,
            answer=answer,
            sources=docs,
            latency_ms=round(latency_ms, 2),
        )


ai_service = AIService()

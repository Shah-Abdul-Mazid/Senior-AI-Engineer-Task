from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import ai_service

router = APIRouter(prefix="/chat", tags=["AI & GenAI"])


@router.post("/", response_model=ChatResponse)
async def chat_completion(payload: ChatRequest):
    """Standard GenAI Chat Completion."""
    return await ai_service.chat(payload)


@router.post("/stream")
async def chat_stream(payload: ChatRequest):
    """Real-time token-by-token streaming (Server-Sent Events)."""
    return StreamingResponse(
        ai_service.stream_chat(payload),
        media_type="text/event-stream",
    )

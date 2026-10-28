from pydantic import BaseModel
from typing import List


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False


class ChatResponse(BaseModel):
    message: ChatMessage
    model: str
    tokens_used: int
    latency_ms: float

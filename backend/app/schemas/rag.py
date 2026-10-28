from pydantic import BaseModel
from typing import List


class DocumentChunk(BaseModel):
    id: str
    text: str
    score: float


class RAGRequest(BaseModel):
    query: str
    top_k: int = 3


class RAGResponse(BaseModel):
    query: str
    answer: str
    sources: List[DocumentChunk]
    latency_ms: float

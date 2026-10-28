from fastapi import APIRouter
from app.schemas.rag import RAGRequest, RAGResponse
from app.services.ai_service import ai_service

router = APIRouter(prefix="/rag", tags=["AI & RAG"])


@router.post("/query", response_model=RAGResponse)
async def rag_query(payload: RAGRequest):
    """Retrieval-Augmented Generation (Vector Search + LLM)."""
    return await ai_service.answer_rag(payload)

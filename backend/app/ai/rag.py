"""RAG Vector store & Retriever."""
from typing import List
from app.schemas.rag import DocumentChunk


class VectorRetriever:
    def __init__(self):
        # Ready for ChromaDB, Qdrant, Pinecone, or pgvector
        self.knowledge_base = [
            DocumentChunk(id="doc_1", text="FastAPI provides high-performance asynchronous endpoints ideal for AI.", score=0.96),
            DocumentChunk(id="doc_2", text="AI Engineers use StreamingResponse for token-by-token LLM generation.", score=0.92),
            DocumentChunk(id="doc_3", text="RAG combines vector retrieval with LLMs to provide grounded answers.", score=0.89),
        ]

    def search(self, query: str, top_k: int = 3) -> List[DocumentChunk]:
        return self.knowledge_base[:top_k]


retriever = VectorRetriever()

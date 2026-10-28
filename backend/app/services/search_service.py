"""Search and retrieval service supporting keyword, semantic, and hybrid search."""
import time
import math
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, desc
import openai
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.schemas.document import SearchRequest, SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self._client: Optional[openai.AsyncOpenAI] = None

    def _get_client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector using OpenAI text-embedding-3-small."""
        try:
            client = self._get_client()
            res = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text[:4000],  # stay within safe token limits
            )
            return res.data[0].embedding
        except Exception as e:
            logger.warning(f"Could not generate embedding via OpenAI ({e}). Using semantic fallback.")
            return None

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def search(self, payload: SearchRequest, db: AsyncSession) -> SearchResponse:
        start_time = time.perf_counter()
        search_type = payload.search_type
        query = payload.query.strip()

        # Build base query joining Document and Invoice
        stmt = (
            select(Document, Invoice)
            .outerjoin(Invoice, Document.id == Invoice.document_id)
        )

        # Filters
        if payload.status_filter:
            stmt = stmt.where(Document.status == payload.status_filter)
        if payload.file_type_filter:
            stmt = stmt.where(Document.file_type == payload.file_type_filter)
        if payload.date_from and hasattr(Invoice, "invoice_date"):
            stmt = stmt.where(Invoice.invoice_date >= payload.date_from)
        if payload.date_to and hasattr(Invoice, "invoice_date"):
            stmt = stmt.where(Invoice.invoice_date <= payload.date_to)

        result = await db.execute(stmt)
        rows = result.all()

        matched_items: List[SearchResultItem] = []
        q_lower = query.lower()
        q_tokens = set(q_lower.split())

        query_embedding = None
        if search_type in ["semantic", "hybrid"]:
            query_embedding = await self.get_embedding(query)

        for doc, inv in rows:
            score = 0.0

            # 1. Keyword matching
            text_corpus = f"{doc.filename} {doc.raw_text or ''} {inv.supplier_name if inv else ''} {inv.invoice_number if inv else ''} {inv.customer_name if inv else ''}".lower()

            keyword_hits = sum(1 for token in q_tokens if token in text_corpus)
            keyword_score = keyword_hits / (len(q_tokens) or 1)

            # Exact invoice number match gets highest boost
            if inv and inv.invoice_number and q_lower == inv.invoice_number.lower():
                keyword_score = 1.0

            # 2. Semantic matching
            semantic_score = 0.0
            if query_embedding and doc.text_embedding:
                semantic_score = self._cosine_similarity(query_embedding, doc.text_embedding)

            # 3. Hybrid blend
            if search_type == "keyword":
                score = keyword_score
            elif search_type == "semantic":
                score = semantic_score if query_embedding else keyword_score
            else:  # hybrid
                score = (0.4 * keyword_score) + (0.6 * semantic_score) if query_embedding else keyword_score

            if score > 0.05 or (search_type == "keyword" and keyword_hits > 0):
                matched_items.append(
                    SearchResultItem(
                        document_id=doc.id,
                        filename=doc.original_filename or doc.filename,
                        file_type=doc.file_type.value if hasattr(doc.file_type, "value") else str(doc.file_type),
                        status=doc.status,
                        invoice_number=inv.invoice_number if inv else None,
                        supplier_name=inv.supplier_name if inv else None,
                        total=inv.total if inv else None,
                        currency=inv.currency if inv else None,
                        relevance_score=round(score, 4),
                        created_at=doc.created_at,
                    )
                )

        # Sort by relevance score descending
        matched_items.sort(key=lambda x: (x.relevance_score or 0.0), reverse=True)
        results = matched_items[:payload.top_k]

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return SearchResponse(
            query=query,
            search_type=search_type,
            results=results,
            total_results=len(matched_items),
            latency_ms=round(latency_ms, 2),
        )


search_service = SearchService()

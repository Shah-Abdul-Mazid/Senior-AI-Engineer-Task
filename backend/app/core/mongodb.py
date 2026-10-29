"""MongoDB connection and operations for Task 5: Document Metadata, Extracted Text,
Structured Results, Validation Errors, Processing History, and Search (Keyword + Semantic).
"""
import asyncio
import math
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

import motor.motor_asyncio
from pymongo import MongoClient, TEXT, ASCENDING, DESCENDING
from app.core.config import settings

logger = logging.getLogger(__name__)


class MongoDBManager:
    def __init__(self):
        self._motor_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self._sync_client: Optional[MongoClient] = None
        self._db_name: str = "docai_intelligence"
        self._connected: bool = False
        self._client_loop = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_db_name(self) -> str:
        # Sanitize projects name for Mongo database naming standards (max 38 bytes in MongoDB Atlas)
        raw_name = getattr(settings, "MONGODB_DB_PROJECTS_NAME", "docai_intelligence")
        clean = "".join(c if c.isalnum() or c == "_" else "_" for c in raw_name).strip("_")
        if not clean or len(clean) > 35:
            clean = "docai_intelligence"
        return clean

    async def connect(self) -> bool:
        """Connects to MongoDB Atlas using clean RFC 3986 URL-encoded credentials."""
        uri = settings.clean_mongodb_uri
        if not uri:
            logger.warning("[MongoDB] No MONGODB_URI configured in settings.")
            return False

        try:
            loop = asyncio.get_running_loop()
            self._db_name = self._get_db_name()
            self._motor_client = motor.motor_asyncio.AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            self._client_loop = loop
            # Test ping
            await self._motor_client.admin.command("ping")
            self._connected = True
            logger.info(f"[MongoDB] Connected successfully to Atlas database '{self._db_name}'")

            # Initialize collections and text/compound indexes
            await self._init_indexes()
            return True
        except Exception as e:
            logger.warning(f"[MongoDB] Could not connect to Atlas: {e}")
            self._connected = False
            return False

    def get_sync_db(self):
        """Synchronous PyMongo database handle for background workers or scripts."""
        uri = settings.clean_mongodb_uri
        if not uri:
            return None
        if self._sync_client is None:
            self._sync_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._sync_client[self._get_db_name()]

    def get_db(self):
        """Async motor database handle with dynamic loop binding."""
        uri = settings.clean_mongodb_uri
        if not uri:
            return None

        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._motor_client is None or (curr_loop is not None and self._client_loop != curr_loop):
            self._motor_client = motor.motor_asyncio.AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            self._client_loop = curr_loop
            self._connected = True

        return self._motor_client[self._get_db_name()]

    async def _init_indexes(self):
        """Creates compound and full-text search indexes across collections."""
        try:
            db = self.get_db()
            if db is None:
                return

            # 1. Documents collection indexes
            await db.documents.create_index([("document_id", ASCENDING)], unique=True)
            await db.documents.create_index([("status", ASCENDING)])
            await db.documents.create_index([("file_type", ASCENDING)])
            await db.documents.create_index([("created_at", DESCENDING)])

            # Full-text search index on document raw_text and filename
            try:
                await db.documents.create_index(
                    [
                        ("raw_text", TEXT),
                        ("filename", TEXT),
                        ("original_filename", TEXT),
                    ],
                    name="doc_fulltext_idx",
                )
            except Exception:
                pass

            # 2. Invoices collection indexes
            await db.invoices.create_index([("document_id", ASCENDING)], unique=True)
            await db.invoices.create_index([("invoice_number", ASCENDING)])
            await db.invoices.create_index([("purchase_order_number", ASCENDING)])
            await db.invoices.create_index([("supplier_name", ASCENDING)])
            await db.invoices.create_index([("customer_name", ASCENDING)])
            await db.invoices.create_index([("invoice_date", DESCENDING)])
            await db.invoices.create_index([("total", ASCENDING)])

            # Full-text search index on invoice entities
            try:
                await db.invoices.create_index(
                    [
                        ("invoice_number", TEXT),
                        ("purchase_order_number", TEXT),
                        ("supplier_name", TEXT),
                        ("customer_name", TEXT),
                        ("line_items.description", TEXT),
                    ],
                    name="inv_fulltext_idx",
                )
            except Exception:
                pass

            # 3. Validation errors collection indexes
            await db.validation_errors.create_index([("document_id", ASCENDING)])
            await db.validation_errors.create_index([("severity", ASCENDING)])
            await db.validation_errors.create_index([("resolved", ASCENDING)])

            # 4. Processing history collection indexes
            await db.processing_history.create_index([("document_id", ASCENDING)])
            await db.processing_history.create_index([("created_at", DESCENDING)])

            logger.info("[MongoDB] Full-text and compound indexes verified successfully.")
        except Exception as e:
            logger.warning(f"[MongoDB] Index creation notice: {e}")

    # ── CRUD Operations for Document Metadata, Extracted Text & Results ───────

    async def save_document(self, doc_data: Dict[str, Any]) -> bool:
        """Stores or updates document metadata and raw extracted text."""
        db = self.get_db()
        if db is None:
            return False
        try:
            doc_id = str(doc_data.get("document_id") or doc_data.get("id"))
            update_data = {**doc_data, "document_id": doc_id, "updated_at": datetime.utcnow()}
            if "created_at" not in update_data:
                update_data["created_at"] = datetime.utcnow()

            await db.documents.update_one(
                {"document_id": doc_id},
                {"$set": update_data},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Error saving document {doc_data.get('document_id')}: {e}")
            return False

    async def save_invoice(self, invoice_data: Dict[str, Any]) -> bool:
        """Stores or updates structured invoice extraction results & line items."""
        db = self.get_db()
        if db is None:
            return False
        try:
            doc_id = str(invoice_data.get("document_id"))
            update_data = {**invoice_data, "document_id": doc_id, "updated_at": datetime.utcnow()}

            await db.invoices.update_one(
                {"document_id": doc_id},
                {"$set": update_data},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Error saving invoice for doc {invoice_data.get('document_id')}: {e}")
            return False

    async def save_validation_errors(self, document_id: str, errors: List[Dict[str, Any]]) -> bool:
        """Stores validation errors for a document."""
        db = self.get_db()
        if db is None:
            return False
        try:
            doc_id = str(document_id)
            # Remove previous errors for this document
            await db.validation_errors.delete_many({"document_id": doc_id})

            if errors:
                docs_to_insert = [
                    {
                        **err,
                        "document_id": doc_id,
                        "created_at": datetime.utcnow(),
                    }
                    for err in errors
                ]
                await db.validation_errors.insert_many(docs_to_insert)
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Error saving validation errors: {e}")
            return False

    async def record_processing_history(
        self,
        document_id: str,
        status: str,
        stage: str,
        attempt_count: int = 1,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Appends a processing history audit record for tracking."""
        db = self.get_db()
        if db is None:
            return False
        try:
            record = {
                "document_id": str(document_id),
                "status": status,
                "stage": stage,
                "attempt_count": attempt_count,
                "duration_ms": duration_ms,
                "error_message": error_message,
                "timestamp": datetime.utcnow(),
            }
            await db.processing_history.insert_one(record)
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Error recording processing history: {e}")
            return False

    async def get_document_full(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves document metadata, extracted invoice, validation errors, and history."""
        db = self.get_db()
        if db is None:
            return None
        doc_id = str(document_id)
        doc = await db.documents.find_one({"document_id": doc_id}, {"_id": 0})
        if not doc:
            return None

        invoice = await db.invoices.find_one({"document_id": doc_id}, {"_id": 0})
        cursor_errs = db.validation_errors.find({"document_id": doc_id}, {"_id": 0})
        errors = await cursor_errs.to_list(length=100)

        cursor_hist = db.processing_history.find({"document_id": doc_id}, {"_id": 0}).sort("timestamp", -1)
        history = await cursor_hist.to_list(length=20)

        return {
            "document": doc,
            "invoice": invoice,
            "validation_errors": errors,
            "processing_history": history,
        }

    # ── Search Engine: Keyword Filtering & Semantic Search ────────────────────

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def search(
        self,
        query: str,
        search_type: str = "hybrid",  # "keyword", "semantic", "hybrid"
        query_embedding: Optional[List[float]] = None,
        status_filter: Optional[str] = None,
        file_type_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Executes keyword-based filtering, semantic search, or hybrid search directly on MongoDB.
        """
        db = self.get_db()
        if db is None:
            return []

        q_clean = query.strip()
        q_tokens = [t.lower() for t in q_clean.split() if t]

        # 1. Base query filter
        doc_match: Dict[str, Any] = {}
        if status_filter:
            doc_match["status"] = status_filter
        if file_type_filter:
            doc_match["file_type"] = file_type_filter

        # Fetch all matching documents
        cursor = db.documents.find(doc_match, {"_id": 0})
        docs = await cursor.to_list(length=200)
        if not docs:
            return []

        doc_ids = [d["document_id"] for d in docs]
        inv_cursor = db.invoices.find({"document_id": {"$in": doc_ids}}, {"_id": 0})
        invoices_list = await inv_cursor.to_list(length=200)
        invoices_map = {inv["document_id"]: inv for inv in invoices_list}

        results: List[Dict[str, Any]] = []

        for doc in docs:
            d_id = doc["document_id"]
            inv = invoices_map.get(d_id)

            # Apply invoice date filters if provided
            if date_from and inv and inv.get("invoice_date") and str(inv["invoice_date"]) < str(date_from):
                continue
            if date_to and inv and inv.get("invoice_date") and str(inv["invoice_date"]) > str(date_to):
                continue

            # Compute Keyword Score
            keyword_score = 0.0
            if q_clean:
                text_corpus = (
                    f"{doc.get('filename', '')} "
                    f"{doc.get('raw_text', '')} "
                    f"{inv.get('supplier_name', '') if inv else ''} "
                    f"{inv.get('invoice_number', '') if inv else ''} "
                    f"{inv.get('customer_name', '') if inv else ''} "
                    f"{inv.get('purchase_order_number', '') if inv else ''}"
                ).lower()

                # Exact matches get highest score
                if inv and inv.get("invoice_number") and q_clean.lower() == str(inv["invoice_number"]).lower():
                    keyword_score = 1.0
                elif inv and inv.get("purchase_order_number") and q_clean.lower() == str(inv["purchase_order_number"]).lower():
                    keyword_score = 1.0
                elif q_tokens:
                    hits = sum(1 for tok in q_tokens if tok in text_corpus)
                    keyword_score = hits / len(q_tokens)
            else:
                keyword_score = 1.0

            # Compute Semantic Score
            semantic_score = 0.0
            if query_embedding and doc.get("text_embedding"):
                semantic_score = self._cosine_similarity(query_embedding, doc["text_embedding"])

            # Compute Combined Score
            if search_type == "keyword":
                final_score = keyword_score
            elif search_type == "semantic":
                final_score = semantic_score if query_embedding else keyword_score
            else:  # hybrid
                if query_embedding:
                    final_score = 0.4 * keyword_score + 0.6 * semantic_score
                else:
                    final_score = keyword_score

            if final_score > 0.05 or not q_clean:
                # Find matching highlight snippet
                snippet = ""
                raw_text = doc.get("raw_text") or ""
                if q_clean and raw_text:
                    lower_raw = raw_text.lower()
                    idx = lower_raw.find(q_clean.lower())
                    if idx != -1:
                        snippet = raw_text[max(0, idx - 60):min(len(raw_text), idx + 140)].replace("\n", " ").strip()
                    else:
                        for tok in q_tokens:
                            idx = lower_raw.find(tok)
                            if idx != -1:
                                snippet = raw_text[max(0, idx - 60):min(len(raw_text), idx + 140)].replace("\n", " ").strip()
                                break
                if not snippet and raw_text:
                    snippet = raw_text[:160].replace("\n", " ").strip()

                results.append({
                    "document_id": d_id,
                    "filename": doc.get("filename"),
                    "status": doc.get("status"),
                    "score": round(float(final_score), 4),
                    "invoice_number": inv.get("invoice_number") if inv else None,
                    "supplier_name": inv.get("supplier_name") if inv else None,
                    "customer_name": inv.get("customer_name") if inv else None,
                    "invoice_date": str(inv["invoice_date"]) if inv and inv.get("invoice_date") else None,
                    "total": inv.get("total") if inv else None,
                    "currency": inv.get("currency", "USD") if inv else "USD",
                    "snippet": snippet,
                    "search_type_applied": search_type,
                })

        # Sort results by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def clear_all(self) -> int:
        """Deletes all documents, invoices, errors, and history from MongoDB."""
        db = self.get_db()
        if db is None:
            return 0
        try:
            r1 = await db.documents.delete_many({})
            await db.invoices.delete_many({})
            await db.validation_errors.delete_many({})
            await db.processing_history.delete_many({})
            return r1.deleted_count
        except Exception as e:
            logger.error(f"[MongoDB] Error clearing collections: {e}")
            return 0


mongo_manager = MongoDBManager()

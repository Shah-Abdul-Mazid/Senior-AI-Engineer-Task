"""Automated tests for Task 5 & Task 7: MongoDB Database & Search (Metadata, Extracted Text,
Structured Results, Validation Errors, Processing History, Keyword-based Filtering & Semantic Search).
"""
import pytest
import uuid
from datetime import datetime
from app.core.mongodb import mongo_manager
from app.services.search_service import search_service
from app.schemas.document import SearchRequest


@pytest.mark.asyncio
async def test_mongodb_connection():
    """Verify live connection to MongoDB Atlas database with escaped credentials."""
    connected = await mongo_manager.connect()
    assert connected is True, "MongoDB Atlas should connect successfully"
    assert mongo_manager.is_connected is True
    db = mongo_manager.get_db()
    assert db is not None


@pytest.mark.asyncio
async def test_mongodb_document_crud_and_history():
    """Verify storing document metadata, raw text, validation errors, and processing history in MongoDB."""
    test_id = f"test-doc-{uuid.uuid4()}"

    # 1. Save document metadata & raw text
    doc_saved = await mongo_manager.save_document({
        "document_id": test_id,
        "filename": "invoice_sample_789.pdf",
        "original_filename": "invoice_sample_789.pdf",
        "file_type": "pdf",
        "file_path": f"/tmp/{test_id}.pdf",
        "file_size_bytes": 104857.0,
        "page_count": 2.0,
        "sheet_count": 0.0,
        "raw_text": "Vendor: Acme Global Supplies Inc. Invoice No: AG-2026-9021 Total: $4,580.00",
        "status": "completed",
        "text_embedding": [0.05] * 1536,
    })
    assert doc_saved is True

    # 2. Save structured invoice results & line items
    inv_saved = await mongo_manager.save_invoice({
        "document_id": test_id,
        "invoice_number": "AG-2026-9021",
        "purchase_order_number": "PO-7744",
        "invoice_date": "2026-05-15",
        "supplier_name": "Acme Global Supplies Inc",
        "customer_name": "Enterprise Logistics Corp",
        "subtotal": 4163.64,
        "tax": 416.36,
        "total": 4580.00,
        "currency": "USD",
        "confidence_score": 0.96,
        "line_items": [
            {
                "description": "Industrial Laser Sensor v4",
                "quantity": 2.0,
                "unit_price": 2081.82,
                "amount": 4163.64,
            }
        ],
    })
    assert inv_saved is True

    # 3. Save validation errors
    err_saved = await mongo_manager.save_validation_errors(
        test_id,
        [
            {
                "error_type": "INFO_NOTE",
                "severity": "info",
                "field_name": "tax",
                "message": "Tax mathematically verified",
                "resolved": False,
            }
        ],
    )
    assert err_saved is True

    # 4. Record processing history
    hist_saved = await mongo_manager.record_processing_history(
        document_id=test_id,
        status="completed",
        stage="ocr_and_ai_extraction",
        attempt_count=1,
        duration_ms=842.5,
    )
    assert hist_saved is True

    # 5. Retrieve full document package
    full_data = await mongo_manager.get_document_full(test_id)
    assert full_data is not None
    assert full_data["document"]["filename"] == "invoice_sample_789.pdf"
    assert full_data["invoice"]["invoice_number"] == "AG-2026-9021"
    assert full_data["invoice"]["total"] == 4580.00
    assert len(full_data["validation_errors"]) == 1
    assert len(full_data["processing_history"]) >= 1

    # Cleanup test document
    db = mongo_manager.get_db()
    if db is not None:
        await db.documents.delete_one({"document_id": test_id})
        await db.invoices.delete_one({"document_id": test_id})
        await db.validation_errors.delete_many({"document_id": test_id})
        await db.processing_history.delete_many({"document_id": test_id})


@pytest.mark.asyncio
async def test_mongodb_keyword_and_semantic_search():
    """Verify keyword filtering and semantic search on MongoDB Atlas."""
    test_id = str(uuid.uuid4())

    await mongo_manager.save_document({
        "document_id": test_id,
        "filename": "logistics_freight_q3.png",
        "file_type": "png",
        "raw_text": "Freight & Cargo International Bill of Lading BL-448109 Total amount due $12,950.00",
        "status": "completed",
        "text_embedding": [0.12] * 1536,
    })
    await mongo_manager.save_invoice({
        "document_id": test_id,
        "invoice_number": "BL-448109",
        "supplier_name": "Freight & Cargo International",
        "customer_name": "Pacific Import Distributors",
        "total": 12950.00,
        "currency": "USD",
        "invoice_date": "2026-08-20",
    })

    # Test 1: Keyword exact search by invoice number
    keyword_hits = await mongo_manager.search(query="BL-448109", search_type="keyword")
    assert len(keyword_hits) >= 1
    found = any(h["document_id"] == test_id for h in keyword_hits)
    assert found is True

    # Test 2: Keyword search by vendor name
    vendor_hits = await mongo_manager.search(query="Freight Cargo", search_type="keyword")
    assert len(vendor_hits) >= 1

    # Test 3: Semantic search with vector query
    fake_query_vec = [0.12] * 1536
    semantic_hits = await mongo_manager.search(
        query="shipping containers freight bill",
        search_type="semantic",
        query_embedding=fake_query_vec,
    )
    assert len(semantic_hits) >= 1
    top_hit = next(h for h in semantic_hits if h["document_id"] == test_id)
    assert top_hit["score"] > 0.9  # Exact cosine similarity match

    # Test 4: End-to-end integration via SearchService
    search_req = SearchRequest(
        query="BL-448109",
        search_type="keyword",
        top_k=5,
    )
    # Using dummy session; search_service routes to MongoDB first
    resp = await search_service.search(search_req, db=None)
    assert resp.total_results >= 1
    assert any(str(r.invoice_number) == "BL-448109" for r in resp.results)

    # Cleanup
    db = mongo_manager.get_db()
    if db is not None:
        await db.documents.delete_one({"document_id": test_id})
        await db.invoices.delete_one({"document_id": test_id})

"""Document processing, retrieval, correction, and search REST API endpoints."""
import os
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.validation_error import ValidationError
from app.schemas.document import (
    DocumentUploadResponse,
    BatchUploadResponse,
    ProcessingStatusResponse,
    DocumentResultResponse,
    DocumentListItem,
    CorrectionRequest,
    SearchRequest,
    SearchResponse,
)
from app.services.document_service import document_service
from app.services.search_service import search_service
from app.services.validation_service import validation_service
from app.services.eval_service import eval_service

router = APIRouter(prefix="/documents", tags=["Document Intelligence"])


@router.get("/dataset/stats")
async def get_dataset_statistics():
    """Retrieve statistics about the business document benchmark dataset in uploads/."""
    return eval_service.get_dataset_stats()


@router.post("/dataset/evaluate")
async def run_dataset_evaluation(
    sample_size: int = Query(25, ge=1, le=100, description="Number of documents to benchmark"),
):
    """
    Task 7: Evaluates extraction accuracy, processing time, success rate, and failure rate
    against the labeled dataset in uploads/.
    """
    return await eval_service.evaluate_dataset(sample_limit=sample_size)


@router.post("/load-sample", response_model=DocumentUploadResponse)
async def load_sample_document(
    filename: str = Query(..., description="Filename from uploads/ or batch_1/"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """Loads a benchmark invoice (TIFF, JPG, XLSX, PDF) directly from dataset into the queue and processes it."""
    import glob, shutil
    from app.storage.file_store import get_upload_dir
    from app.models.document import FileType, Document, DocumentStatus
    from app.models.processing_job import ProcessingJob, JobStatus

    up_dir = get_upload_dir()
    matches = glob.glob(str(up_dir / filename))
    if not matches:
        matches = glob.glob(str(up_dir / "**" / filename), recursive=True)
    if not matches:
        matches = glob.glob(f"uploads/**/{filename}", recursive=True)

    if not matches:
        raise HTTPException(status_code=404, detail=f"Sample file '{filename}' not found in dataset.")

    src_path = matches[0]
    raw_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "tiff"
    ext = "tiff" if raw_ext == "tif" else raw_ext

    try:
        file_type_enum = FileType(ext)
    except ValueError:
        file_type_enum = FileType.TIFF

    file_size = os.path.getsize(src_path)

    doc = Document(
        filename=os.path.basename(src_path),
        original_filename=filename,
        file_type=file_type_enum,
        file_path=src_path,
        file_size_bytes=float(file_size),
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    job = ProcessingJob(
        document_id=doc.id,
        status=JobStatus.PENDING,
        stage="queued",
        attempt_count=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(doc)

    if background_tasks:
        background_tasks.add_task(document_service.process_document_pipeline, doc.id)
    else:
        await document_service.process_document_pipeline(doc.id)

    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.original_filename,
        file_type=ext,
        status=doc.status,
        message=f"Sample '{filename}' queued and processed.",
    )


@router.post("/upload", response_model=BatchUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts single or batch upload of business documents (PDF, JPG, PNG, TIFF, XLSX, XLS, CSV).
    Saves files securely and enqueues background OCR and AI processing.
    """
    uploaded: List[DocumentUploadResponse] = []
    failed: List[dict] = []

    for file in files:
        try:
            resp = await document_service.ingest_document(file, db)
            uploaded.append(resp)
            # Enqueue asynchronous processing pipeline
            background_tasks.add_task(
                document_service.process_document_pipeline,
                resp.document_id,
            )
        except Exception as e:
            failed.append({
                "filename": file.filename or "unknown",
                "error": str(e),
            })

    return BatchUploadResponse(
        uploaded=uploaded,
        failed=failed,
        total=len(files),
        successful=len(uploaded),
    )


@router.get("/", response_model=List[DocumentListItem])
async def list_documents(
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all processed and queued documents with status and summary metrics."""
    stmt = (
        select(Document, Invoice)
        .outerjoin(Invoice, Document.id == Invoice.document_id)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for doc, inv in rows:
        items.append(
            DocumentListItem(
                document_id=doc.id,
                filename=doc.original_filename or doc.filename,
                file_type=doc.file_type.value if hasattr(doc.file_type, "value") else str(doc.file_type),
                status=doc.status,
                invoice_number=inv.invoice_number if inv else None,
                supplier_name=inv.supplier_name if inv else None,
                total=inv.total if inv else None,
                currency=inv.currency if inv else None,
                has_errors=(doc.status == DocumentStatus.REQUIRES_REVIEW or doc.status == DocumentStatus.FAILED),
                created_at=doc.created_at,
            )
        )
    return items


@router.get("/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Check asynchronous OCR & extraction progress (useful for frontend polling / SSE)."""
    status_resp = await document_service.get_document_status(document_id, db)
    if not status_resp:
        raise HTTPException(status_code=404, detail="Document not found")
    return status_resp


@router.get("/{document_id}/result", response_model=DocumentResultResponse)
async def get_document_result(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full structured extraction results, line items, and validation errors."""
    result = await document_service.get_document_result(document_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.patch("/{document_id}/corrections", response_model=DocumentResultResponse)
async def submit_corrections(
    document_id: UUID,
    payload: CorrectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit manual human corrections for flagged fields and update validation state."""
    try:
        updated = await document_service.apply_corrections(document_id, payload, db)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply corrections: {str(e)}")


@router.post("/{document_id}/retry", response_model=DocumentUploadResponse)
async def retry_processing(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Reprocess a failed or stuck document job."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = DocumentStatus.PENDING
    doc.error_message = None
    await db.commit()

    background_tasks.add_task(
        document_service.process_document_pipeline,
        document_id,
    )

    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.original_filename or doc.filename,
        file_type=doc.file_type.value if hasattr(doc.file_type, "value") else str(doc.file_type),
        status=doc.status,
        message="Document processing re-queued successfully.",
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute keyword, semantic vector, or hybrid search across documents."""
    return await search_service.search(payload, db)


@router.post("/cross-verify")
async def cross_verify_documents(
    doc_id_a: UUID = Query(..., description="ID of first document (e.g. PDF invoice)"),
    doc_id_b: UUID = Query(..., description="ID of second document (e.g. Excel spreadsheet or companion PDF)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Performs cross-verification between two documents.
    Compares invoice numbers, totals, dates, and suppliers to find financial discrepancies.
    """
    doc_a = await document_service.get_document_result(doc_id_a, db)
    doc_b = await document_service.get_document_result(doc_id_b, db)

    if not doc_a or not doc_b:
        raise HTTPException(status_code=404, detail="One or both documents not found")

    if not doc_a.invoice or not doc_b.invoice:
        raise HTTPException(status_code=400, detail="Both documents must be processed with extracted invoice data")

    from app.schemas.document import ExtractedInvoice
    inv_a = ExtractedInvoice(**doc_a.invoice.model_dump())
    inv_b = ExtractedInvoice(**doc_b.invoice.model_dump())

    verification = validation_service.cross_verify_documents(
        doc_a_name=doc_a.filename,
        invoice_a=inv_a,
        doc_b_name=doc_b.filename,
        invoice_b=inv_b,
    )
    return verification


@router.delete("/clear")
async def clear_documents(
    status: Optional[str] = Query(None, description="Filter: 'requires_review', 'failed', 'completed', or 'all'"),
    db: AsyncSession = Depends(get_db),
):
    """
    Clears documents from the queue/database.
    Can clear 'all', or specifically 'requires_review', 'failed', etc.
    """
    count = await document_service.delete_documents(db, status_filter=status)
    return {
        "status": "success",
        "deleted_count": count,
        "message": f"Successfully cleared {count} document(s)" + (f" with status '{status}'." if status else "."),
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Deletes a single document and all its associated invoices, line items, and errors."""
    success = await document_service.delete_document(document_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "status": "success",
        "message": "Document deleted successfully",
        "document_id": str(document_id),
    }

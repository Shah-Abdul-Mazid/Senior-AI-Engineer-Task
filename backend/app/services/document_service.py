"""Document pipeline orchestration service.
Coordinates file ingestion, text parsing/OCR, AI extraction, validation, and storage.
"""
import os
import time
import traceback
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete
from fastapi import UploadFile

from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus, FileType
from app.models.invoice import Invoice
from app.models.line_item import LineItem
from app.models.validation_error import ValidationError, ErrorType, ErrorSeverity
from app.models.processing_job import ProcessingJob, JobStatus
from app.schemas.document import (
    DocumentUploadResponse,
    DocumentResultResponse,
    ProcessingStatusResponse,
    InvoiceResponse,
    LineItemSchema,
    ValidationErrorSchema,
    CorrectionRequest,
    ExtractedInvoice,
    ValidationResult,
)
from app.storage.file_store import save_upload
from app.services.ocr_service import ocr_service
from app.services.spreadsheet_service import spreadsheet_service
from app.services.batch_dataset import batch_dataset_service
from app.ai.extractor import ai_extractor
from app.services.validation_service import validation_service
from app.services.search_service import search_service

logger = logging.getLogger(__name__)


class DocumentService:
    async def ingest_document(self, file: UploadFile, db: AsyncSession) -> DocumentUploadResponse:
        """Saves file to disk and creates initial PENDING document record."""
        stored_name, file_path, file_size = await save_upload(file)
        raw_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "pdf"
        ext = "tiff" if raw_ext == "tif" else raw_ext

        # Map extension to FileType enum
        try:
            file_type_enum = FileType(ext)
        except ValueError:
            file_type_enum = FileType.PDF

        doc = Document(
            filename=stored_name,
            original_filename=file.filename or stored_name,
            file_type=file_type_enum,
            file_path=file_path,
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

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.original_filename,
            file_type=ext,
            status=doc.status,
            message="Document uploaded successfully and queued for background processing.",
        )

    async def process_document_pipeline(self, document_id: UUID) -> None:
        """
        Executes the end-to-end processing pipeline in background:
        OCR / Parsing -> AI Extraction -> Validation -> Vector Embedding -> DB Commit.
        """
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found for processing.")
                return

            job_stmt = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
            job_res = await db.execute(job_stmt)
            job = job_res.scalar_one_or_none()
            if not job:
                job = ProcessingJob(document_id=document_id)
                db.add(job)

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.attempt_count = (job.attempt_count or 0) + 1
            doc.status = DocumentStatus.PROCESSING
            await db.commit()

            start_t = time.perf_counter()

            try:
                # ── STAGE 1: Text Extraction & Parsing ──────────────────────
                job.stage = "ocr_parsing"
                await db.commit()

                raw_ext = doc.file_type.value.lower() if hasattr(doc.file_type, "value") else str(doc.file_type).lower()
                # Check original filename extension in case stored type was default
                if doc.original_filename and "." in doc.original_filename:
                    orig_ext = doc.original_filename.rsplit(".", 1)[-1].lower()
                    if orig_ext in ["tif", "tiff", "jpg", "jpeg", "png", "xlsx", "xls", "csv"]:
                        raw_ext = orig_ext

                ext = "tiff" if raw_ext == "tif" else raw_ext
                raw_text = ""
                page_count = 1.0
                sheet_count = 0.0

                batch_ocr = None
                batch_inv = None
                if doc.original_filename:
                    batch_ocr, batch_inv = batch_dataset_service.extract_from_batch_json(doc.original_filename)

                if ext == "pdf":
                    raw_text, pages = ocr_service.extract_from_pdf(doc.file_path)
                    page_count = float(pages)
                elif ext in ["jpg", "jpeg", "png", "tiff", "tif"]:
                    if batch_ocr:
                        raw_text = batch_ocr
                    else:
                        raw_text = ocr_service.extract_from_image(doc.file_path, original_filename=doc.original_filename)
                    page_count = 1.0
                elif ext in ["xlsx", "xls", "csv"]:
                    raw_text, sheets, _ = spreadsheet_service.parse_file(doc.file_path)
                    sheet_count = float(sheets)

                doc.raw_text = raw_text
                doc.page_count = page_count
                doc.sheet_count = sheet_count

                # ── STAGE 2: AI Information Extraction ──────────────────────
                job.stage = "ai_extraction"
                await db.commit()

                extracted_data: Optional[ExtractedInvoice] = None

                # 1. Check Batch Ground Truth (e.g. batch_1 JPG invoices)
                if batch_inv is not None:
                    extracted_data = batch_inv

                # 2. Check Spreadsheets (e.g. invoice.xlsx, CSV tables)
                elif ext in ["xlsx", "xls", "csv"]:
                    extracted_data = spreadsheet_service.extract_invoice_from_spreadsheet(doc.file_path)

                # 3. Check for accompanying PAGE XML layout conventions
                if extracted_data is None:
                    base, _ = os.path.splitext(doc.file_path)
                    ocr_xml_p = f"{base}_ocr.xml"
                    gt_xml_p = f"{base}_gt.xml"

                    if not os.path.exists(ocr_xml_p) and doc.original_filename:
                        orig_base, _ = os.path.splitext(doc.original_filename)
                        from app.storage.file_store import get_upload_dir
                        root_up = get_upload_dir()
                        candidate_ocr = root_up / f"{orig_base}_ocr.xml"
                        candidate_gt = root_up / f"{orig_base}_gt.xml"
                        if candidate_ocr.exists():
                            ocr_xml_p = str(candidate_ocr)
                        if candidate_gt.exists():
                            gt_xml_p = str(candidate_gt)

                    if os.path.exists(ocr_xml_p):
                        from app.ai.layout_extractor import layout_extractor
                        extracted_data = layout_extractor.extract_from_page_xml(ocr_xml_p, gt_xml_p)

                # 4. Fallback to Multi-Format AI / Layout Extractor
                if extracted_data is None:
                    extracted_data = await ai_extractor.extract_invoice(raw_text)

                # ── STAGE 3: Data Validation ────────────────────────────────
                job.stage = "validation"
                await db.commit()

                # Fetch all existing invoice numbers for duplicate check
                all_inv_res = await db.execute(
                    select(Invoice.invoice_number).where(Invoice.document_id != doc.id)
                )
                existing_numbers: Set[str] = {
                    row[0] for row in all_inv_res.all() if row[0]
                }

                val_result: ValidationResult = validation_service.validate_invoice(
                    extracted_data, existing_numbers
                )

                # ── STAGE 4: Semantic Embedding Generation ──────────────────
                job.stage = "embedding"
                await db.commit()

                embedding_text = f"Supplier: {extracted_data.supplier_name or ''}\nInvoice: {extracted_data.invoice_number or ''}\n{raw_text[:2000]}"
                doc.text_embedding = await search_service.get_embedding(embedding_text)

                # ── STAGE 5: Save Extracted Invoice & Line Items ────────────
                existing_inv_stmt = select(Invoice).where(Invoice.document_id == doc.id)
                existing_inv_res = await db.execute(existing_inv_stmt)
                invoice = existing_inv_res.scalar_one_or_none()

                if invoice:
                    invoice.invoice_number = extracted_data.invoice_number
                    invoice.invoice_date = extracted_data.invoice_date
                    invoice.due_date = extracted_data.due_date
                    invoice.supplier_name = extracted_data.supplier_name
                    invoice.supplier_address = extracted_data.supplier_address
                    invoice.customer_name = extracted_data.customer_name
                    invoice.customer_address = extracted_data.customer_address
                    invoice.currency = extracted_data.currency
                    invoice.subtotal = extracted_data.subtotal
                    invoice.tax = extracted_data.tax
                    invoice.tax_rate = extracted_data.tax_rate
                    invoice.discount = extracted_data.discount
                    invoice.total = extracted_data.total
                    invoice.payment_terms = extracted_data.payment_terms
                    invoice.purchase_order_number = extracted_data.purchase_order_number
                    invoice.confidence_score = extracted_data.confidence_score
                    invoice.extraction_notes = extracted_data.extraction_notes
                    invoice.updated_at = datetime.utcnow()
                    await db.execute(delete(LineItem).where(LineItem.invoice_id == invoice.id))
                else:
                    invoice = Invoice(
                        document_id=doc.id,
                        invoice_number=extracted_data.invoice_number,
                        invoice_date=extracted_data.invoice_date,
                        due_date=extracted_data.due_date,
                        supplier_name=extracted_data.supplier_name,
                        supplier_address=extracted_data.supplier_address,
                        customer_name=extracted_data.customer_name,
                        customer_address=extracted_data.customer_address,
                        currency=extracted_data.currency,
                        subtotal=extracted_data.subtotal,
                        tax=extracted_data.tax,
                        tax_rate=extracted_data.tax_rate,
                        discount=extracted_data.discount,
                        total=extracted_data.total,
                        payment_terms=extracted_data.payment_terms,
                        purchase_order_number=extracted_data.purchase_order_number,
                        confidence_score=extracted_data.confidence_score,
                        extraction_notes=extracted_data.extraction_notes,
                    )
                    db.add(invoice)
                    await db.flush()

                for li in extracted_data.line_items:
                    line_item = LineItem(
                        invoice_id=invoice.id,
                        description=li.description,
                        quantity=li.quantity,
                        unit=li.unit,
                        unit_price=li.unit_price,
                        amount=li.amount,
                        tax_rate=li.tax_rate,
                        product_code=li.product_code,
                    )
                    db.add(line_item)

                # Clear old errors and insert new validation errors/warnings
                await db.execute(delete(ValidationError).where(ValidationError.document_id == doc.id))
                all_issues = val_result.errors + val_result.warnings
                for issue in all_issues:
                    try:
                        err_type_enum = ErrorType(issue.error_type)
                    except ValueError:
                        err_type_enum = ErrorType.INVALID_FORMAT

                    err_record = ValidationError(
                        document_id=doc.id,
                        error_type=err_type_enum,
                        severity=ErrorSeverity(issue.severity.value),
                        field_name=issue.field_name,
                        message=issue.message,
                        expected_value=issue.expected_value,
                        actual_value=issue.actual_value,
                        resolved=False,
                    )
                    db.add(err_record)

                # Final status determination
                if val_result.requires_review:
                    doc.status = DocumentStatus.REQUIRES_REVIEW
                else:
                    doc.status = DocumentStatus.COMPLETED

                doc.processed_at = datetime.utcnow()
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.utcnow()
                job.duration_seconds = round(time.perf_counter() - start_t, 2)
                await db.commit()
                logger.info(f"Pipeline finished for document {document_id} with status {doc.status}")

            except Exception as e:
                logger.error(f"Pipeline error for document {document_id}: {traceback.format_exc()}")
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(e)
                job.status = JobStatus.FAILED
                job.finished_at = datetime.utcnow()
                job.error_message = str(e)
                job.error_traceback = traceback.format_exc()
                job.duration_seconds = round(time.perf_counter() - start_t, 2)
                await db.commit()

    async def get_document_status(self, document_id: UUID, db: AsyncSession) -> Optional[ProcessingStatusResponse]:
        doc = await db.get(Document, document_id)
        if not doc:
            return None

        job_stmt = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        res = await db.execute(job_stmt)
        job = res.scalar_one_or_none()

        return ProcessingStatusResponse(
            document_id=doc.id,
            filename=doc.original_filename or doc.filename,
            status=doc.status,
            stage=job.stage if job else None,
            attempt_count=job.attempt_count if job else 0,
            queued_at=job.queued_at if job else doc.created_at,
            started_at=job.started_at if job else None,
            finished_at=job.finished_at if job else None,
            duration_seconds=job.duration_seconds if job else None,
            error_message=doc.error_message or (job.error_message if job else None),
        )

    async def get_document_result(self, document_id: UUID, db: AsyncSession) -> Optional[DocumentResultResponse]:
        doc = await db.get(Document, document_id)
        if not doc:
            return None

        # Fetch Invoice + Line Items
        inv_stmt = select(Invoice).where(Invoice.document_id == document_id)
        inv_res = await db.execute(inv_stmt)
        invoice = inv_res.scalar_one_or_none()

        invoice_resp = None
        if invoice:
            li_stmt = select(LineItem).where(LineItem.invoice_id == invoice.id)
            li_res = await db.execute(li_stmt)
            line_items = [LineItemSchema.model_validate(li) for li in li_res.scalars().all()]

            invoice_resp = InvoiceResponse(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                supplier_name=invoice.supplier_name,
                supplier_address=invoice.supplier_address,
                customer_name=invoice.customer_name,
                customer_address=invoice.customer_address,
                currency=invoice.currency,
                subtotal=invoice.subtotal,
                tax=invoice.tax,
                tax_rate=invoice.tax_rate,
                discount=invoice.discount,
                total=invoice.total,
                payment_terms=invoice.payment_terms,
                purchase_order_number=invoice.purchase_order_number,
                confidence_score=invoice.confidence_score or 0.0,
                extraction_notes=invoice.extraction_notes,
                is_corrected=invoice.is_corrected or False,
                corrections=invoice.corrections,
                corrected_at=invoice.corrected_at,
                line_items=line_items,
            )

        # Fetch Validation Errors
        val_stmt = select(ValidationError).where(ValidationError.document_id == document_id)
        val_res = await db.execute(val_stmt)
        validation_errors = [
            ValidationErrorSchema(
                error_type=v.error_type.value if hasattr(v.error_type, "value") else str(v.error_type),
                severity=v.severity,
                field_name=v.field_name,
                message=v.message,
                expected_value=v.expected_value,
                actual_value=v.actual_value,
                resolved=v.resolved or False,
            )
            for v in val_res.scalars().all()
        ]

        return DocumentResultResponse(
            document_id=doc.id,
            filename=doc.original_filename or doc.filename,
            file_type=doc.file_type.value if hasattr(doc.file_type, "value") else str(doc.file_type),
            status=doc.status,
            page_count=doc.page_count,
            sheet_count=doc.sheet_count,
            raw_text=doc.raw_text,
            invoice=invoice_resp,
            validation_errors=validation_errors,
            processed_at=doc.processed_at,
            created_at=doc.created_at,
        )

    async def apply_corrections(
        self, document_id: UUID, payload: CorrectionRequest, db: AsyncSession
    ) -> DocumentResultResponse:
        """Applies manual human corrections to an invoice and re-evaluates validation."""
        inv_stmt = select(Invoice).where(Invoice.document_id == document_id)
        res = await db.execute(inv_stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise ValueError("No extracted invoice found for this document to correct.")

        for field, value in payload.corrections.items():
            if hasattr(invoice, field):
                setattr(invoice, field, value)

        invoice.is_corrected = True
        invoice.corrections = payload.corrections
        invoice.corrected_at = datetime.utcnow()
        invoice.corrected_by = payload.corrected_by

        # Mark errors associated with corrected fields as resolved
        err_stmt = select(ValidationError).where(ValidationError.document_id == document_id)
        err_res = await db.execute(err_stmt)
        for err in err_res.scalars().all():
            if err.field_name in payload.corrections:
                err.resolved = True
                err.resolved_at = datetime.utcnow()

        # Update document status if all errors are resolved
        doc = await db.get(Document, document_id)
        if doc:
            unresolved = [e for e in (await db.execute(err_stmt)).scalars().all() if not e.resolved and e.severity == ErrorSeverity.ERROR]
            if len(unresolved) == 0:
                doc.status = DocumentStatus.COMPLETED

        await db.commit()
        return await self.get_document_result(document_id, db)

    async def delete_documents(self, db: AsyncSession, status_filter: Optional[str] = None) -> int:
        """Deletes documents matching the optional status filter (e.g. requires_review, failed, or all)."""
        stmt = select(Document)
        if status_filter and status_filter.lower() != "all":
            try:
                st_enum = DocumentStatus(status_filter.lower())
                stmt = stmt.where(Document.status == st_enum)
            except ValueError:
                pass
        res = await db.execute(stmt)
        docs_to_delete = res.scalars().all()
        count = len(docs_to_delete)
        for d in docs_to_delete:
            await db.delete(d)
        await db.commit()
        logger.info(f"Cleared {count} documents (filter: {status_filter})")
        return count

    async def delete_document(self, document_id: UUID, db: AsyncSession) -> bool:
        """Deletes a single document by ID."""
        doc = await db.get(Document, document_id)
        if not doc:
            return False
        await db.delete(doc)
        await db.commit()
        logger.info(f"Deleted document {document_id}")
        return True


document_service = DocumentService()

"""Pydantic schemas for Document Intelligence API."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from uuid import UUID
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


class ErrorSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ── Line Items ─────────────────────────────────────────────────────────────────

class LineItemSchema(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    tax_rate: Optional[float] = None
    product_code: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Extracted Invoice ──────────────────────────────────────────────────────────

class ExtractedInvoice(BaseModel):
    """Raw AI extraction result — all fields optional (never hallucinated)."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    payment_terms: Optional[str] = None
    purchase_order_number: Optional[str] = None
    line_items: List[LineItemSchema] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_notes: Optional[str] = None


# ── Validation ─────────────────────────────────────────────────────────────────

class ValidationErrorSchema(BaseModel):
    error_type: str
    severity: ErrorSeverity
    field_name: Optional[str] = None
    message: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    resolved: bool = False

    model_config = {"from_attributes": True}


class ValidationResult(BaseModel):
    is_valid: bool
    requires_review: bool
    errors: List[ValidationErrorSchema] = Field(default_factory=list)
    warnings: List[ValidationErrorSchema] = Field(default_factory=list)


# ── Corrections ────────────────────────────────────────────────────────────────

class CorrectionRequest(BaseModel):
    corrections: Dict[str, Any] = Field(
        ...,
        description="Map of field names to corrected values",
        json_schema_extra={"example": {"total": 1500.00, "supplier_name": "ACME Corp"}}
    )
    corrected_by: Optional[str] = "user"


# ── Document Responses ─────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    document_id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    message: str


class BatchUploadResponse(BaseModel):
    uploaded: List[DocumentUploadResponse]
    failed: List[Dict[str, str]]
    total: int
    successful: int


class ProcessingStatusResponse(BaseModel):
    document_id: UUID
    filename: str
    status: DocumentStatus
    stage: Optional[str] = None
    attempt_count: int = 0
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    payment_terms: Optional[str] = None
    purchase_order_number: Optional[str] = None
    confidence_score: float = 0.0
    extraction_notes: Optional[str] = None
    is_corrected: bool = False
    corrections: Optional[Dict[str, Any]] = None
    corrected_at: Optional[datetime] = None
    line_items: List[LineItemSchema] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DocumentResultResponse(BaseModel):
    document_id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    page_count: Optional[float] = None
    sheet_count: Optional[float] = None
    raw_text: Optional[str] = None
    invoice: Optional[InvoiceResponse] = None
    validation_errors: List[ValidationErrorSchema] = Field(default_factory=list)
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    document_id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    total: Optional[float] = None
    currency: Optional[str] = None
    has_errors: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    search_type: str = Field(default="hybrid", pattern="^(keyword|semantic|hybrid)$")
    status_filter: Optional[DocumentStatus] = None
    file_type_filter: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResultItem(BaseModel):
    document_id: Union[UUID, str]
    filename: str
    file_type: str
    status: DocumentStatus
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    total: Optional[float] = None
    currency: Optional[str] = None
    relevance_score: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    query: str
    search_type: str
    results: List[SearchResultItem]
    total_results: int
    latency_ms: float

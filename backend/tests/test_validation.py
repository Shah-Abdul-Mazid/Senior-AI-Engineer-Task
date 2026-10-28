"""Automated tests for Document Intelligence Data Validation Engine (Task 3)."""
from datetime import date
from app.schemas.document import ExtractedInvoice, LineItemSchema
from app.services.validation_service import validation_service


def test_validation_clean_invoice():
    """Test that a mathematically sound and complete invoice passes validation."""
    invoice = ExtractedInvoice(
        invoice_number="INV-2026-001",
        invoice_date=date(2026, 10, 20),
        supplier_name="Acme Industrial Supplies",
        customer_name="Tech Global Corp",
        currency="USD",
        subtotal=100.00,
        tax=10.00,
        discount=0.00,
        total=110.00,
        line_items=[
            LineItemSchema(description="Widget A", quantity=2, unit_price=25.00, amount=50.00),
            LineItemSchema(description="Widget B", quantity=1, unit_price=50.00, amount=50.00),
        ],
        confidence_score=0.95,
    )
    result = validation_service.validate_invoice(invoice)
    assert result.is_valid is True
    assert result.requires_review is False
    assert len(result.errors) == 0


def test_validation_math_mismatch():
    """Test that subtotal + tax != total is flagged as an ERROR."""
    invoice = ExtractedInvoice(
        invoice_number="INV-2026-002",
        invoice_date=date(2026, 10, 20),
        supplier_name="Acme Corp",
        subtotal=100.00,
        tax=10.00,
        total=150.00,  # Incorrect total (should be 110.00)
        confidence_score=0.90,
    )
    result = validation_service.validate_invoice(invoice)
    assert result.is_valid is False
    assert result.requires_review is True
    error_types = [e.error_type for e in result.errors]
    assert "math_mismatch" in error_types


def test_validation_missing_required_fields():
    """Test that missing mandatory fields (invoice_number, date, total) trigger errors."""
    invoice = ExtractedInvoice(
        invoice_number=None,
        invoice_date=None,
        supplier_name=None,
        total=None,
        confidence_score=0.8,
    )
    result = validation_service.validate_invoice(invoice)
    assert result.is_valid is False
    assert result.requires_review is True
    missing_fields = [e.field_name for e in result.errors if e.error_type == "missing_field"]
    assert "invoice_number" in missing_fields
    assert "invoice_date" in missing_fields
    assert "supplier_name" in missing_fields
    assert "total" in missing_fields


def test_validation_duplicate_invoice():
    """Test detection of duplicate invoice numbers against existing records."""
    existing_invoices = {"INV-EXISTING-999", "INV-2026-001"}
    invoice = ExtractedInvoice(
        invoice_number="INV-EXISTING-999",
        invoice_date=date(2026, 10, 20),
        supplier_name="Global Vendor",
        subtotal=100.0,
        tax=0.0,
        total=100.0,
        confidence_score=0.9,
    )
    result = validation_service.validate_invoice(invoice, existing_invoice_numbers=existing_invoices)
    assert result.is_valid is False
    assert any(e.error_type == "duplicate_invoice" for e in result.errors)


def test_validation_line_items_mismatch():
    """Test warning when line items sum does not equal subtotal."""
    invoice = ExtractedInvoice(
        invoice_number="INV-2026-003",
        invoice_date=date(2026, 10, 20),
        supplier_name="Acme Corp",
        subtotal=100.00,
        tax=10.00,
        total=110.00,
        line_items=[
            LineItemSchema(description="Item 1", amount=30.00),
            LineItemSchema(description="Item 2", amount=40.00),  # Sum is 70, not 100
        ],
        confidence_score=0.95,
    )
    result = validation_service.validate_invoice(invoice)
    assert any(w.error_type == "line_item_mismatch" for w in result.warnings)


def test_cross_verification_matching_documents():
    """Test cross verification between two documents with identical numbers."""
    inv_a = ExtractedInvoice(
        invoice_number="INV-100",
        invoice_date=date(2026, 1, 15),
        supplier_name="Supplier Alpha",
        total=500.00,
    )
    inv_b = ExtractedInvoice(
        invoice_number="INV-100",
        invoice_date=date(2026, 1, 15),
        supplier_name="Supplier Alpha",
        total=500.00,
    )
    res = validation_service.cross_verify_documents("invoice.pdf", inv_a, "report.xlsx", inv_b)
    assert res["is_matched"] is True
    assert res["match_score"] == 1.0
    assert len(res["discrepancies"]) == 0


def test_cross_verification_mismatch():
    """Test cross verification when amounts or invoice numbers diverge."""
    inv_pdf = ExtractedInvoice(
        invoice_number="INV-100",
        invoice_date=date(2026, 1, 15),
        total=500.00,
    )
    inv_excel = ExtractedInvoice(
        invoice_number="INV-100",
        invoice_date=date(2026, 1, 15),
        total=550.00,  # $50 discrepancy
    )
    res = validation_service.cross_verify_documents("invoice.pdf", inv_pdf, "statement.xlsx", inv_excel)
    assert res["is_matched"] is False
    assert res["discrepancies_count"] >= 1
    assert res["discrepancies"][0]["field"] == "total"

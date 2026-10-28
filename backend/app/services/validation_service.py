"""Data Validation Engine for Document Intelligence.
Validates extracted financial data, performs mathematical checks, checks duplicates,
and handles cross-document (PDF vs PDF, PDF vs Excel) verification.
"""
from typing import List, Optional, Set, Dict, Any
from app.schemas.document import ExtractedInvoice, ValidationResult, ValidationErrorSchema, ErrorSeverity
from app.core.config import settings

TOLERANCE = 0.02  # Floating point rounding allowance ($0.02)


class ValidationService:
    def validate_invoice(
        self,
        invoice: ExtractedInvoice,
        existing_invoice_numbers: Optional[Set[str]] = None,
    ) -> ValidationResult:
        """
        Runs comprehensive validation rules against an extracted invoice:
        1. Required fields presence
        2. Non-negative numeric values
        3. Mathematical consistency: subtotal + tax == total (within tolerance)
        4. Line items sum consistency: sum(line_item.amount) == subtotal
        5. Duplicate invoice number detection
        6. Confidence score threshold
        """
        errors: List[ValidationErrorSchema] = []
        warnings: List[ValidationErrorSchema] = []

        # 1. Missing Required Fields
        required_fields = [
            ("invoice_number", "Invoice Number"),
            ("invoice_date", "Invoice Date"),
            ("supplier_name", "Supplier / Vendor Name"),
            ("total", "Total Amount"),
        ]
        for attr, label in required_fields:
            val = getattr(invoice, attr)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(
                    ValidationErrorSchema(
                        error_type="missing_field",
                        severity=ErrorSeverity.ERROR,
                        field_name=attr,
                        message=f"Mandatory field '{label}' is missing from the document.",
                        expected_value="Non-empty value",
                        actual_value="null",
                    )
                )

        # 2. Negative Values Check
        for attr in ["subtotal", "tax", "total", "discount"]:
            val = getattr(invoice, attr)
            if val is not None and val < 0:
                errors.append(
                    ValidationErrorSchema(
                        error_type="negative_value",
                        severity=ErrorSeverity.ERROR,
                        field_name=attr,
                        message=f"Field '{attr}' cannot be negative ({val}).",
                        expected_value=">= 0.0",
                        actual_value=str(val),
                    )
                )

        # 3. Mathematical Consistency: subtotal + tax (+/- discount) == total
        if invoice.total is not None and invoice.subtotal is not None:
            tax = invoice.tax or 0.0
            discount = invoice.discount or 0.0
            expected_total = round(invoice.subtotal + tax - discount, 2)
            actual_total = round(invoice.total, 2)
            diff = abs(expected_total - actual_total)

            if diff > TOLERANCE:
                errors.append(
                    ValidationErrorSchema(
                        error_type="math_mismatch",
                        severity=ErrorSeverity.ERROR,
                        field_name="total",
                        message=(
                            f"Calculation mismatch: subtotal ({invoice.subtotal}) + tax ({tax}) "
                            f"- discount ({discount}) = {expected_total}, but total is {actual_total} "
                            f"(Difference: {round(diff, 2)})."
                        ),
                        expected_value=str(expected_total),
                        actual_value=str(actual_total),
                    )
                )

        # 4. Line Items Consistency: sum of line items matches subtotal (net) or total (gross)
        if invoice.line_items and (invoice.subtotal is not None or invoice.total is not None):
            line_amounts = [li.amount for li in invoice.line_items if li.amount is not None]
            if len(line_amounts) == len(invoice.line_items):
                items_sum = round(sum(line_amounts), 2)
                subtotal = round(invoice.subtotal, 2) if invoice.subtotal is not None else None
                total = round(invoice.total, 2) if invoice.total is not None else None

                matches_subtotal = subtotal is not None and abs(items_sum - subtotal) <= TOLERANCE
                matches_total = total is not None and abs(items_sum - total) <= TOLERANCE

                if not (matches_subtotal or matches_total):
                    expected_ref = str(subtotal if subtotal is not None else total)
                    warnings.append(
                        ValidationErrorSchema(
                            error_type="line_item_mismatch",
                            severity=ErrorSeverity.WARNING,
                            field_name="subtotal",
                            message=(
                                f"Sum of extracted line items ({items_sum}) does not match "
                                f"subtotal ({subtotal}) or total ({total})."
                            ),
                            expected_value=expected_ref,
                            actual_value=str(items_sum),
                        )
                    )

        # 5. Duplicate Invoice Detection
        if invoice.invoice_number and existing_invoice_numbers:
            clean_num = invoice.invoice_number.strip().upper()
            if clean_num in {n.strip().upper() for n in existing_invoice_numbers}:
                errors.append(
                    ValidationErrorSchema(
                        error_type="duplicate_invoice",
                        severity=ErrorSeverity.ERROR,
                        field_name="invoice_number",
                        message=f"Duplicate invoice detected: Invoice number '{invoice.invoice_number}' already exists in system records.",
                        expected_value="Unique invoice number",
                        actual_value=invoice.invoice_number,
                    )
                )

        # 6. Low Confidence Score Flag
        if invoice.confidence_score < settings.MIN_CONFIDENCE_SCORE:
            warnings.append(
                ValidationErrorSchema(
                    error_type="low_confidence",
                    severity=ErrorSeverity.WARNING,
                    field_name="confidence_score",
                    message=(
                        f"AI extraction confidence is low ({round(invoice.confidence_score, 2)} < {settings.MIN_CONFIDENCE_SCORE}). "
                        "Manual review is strongly advised."
                    ),
                    expected_value=f">= {settings.MIN_CONFIDENCE_SCORE}",
                    actual_value=str(round(invoice.confidence_score, 2)),
                )
            )

        is_valid = len(errors) == 0
        requires_review = len(errors) > 0 or len(warnings) > 0

        return ValidationResult(
            is_valid=is_valid,
            requires_review=requires_review,
            errors=errors,
            warnings=warnings,
        )

    def cross_verify_documents(
        self,
        doc_a_name: str,
        invoice_a: ExtractedInvoice,
        doc_b_name: str,
        invoice_b: ExtractedInvoice,
    ) -> Dict[str, Any]:
        """
        Cross-verification between two documents (e.g. PDF vs PDF or PDF vs Excel/CSV).
        Verifies invoice number, supplier, date, line items, and total amount.
        """
        discrepancies: List[Dict[str, Any]] = []

        # Compare Invoice Number
        if invoice_a.invoice_number and invoice_b.invoice_number:
            if invoice_a.invoice_number.strip().upper() != invoice_b.invoice_number.strip().upper():
                discrepancies.append({
                    "field": "invoice_number",
                    "doc_a": {"name": doc_a_name, "value": invoice_a.invoice_number},
                    "doc_b": {"name": doc_b_name, "value": invoice_b.invoice_number},
                    "status": "mismatch",
                })
        elif invoice_a.invoice_number != invoice_b.invoice_number:
            discrepancies.append({
                "field": "invoice_number",
                "doc_a": {"name": doc_a_name, "value": invoice_a.invoice_number},
                "doc_b": {"name": doc_b_name, "value": invoice_b.invoice_number},
                "status": "missing_in_one",
            })

        # Compare Total Amount
        if invoice_a.total is not None and invoice_b.total is not None:
            diff = abs(invoice_a.total - invoice_b.total)
            if diff > TOLERANCE:
                discrepancies.append({
                    "field": "total",
                    "doc_a": {"name": doc_a_name, "value": invoice_a.total},
                    "doc_b": {"name": doc_b_name, "value": invoice_b.total},
                    "difference": round(diff, 2),
                    "status": "mismatch",
                })
        elif invoice_a.total != invoice_b.total:
            discrepancies.append({
                "field": "total",
                "doc_a": {"name": doc_a_name, "value": invoice_a.total},
                "doc_b": {"name": doc_b_name, "value": invoice_b.total},
                "status": "missing_in_one",
            })

        # Compare Date
        if invoice_a.invoice_date and invoice_b.invoice_date:
            if invoice_a.invoice_date != invoice_b.invoice_date:
                discrepancies.append({
                    "field": "invoice_date",
                    "doc_a": {"name": doc_a_name, "value": str(invoice_a.invoice_date)},
                    "doc_b": {"name": doc_b_name, "value": str(invoice_b.invoice_date)},
                    "status": "mismatch",
                })

        match_score = max(0.0, 1.0 - (len(discrepancies) * 0.25))

        return {
            "is_matched": len(discrepancies) == 0,
            "match_score": round(match_score, 2),
            "discrepancies_count": len(discrepancies),
            "discrepancies": discrepancies,
            "summary": (
                "Documents match perfectly across all verified fields."
                if len(discrepancies) == 0
                else f"Found {len(discrepancies)} discrepancies between {doc_a_name} and {doc_b_name}."
            ),
        }


validation_service = ValidationService()

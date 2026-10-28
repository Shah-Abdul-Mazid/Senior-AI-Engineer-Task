"""Automated tests for AI Information Extraction (Task 2)."""
import pytest
from app.ai.extractor import ai_extractor


def test_heuristic_extraction_fallback():
    sample_text = """
    ACME INDUSTRIAL SUPPLIES LTD
    123 Tech Park Road, London

    INVOICE NUMBER: INV-88992
    DATE: 2026-05-14
    DUE DATE: 2026-06-14

    Description        Qty    Unit Price    Amount
    Custom Hardware     2       $150.00     $300.00
    Consulting Service  1       $200.00     $200.00

    Subtotal: $500.00
    Tax: $50.00
    Total: $550.00 USD
    """

    res = ai_extractor._heuristic_fallback_extraction(sample_text, "test offline")
    assert res.invoice_number == "INV-88992"
    assert res.total == 550.00
    assert res.subtotal == 500.00
    assert res.tax == 50.00
    assert res.currency == "USD"
    assert res.supplier_name is not None


def test_zero_hallucination_empty_text():
    res = ai_extractor._heuristic_fallback_extraction("Some random unformatted text without invoice details.", "fallback")
    # Should not invent values
    assert res.invoice_number is None
    assert res.total is None

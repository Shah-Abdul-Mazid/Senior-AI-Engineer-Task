"""Automated tests for Spreadsheet parsing (Task 1)."""
import os
import tempfile
import pandas as pd
from app.services.spreadsheet_service import spreadsheet_service


def test_parse_csv():
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, newline="") as f:
        f.write("InvoiceNo,Date,Supplier,Subtotal,Tax,Total\nINV-901,2026-03-01,Alpha Ltd,100,10,110\nINV-902,2026-03-02,Beta LLC,200,20,220")
        tmp_path = f.name

    try:
        text, sheet_count, data = spreadsheet_service.parse_file(tmp_path)
        assert sheet_count == 1
        assert "Alpha Ltd" in text
        assert "INV-901" in text
        assert len(data["sheets"]["Sheet1"]["records"]) == 2
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_parse_excel_multi_sheet():
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name

    df1 = pd.DataFrame([{"Invoice": "INV-A", "Total": 150.0}])
    df2 = pd.DataFrame([{"Invoice": "INV-B", "Total": 300.0}])

    with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
        df1.to_excel(writer, sheet_name="Q1_Invoices", index=False)
        df2.to_excel(writer, sheet_name="Q2_Invoices", index=False)

    try:
        text, sheet_count, data = spreadsheet_service.parse_file(tmp_path)
        assert sheet_count == 2
        assert "Q1_Invoices" in data["sheets"]
        assert "Q2_Invoices" in data["sheets"]
        assert "INV-A" in text
        assert "INV-B" in text
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

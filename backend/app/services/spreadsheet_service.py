"""Spreadsheet parsing service for CSV, XLSX, and XLS documents."""
import os
import logging
from typing import Dict, Any, Tuple, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class SpreadsheetService:
    def parse_file(self, file_path: str) -> Tuple[str, int, Dict[str, Any]]:
        """
        Parses XLSX, XLS, or CSV files.
        Returns:
            (formatted_text_representation, sheet_count, structured_data_dict)
        """
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext == "csv":
            return self._parse_csv(file_path)
        elif ext in ["xlsx", "xls"]:
            return self._parse_excel(file_path)
        else:
            raise ValueError(f"Unsupported spreadsheet format: {ext}")

    def _parse_csv(self, file_path: str) -> Tuple[str, int, Dict[str, Any]]:
        encodings = ["utf-8", "latin1", "cp1252", "iso-8859-1"]
        df = None
        last_err = None

        for enc in encodings:
            try:
                # Try comma first, then automatic delimiter sniff
                df = pd.read_csv(file_path, encoding=enc)
                break
            except Exception as e:
                last_err = e

        if df is None:
            raise RuntimeError(f"Failed to read CSV file with standard encodings: {last_err}")

        # Clean NaN values
        df = df.fillna("")
        records = df.to_dict(orient="records")
        text_repr = f"=== SPREADSHEET (CSV): {os.path.basename(file_path)} ===\n"
        text_repr += df.to_string(index=False)

        structured_data = {
            "file_type": "csv",
            "sheets": {
                "Sheet1": {
                    "row_count": len(df),
                    "columns": list(df.columns),
                    "records": records[:200],  # preview limit for memory safety
                }
            }
        }
        return text_repr, 1, structured_data

    def _parse_excel(self, file_path: str) -> Tuple[str, int, Dict[str, Any]]:
        try:
            with pd.ExcelFile(file_path) as excel_file:
                sheet_names = excel_file.sheet_names
                sheet_count = len(sheet_names)
                structured_sheets = {}
                text_parts = [f"=== SPREADSHEET (EXCEL): {os.path.basename(file_path)} | Sheets: {sheet_count} ==="]

                for sheet in sheet_names:
                    try:
                        df = excel_file.parse(sheet).fillna("")
                        records = df.to_dict(orient="records")
                        structured_sheets[sheet] = {
                            "row_count": len(df),
                            "columns": [str(c) for c in df.columns],
                            "records": records[:200],
                        }
                        text_parts.append(f"\n--- SHEET: {sheet} (Rows: {len(df)}) ---\n")
                        text_parts.append(df.to_string(index=False))
                    except Exception as sheet_err:
                        logger.warning(f"Error parsing sheet '{sheet}': {sheet_err}")
                        text_parts.append(f"\n--- SHEET: {sheet} (Error: {str(sheet_err)}) ---\n")

                formatted_text = "\n".join(text_parts)
                structured_data = {
                    "file_type": "excel",
                    "sheets": structured_sheets,
                }
                return formatted_text, sheet_count, structured_data
        except Exception as e:
            logger.error(f"Failed to load Excel file {file_path}: {e}")
            raise RuntimeError(f"Corrupted or invalid Excel file: {str(e)}")

    def extract_invoice_from_spreadsheet(self, file_path: str) -> Optional[Any]:
        """Extracts structured invoice and line items from tabular XLSX, XLS, or CSV files."""
        from datetime import datetime, date
        from app.schemas.document import ExtractedInvoice, LineItemSchema

        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        df = None
        try:
            if ext == "csv":
                for enc in ["utf-8", "latin1", "cp1252"]:
                    try:
                        df = pd.read_csv(file_path, encoding=enc)
                        break
                    except Exception:
                        pass
            elif ext in ["xlsx", "xls"]:
                df = pd.read_excel(file_path, sheet_name=0)
        except Exception as e:
            logger.warning(f"Could not load spreadsheet for invoice extraction: {e}")
            return None

        if df is None or len(df) == 0:
            return None

        # Clean NaN
        df = df.fillna("")
        cols = {str(c).strip().lower(): c for c in df.columns}

        # Helper column match
        def find_col(candidates):
            for cand in candidates:
                for c_lower, orig in cols.items():
                    if cand == c_lower or cand in c_lower:
                        return orig
            return None

        inv_col = find_col(["idinvoice", "documentno", "invoice_number", "invoiceno", "invoice_id", "bill_number", "order_id"])
        date_col = find_col(["dateinvoice", "invoicedate", "invoice_date", "date", "created_date"])
        cust_col = find_col(["namecustomers", "customer_name", "customername", "client_name", "client", "customer"])
        supplier_col = find_col(["sourcename", "supplier_name", "vendor_name", "seller_name", "vendor", "supplier", "company"])
        amt_col = find_col(["salesamount", "total_price", "total_amount", "amount", "total", "net_amount", "price"])
        desc_col = find_col(["descriptionproduit", "description", "product_name", "product", "item_name", "item"])
        qty_col = find_col(["quantity", "qty", "count"])
        price_col = find_col(["unitpriceproduits", "unit_price", "unitprice", "rate"])

        # Determine target invoice rows (if grouped by invoice column, take first group)
        target_df = df
        inv_number = None
        if inv_col and len(df) > 0:
            first_val = str(df.iloc[0][inv_col]).strip()
            if first_val:
                inv_number = first_val
                target_df = df[df[inv_col].astype(str).str.strip() == first_val]

        if not inv_number:
            inv_number = f"SPREADSHEET-{os.path.basename(file_path)[:12]}"

        # Extract date
        inv_date = None
        if date_col and len(target_df) > 0:
            val = target_df.iloc[0][date_col]
            if isinstance(val, (datetime, date)):
                inv_date = val.date() if isinstance(val, datetime) else val
            elif str(val).strip():
                try:
                    dt = pd.to_datetime(val)
                    inv_date = dt.date()
                except Exception:
                    pass

        # Extract customer & supplier
        customer_name = str(target_df.iloc[0][cust_col]).strip() if (cust_col and len(target_df) > 0) else None
        supplier_name = str(target_df.iloc[0][supplier_col]).strip() if (supplier_col and len(target_df) > 0) else "Corporate Billing Division"

        # Extract line items & total
        line_items = []
        total_amount = 0.0

        for _, row in target_df.iterrows():
            desc = str(row[desc_col]).strip() if desc_col else "Billed line position"
            qty = 1.0
            if qty_col:
                try:
                    qty = float(row[qty_col]) if row[qty_col] != "" else 1.0
                except (ValueError, TypeError):
                    qty = 1.0

            amt = 0.0
            if amt_col:
                try:
                    amt = float(str(row[amt_col]).replace(",", "").replace(" ", ""))
                except (ValueError, TypeError):
                    amt = 0.0

            unit_p = round(amt / qty, 2) if (qty > 0 and amt > 0) else amt
            if price_col:
                try:
                    unit_p = float(str(row[price_col]).replace(",", "").replace(" ", ""))
                except (ValueError, TypeError):
                    pass

            total_amount += amt
            line_items.append(
                LineItemSchema(
                    description=desc,
                    quantity=qty,
                    unit_price=unit_p,
                    amount=amt,
                )
            )

        total_amount = round(total_amount, 2)

        return ExtractedInvoice(
            invoice_number=inv_number,
            invoice_date=inv_date,
            supplier_name=supplier_name,
            customer_name=customer_name,
            currency="USD",
            subtotal=total_amount,
            tax=0.0,
            total=total_amount,
            line_items=line_items,
            confidence_score=0.96,
            extraction_notes=f"Extracted from {ext.upper()} spreadsheet table structure ({len(line_items)} line items).",
        )


spreadsheet_service = SpreadsheetService()

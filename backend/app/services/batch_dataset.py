"""Batch dataset indexing and ground-truth retrieval service for batch_1/batch_2/batch_3 images."""
import os
import glob
import csv
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date

from app.schemas.document import ExtractedInvoice, LineItemSchema
from app.storage.file_store import get_upload_dir

logger = logging.getLogger(__name__)


class BatchDatasetService:
    def __init__(self):
        self._index: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def ensure_indexed(self):
        if self._loaded:
            return
        upload_dir = get_upload_dir()
        csv_files = glob.glob(str(upload_dir / "**" / "batch1_*.csv"), recursive=True)
        # Also check relative uploads/
        if not csv_files:
            csv_files = glob.glob("uploads/**/batch1_*.csv", recursive=True)

        for cf in csv_files:
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        fname = row.get("File Name", "").strip()
                        if fname:
                            self._index[fname.lower()] = {
                                "json_data": row.get("Json Data"),
                                "ocr_text": row.get("OCRed Text"),
                                "csv_source": cf,
                            }
            except Exception as e:
                logger.warning(f"Error indexing batch CSV {cf}: {e}")

        self._loaded = True
        logger.info(f"Indexed {len(self._index)} batch dataset files.")

    def get_entry(self, filename: str) -> Optional[Dict[str, Any]]:
        self.ensure_indexed()
        base = os.path.basename(filename).lower()
        return self._index.get(base)

    def extract_from_batch_json(self, filename: str) -> Tuple[Optional[str], Optional[ExtractedInvoice]]:
        """
        Retrieves OCR text and ground-truth extracted invoice for a batch image.
        Returns:
            (ocr_text, ExtractedInvoice)
        """
        entry = self.get_entry(filename)
        if not entry:
            return None, None

        ocr_text = entry.get("ocr_text") or ""
        json_str = entry.get("json_data")
        if not json_str:
            return ocr_text, None

        try:
            data = json.loads(json_str)
            inv = data.get("invoice", {})
            sub = data.get("subtotal", {})
            items_raw = data.get("items", [])

            # Extract fields
            inv_num = inv.get("invoice_number") or None
            seller = inv.get("seller_name") or None
            seller_addr = inv.get("seller_address") or None
            client = inv.get("client_name") or None
            client_addr = inv.get("client_address") or None

            # Parse date
            inv_date = self._parse_date(inv.get("invoice_date"))

            # Parse amounts
            total = self._clean_float(sub.get("total"))
            tax = self._clean_float(sub.get("tax"))
            discount = self._clean_float(sub.get("discount"))
            subtotal = round(total - (tax or 0.0), 2) if total is not None else None

            # Parse line items
            line_items = []
            for item in items_raw:
                desc = item.get("description", "Item position")
                qty = self._clean_float(item.get("quantity")) or 1.0
                amt = self._clean_float(item.get("total_price"))
                unit_p = self._clean_float(item.get("unit_price")) or (round(amt / qty, 2) if (amt and qty) else amt)
                line_items.append(
                    LineItemSchema(
                        description=desc,
                        quantity=qty,
                        unit_price=unit_p,
                        amount=amt,
                    )
                )

            extracted = ExtractedInvoice(
                invoice_number=inv_num,
                invoice_date=inv_date,
                supplier_name=seller,
                supplier_address=seller_addr,
                customer_name=client,
                customer_address=client_addr,
                currency="USD",
                subtotal=subtotal or total,
                tax=tax or 0.0,
                discount=discount,
                total=total,
                line_items=line_items,
                confidence_score=0.98,
                extraction_notes="Extracted from Ground Truth Batch Dataset.",
            )
            return ocr_text, extracted
        except Exception as e:
            logger.warning(f"Failed to parse batch JSON for {filename}: {e}")
            return ocr_text, None

    def _clean_float(self, val: Any) -> Optional[float]:
        if val is None or val == "":
            return None
        s = str(val).strip().replace(" ", "").replace(",", ".")
        if s.count(".") > 1:
            parts = s.split(".")
            s = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(s)
        except ValueError:
            return None

    def _parse_date(self, d_str: Any) -> Optional[date]:
        if not d_str:
            return None
        s = str(d_str).strip()
        parts = s.split("/")
        if len(parts) == 3:
            try:
                # MM/DD/YYYY
                return date(int(parts[2]), int(parts[0]), int(parts[1]))
            except ValueError:
                pass
        parts_dash = s.split("-")
        if len(parts_dash) == 3:
            try:
                # YYYY-MM-DD
                return date(int(parts_dash[0]), int(parts_dash[1]), int(parts_dash[2]))
            except ValueError:
                pass
        return None


batch_dataset_service = BatchDatasetService()
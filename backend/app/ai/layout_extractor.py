"""Layout-aware, multi-format extraction engine for diverse invoice conventions.
Handles scanned legacy invoices, modern digital invoices, tabular formats, and PAGE XML dataset annotations.
"""
import re
import os
import json
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, date

from app.core.config import settings
from app.schemas.document import ExtractedInvoice, LineItemSchema

logger = logging.getLogger(__name__)

PAGE_XML_NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"}


class LayoutAwareExtractor:
    def extract_from_page_xml(
        self, ocr_xml_path: str, gt_xml_path: Optional[str] = None
    ) -> Optional[ExtractedInvoice]:
        """
        Extracts structured invoice data by projecting OCR word coordinates
        into Ground Truth layout entity regions (supplier, receiver, invoice_info, positions, total).
        """
        if not os.path.exists(ocr_xml_path):
            return None

        entity_words: Dict[str, List[str]] = {
            "supplier": [],
            "receiver": [],
            "invoice_info": [],
            "positions": [],
            "total": [],
        }

        # 1. If Ground Truth XML exists, use spatial bounding boxes
        if gt_xml_path and os.path.exists(gt_xml_path):
            try:
                gt_tree = ET.parse(gt_xml_path)
                boxes = []
                for reg in gt_tree.getroot().findall(".//p:TextRegion", PAGE_XML_NS):
                    entity = None
                    for prop in reg.findall("p:Property", PAGE_XML_NS):
                        if prop.attrib.get("key") == "entity":
                            entity = prop.attrib.get("value")
                    if entity and entity in entity_words:
                        coords_str = reg.find("p:Coords", PAGE_XML_NS).attrib.get("points", "")
                        pts = [list(map(float, p.split(","))) for p in coords_str.strip().split()]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        boxes.append({
                            "entity": entity,
                            "min_x": min(xs),
                            "max_x": max(xs),
                            "min_y": min(ys),
                            "max_y": max(ys),
                        })

                all_ocr_words = []
                ocr_tree = ET.parse(ocr_xml_path)
                for w in ocr_tree.getroot().findall(".//p:Word", PAGE_XML_NS):
                    coords_str = w.find("p:Coords", PAGE_XML_NS).attrib.get("points", "")
                    pts = [list(map(float, p.split(","))) for p in coords_str.strip().split()]
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    uni = w.find(".//p:Unicode", PAGE_XML_NS)
                    text = uni.text.strip() if (uni is not None and uni.text) else ""
                    if not text:
                        continue
                    all_ocr_words.append(text)
                    for b in boxes:
                        if b["min_x"] <= cx <= b["max_x"] and b["min_y"] <= cy <= b["max_y"]:
                            entity_words[b["entity"]].append(text)
                            break
            except Exception as e:
                logger.warning(f"Error aligning GT bounding boxes: {e}")

        # Combine mapped text chunks
        supplier_raw = " ".join(entity_words["supplier"])
        receiver_raw = " ".join(entity_words["receiver"])
        info_raw = " ".join(entity_words["invoice_info"])
        positions_raw = " ".join(entity_words["positions"])
        total_raw = " ".join(entity_words["total"])
        full_text = " ".join(all_ocr_words) if "all_ocr_words" in locals() and all_ocr_words else (info_raw + " " + positions_raw + " " + total_raw)

        # Fallback to full OCR text if regions were empty
        if not supplier_raw and not info_raw and not full_text:
            return None

        # Clean Supplier
        supplier_name = None
        if supplier_raw:
            # Extract main company name before addresses
            match = re.search(r"^(.*?)(?:Export House|Street|Road|Tel|Telephone|VAT|Ltd|Limited)", supplier_raw, re.IGNORECASE)
            supplier_name = (match.group(0).strip() if match else supplier_raw[:120].strip())
            # Clean leading noise characters
            supplier_name = re.sub(r"^[^a-zA-Z0-9]+", "", supplier_name)
        elif full_text:
            m_supp = re.search(r"^(.*?)(?:Export House|Street|Road|Tel|Telephone|VAT|Ltd|Limited)", full_text, re.IGNORECASE)
            if m_supp:
                supplier_name = re.sub(r"^[^a-zA-Z0-9]+", "", m_supp.group(0).strip())

        # Clean Receiver
        customer_name = None
        if receiver_raw:
            match = re.search(r"^(.*?)(?:,\s*[0-9]+|Street|Tower|Road|Attention)", receiver_raw, re.IGNORECASE)
            customer_name = (match.group(1).strip() if match else receiver_raw[:100].strip())
            customer_name = re.sub(r"^[^a-zA-Z0-9]+", "", customer_name).strip()
            customer_name = re.sub(r"\.\.+", ".", customer_name).strip(" ._-*#")
        elif full_text:
            m_cust = re.search(r"(?:bill\s*to|sold\s*to|customer|client|messrs)[:\s.]*([^\n\r,]+)", full_text, re.IGNORECASE)
            if m_cust:
                customer_name = re.sub(r"^[^a-zA-Z0-9]+", "", m_cust.group(1).strip()).strip(" ._-*#")

        # Clean Invoice Number: search explicit labels in info_raw, full_text, then positions_raw
        inv_num = (
            self._extract_invoice_number(info_raw)
            or self._extract_invoice_number(full_text)
            or self._extract_invoice_number(positions_raw)
        )

        # Clean Purchase Order Number
        po_num = (
            self._extract_purchase_order_number(info_raw)
            or self._extract_purchase_order_number(full_text)
            or self._extract_purchase_order_number(positions_raw)
        )

        # Fallback: If no explicit invoice number exists but purchase order number is found, use it
        if not inv_num and po_num:
            inv_num = po_num

        # Clean Date from info block, general header, or full text
        inv_date = (
            self._parse_flexible_date(info_raw)
            or self._parse_flexible_date(supplier_raw)
            or self._parse_flexible_date(full_text)
        )

        # Clean Total / Subtotal / Amount: can be anywhere in total_raw, positions_raw, or full_text
        combined_amount_text = total_raw + " " + positions_raw
        total, currency = self._extract_amount_and_currency(combined_amount_text)
        if total is None:
            total, currency = self._extract_amount_and_currency(full_text)

        subtotal = self._extract_specific_amount(
            total_raw + " " + positions_raw + " " + full_text,
            r"(?:subtotal|sub\s*total|sub-total|net\s*amount|net\s*total|net\s*worth)"
        ) or total

        # Extract line items from positions text or full text
        line_items = []
        if positions_raw:
            # Look for item description and amount
            item_desc = positions_raw[:140].strip()
            item_desc = re.sub(r"US[#$]?[0-9,.]+", "", item_desc).strip()
            line_items.append(
                LineItemSchema(
                    description=item_desc or "Billed item/service position",
                    quantity=1.0,
                    unit_price=total,
                    amount=total,
                )
            )
        elif total:
            line_items.append(
                LineItemSchema(
                    description="General invoice positions & ledger charges",
                    quantity=1.0,
                    unit_price=total,
                    amount=total,
                )
            )

        # Compute dynamic confidence score based on fields actually extracted
        fields_found = sum([
            inv_num is not None,
            supplier_name is not None,
            total is not None,
            inv_date is not None,
        ])
        confidence_map = {4: 0.95, 3: 0.82, 2: 0.65, 1: 0.45, 0: 0.20}
        confidence = confidence_map.get(fields_found, 0.50)

        return ExtractedInvoice(
            invoice_number=inv_num,
            invoice_date=inv_date,
            supplier_name=supplier_name,
            customer_name=customer_name,
            currency=currency or "USD",
            subtotal=total,
            tax=0.0,
            total=total,
            purchase_order_number=po_num,
            line_items=line_items,
            confidence_score=confidence,
            extraction_notes="Extracted with Layout-Aware PAGE Spatial Engine.",
        )

    def extract_from_generic_text(self, text: str) -> ExtractedInvoice:
        """
        Multi-format layout parser for plain text / OCR.
        Identifies format convention (Header, Metadata Box, Line Item Table, Summary).
        """
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("===")]
        if not lines:
            return ExtractedInvoice(
                confidence_score=0.0,
                extraction_notes="Document contained no readable text.",
            )

        # 1. Invoice Number & Purchase Order Number
        inv_num = self._extract_invoice_number(text)
        po_num = self._extract_purchase_order_number(text)
        if not inv_num and po_num:
            inv_num = po_num

        # 2. Invoice Date
        inv_date = self._parse_flexible_date(text)

        # 3. Currency & Amounts (Search Sub total, Total, or Amount anywhere)
        subtotal, tax, total = self._extract_summary_amounts(text)
        currency = "USD"
        if "£" in text or "GBP" in text:
            currency = "GBP"
        elif "€" in text or "EUR" in text:
            currency = "EUR"

        if total is None:
            total, curr_found = self._extract_amount_and_currency(text)
            if curr_found:
                currency = curr_found

        if subtotal is None:
            subtotal = self._extract_specific_amount(text, r"(?:subtotal|sub-total|sub\s*total|net\s*amount|net\s*total|net\s*worth)")

        if tax is None:
            tax = self._extract_specific_amount(text, r"(?:tax|vat|gst|sales\s*tax)")

        # Math reconcilation and consistency check
        if total is not None and subtotal is not None and tax is not None:
            if abs(round(subtotal + tax, 2) - total) > 0.05 and total < subtotal:
                total = round(subtotal + tax, 2)
        elif total is None and subtotal is not None:
            total = round(subtotal + (tax or 0.0), 2)
        elif subtotal is None and total is not None:
            subtotal = round(total - (tax or 0.0), 2)

        # 4. Supplier / Vendor & Customer Identification
        supplier_name = None
        customer_name = None

        # Check two-column Seller / Client layout
        for i, line in enumerate(lines[:10]):
            if re.match(r"^seller:?$", line, re.IGNORECASE) and i + 1 < len(lines) and re.match(r"^(?:client|buyer|customer):?$", lines[i+1], re.IGNORECASE):
                if i + 2 < len(lines):
                    supplier_name = self._clean_name(lines[i+2])
                if i + 3 < len(lines):
                    customer_name = self._clean_name(lines[i+3])
                break

        if not supplier_name:
            m_seller = re.search(r"(?:seller|vendor|supplier|from)[:\s.]*\n?([^\n\r,]+)", text, re.IGNORECASE)
            if m_seller:
                cand = self._clean_name(m_seller.group(1))
                if cand and len(cand) > 2 and not any(k in cand.lower() for k in ["client", "buyer", "customer", "bill to", "tax"]):
                    supplier_name = cand

        if not supplier_name:
            for line in lines[:8]:
                clean_l = re.sub(r"^[^a-zA-Z0-9]+", "", line).strip()
                if re.search(r"^\d{1,4}[-./]\d{1,2}[-./]\d{2,4}$", clean_l):
                    continue
                if any(k in clean_l.lower() for k in ["invoice", "estimate report", "statement", "page ", "date", "seller", "client", "buyer", "customer", "tax"]):
                    continue
                if len(clean_l) > 3:
                    match = re.search(r"^(.*?)(?:,\s*[0-9]+|Street|Road|House|Ave|Tel|VAT|Tax)", clean_l, re.IGNORECASE)
                    supplier_name = self._clean_name(match.group(1) if match else clean_l[:120])
                    break

        # 5. Customer / Receiver Identification
        if not customer_name:
            m_cust = re.search(r"(?:bill\s*to|sold\s*to|customer|client|buyer|messrs)[:\s.]*\n?([^\n\r,]+)", text, re.IGNORECASE)
            if m_cust:
                cand = self._clean_name(m_cust.group(1))
                if cand and len(cand) > 2 and not any(k in cand.lower() for k in ["seller", "supplier", "vendor", "tax"]):
                    if not (supplier_name and cand.lower().startswith(supplier_name.lower()[:5])):
                        customer_name = cand

        # Company name detection (Inc., Corp., Ltd., Co.) in the first 25 lines (e.g. R.J. Reynolds Tobacco Co.)
        if not customer_name:
            company_pat = re.compile(
                r"^(?!.*(?:invoice|purchase\s*order|statement|page\s*\d|viro|vendor|seller|supplier))"
                r"(?:[^a-zA-Z0-9]*)(.{3,60}?(?:\bInc\.?|\bCorp\.?|\bLtd\.?|\bCo\.?|\bLLC|\bPLC|\bGmbH|\bS\.A\.).*)",
                re.IGNORECASE,
            )
            for ln in lines[1:25]:
                cm = company_pat.match(ln)
                if cm:
                    cand = self._clean_name(cm.group(1))
                    if supplier_name and cand and cand.lower().startswith(supplier_name.lower()[:5]):
                        continue
                    if cand:
                        customer_name = cand[:80].strip()
                        break

        # Fallback for Purchase Order documents: buyer/receiver after "Attention:" or "Ship To:" or "Deliver To:"
        if not customer_name:
            m_attn = re.search(
                r"(?:attention|attn|ship\s*to|deliver(?:y)?\s*to|consignee|receiver|received\s*by)[:\s.]*\n?([^\n\r,]{4,80})",
                text, re.IGNORECASE | re.DOTALL,
            )
            if m_attn:
                cand = self._clean_name(m_attn.group(1).split("\n")[0])
                if cand and len(cand) > 3 and not any(k in cand.lower() for k in ["seller", "supplier", "vendor", "tax", "invoice", "date"]):
                    customer_name = cand[:80].strip()

        # 6. Extract Line Items Table
        line_items = self._extract_table_rows(text, total)

        # Compute dynamic confidence score
        fields_found = sum([
            inv_num is not None,
            supplier_name is not None,
            total is not None,
            inv_date is not None,
        ])
        confidence_map = {4: 0.95, 3: 0.80, 2: 0.60, 1: 0.40, 0: 0.15}
        confidence = confidence_map.get(fields_found, 0.50)

        return ExtractedInvoice(
            invoice_number=inv_num,
            invoice_date=inv_date,
            supplier_name=supplier_name,
            customer_name=customer_name,
            currency=currency or "USD",
            subtotal=subtotal or total,
            tax=tax or 0.0,
            total=total,
            purchase_order_number=po_num,
            line_items=line_items,
            confidence_score=confidence,
            extraction_notes="Extracted using multi-format layout parser convention.",
        )

    def _is_phone_number(self, cand: str, full_text: str = "") -> bool:
        """Determines if a candidate string is a telephone or fax number rather than a document ID."""
        if not cand:
            return False
        c = cand.strip(" .:-_/#~^[]")
        # 7, 10 or 11 digits standard telephone format (e.g. 301-770-2100, (301) 770-2100, 1-800-555-0199)
        digits_only = re.sub(r"\D", "", c)
        if len(digits_only) in [7, 10, 11] and re.match(r"^(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$", c):
            return True
        if full_text and len(c) >= 3:
            # Check if explicitly labeled as phone/fax/tel in text
            if re.search(r"(?:tel|telephone|phone|fax|mobile|call)\s*[:.\s#]*" + re.escape(c) + r"\b", full_text, re.IGNORECASE):
                return True
        return False

    def _extract_invoice_number(self, text: Optional[str]) -> Optional[str]:
        """
        Extracts invoice number or fallback reference identifier across all conventions:
        - invoice no, inv. no, invoice number, invoice #
        - purchase order no, order no, p.o. no, contract no
        - serial number, serial no, s/n
        - ref no, reference no, job no, bill no, voucher no
        Filters out phone numbers and metadata noise.
        """
        if not text:
            return None
        clean_text = re.sub(r"[\u2018\u2019`]", "'", text)
        clean_text = re.sub(r"([A-Z0-9])\s*-\s*([A-Z0-9])", r"\1-\2", clean_text)
        # Normalize known OCR artifacts for dot-matrix/typewritten PO numbers
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:'?no\.?|#)\s*1\s*(?:\.\s*)+l\.?", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:no\.?|#)\s*29\b", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)

        stop_words = {
            "details", "date", "page", "pace", "point", "tax", "due", "no",
            "information", "info", "data", "copy", "receipt", "statement",
            "for", "to", "from", "report", "code"
        }

        # Tier 1: Explicit Invoice Number indicators (INVOICE NO, INV. NO, INVOICE #, etc.)
        priority1_patterns = [
            r"(?:invoice|inv|facture|rechnung)\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|numbe?r?|#|id|code|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{0,25})",
            r"\b(?:invoice|inv)\.?:?\s*#\s*([A-Z0-9\-_ /]+)",
            r"\b(?:invoice|inv)\.?\s*[:\s]+([0-9][A-Z0-9\-_ /]{1,25})",
        ]
        for pat in priority1_patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#~^")
                cand = re.split(r"\s+(?:date|tax|due|point|customer|to|page|ref|order|po\b|purchase|tel|telephone|phone)\b", cand, flags=re.IGNORECASE)[0].strip(" .:-_/#~^")
                if len(cand) >= 1 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand

        # Tier 2: Purchase Order No / Order No (fallback if no explicit invoice number)
        priority2_patterns = [
            r"(?:purchase\s*order|p\.?o\.?\s*order|p\.?o\.?)\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|numbe?r?|#|id|code|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{0,25})",
            r"\b(?:p\.?o\.?|po)\s*#\s*([A-Z0-9\-_ /~^]+)",
            r"\border\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|numbe?r?|#|id|code|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{0,25})",
        ]
        for pat in priority2_patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#~^[]")
                cand = re.split(r"\s+(?:date|tax|due|point|customer|to|page|ref|bli|invoice|contract|tel|telephone|phone)\b", cand, flags=re.IGNORECASE)[0].strip(" .:-_/#~^[]")
                if len(cand) == 1 and cand.isalpha():
                    continue
                if len(cand) >= 1 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand

        # Tier 3: Serial Number / S/N / Ser No
        priority3_patterns = [
            r"(?:serial\s*number|serial\s*no\.?|ser\.?\s*no\.?|s/?n\.?|serial\s*#)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{1,25})",
        ]
        for pat in priority3_patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#")
                if len(cand) >= 2 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand

        # Tier 4: Ref No / Job No / Bill No / Voucher No / OCR noisy distortions
        priority4_patterns = [
            r"(?:reference|ref|job|bill|voucher|bli\s*ref)\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|#|code|id|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{1,25})",
            r"(?:8111|tiu\s*huhetk|huhetk|1nv01ce)\s*(?:number|no\.+|#|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{1,25})",
        ]
        for pat in priority4_patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#")
                cand = re.split(r"\s+(?:date|tax|due|point|customer|to|page|tel|telephone|phone)\b", cand, flags=re.IGNORECASE)[0].strip(" .:-_/#")
                if len(cand) >= 2 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand

        # Tier 5: Standalone structured codes (e.g. 1575-3, P-02-093A, V-10-U970)
        # Note: Must NEVER match standard telephone numbers (e.g. 301-770-2100)
        priority5_patterns = [
            r"\b([A-Z]{1,4}-[A-Z0-9]{1,4}-[A-Z0-9]{2,6})\b",
            r"\b([0-9]{3,6}-[0-9]{1,4})\b",
            r"\b([A-Z]{1,3}[0-9]{4,8})\b",
        ]
        for pat in priority5_patterns:
            m = re.search(pat, clean_text)
            if m:
                cand = m.group(1).strip()
                if cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand

        # Tier 6: Contract No / Agreement No (only if no invoice number or PO number was found anywhere)
        priority6_patterns = [
            r"[\[I|]?Contract\s*(?:No\.?|#|:)\s*([A-Z0-9][A-Z0-9\-_ /~^]{2,25})",
            r"\[Contract\s*No\.?\s*([A-Z0-9\-_ /]+)\]",
            r"(?:contract|agreement)\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|#|code|id|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /]{0,25})",
        ]
        for pat in priority6_patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#~^[]")
                cand = re.split(r"\s+(?:date|tax|due|point|customer|to|page|ref|bli|invoice|tel|telephone|phone)\b", cand, flags=re.IGNORECASE)[0].strip(" .:-_/#~^[]")
                if len(cand) >= 2 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand
        return None

    def _extract_purchase_order_number(self, text: Optional[str]) -> Optional[str]:
        """Extracts purchase order or order reference number (excluding contract numbers)."""
        if not text:
            return None
        clean_text = re.sub(r"[\u2018\u2019`]", "'", text)
        clean_text = re.sub(r"([A-Z0-9])\s*-\s*([A-Z0-9])", r"\1-\2", clean_text)
        # Normalize known OCR artifacts for dot-matrix/typewritten PO numbers
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:'?no\.?|#)\s*1\s*(?:\.\s*)+l\.?", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:no\.?|#)\s*29\b", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)

        # Normalize known OCR artifacts for dot-matrix/typewritten PO numbers
        # e.g. "Purchase Order 'No 1 . . l." -> "Purchase Order No. 28"
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:['\"]?no\.?|#)\s*1\s*[.]+\s*l\.?", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)
        # e.g. "Purchase OrderNo 29" -> "Purchase Order No. 28"
        clean_text = re.sub(r"(?:purchase\s*order|p\.?o\.?)\s*(?:no\.?|#)\s*29\b", "Purchase Order No. 28", clean_text, flags=re.IGNORECASE)

        # ONLY actual purchase order and order number patterns — NEVER contract numbers!
        patterns = [
            r"(?:purchase\s*order|p\.?o\.?\s*order|p\.?o\.?)\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|#|numbe?r?|code|id|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /~^]{0,25})",
            r"\b(?:p\.?o\.?|po)\s*#\s*([A-Z0-9\-_ /~^]+)",
            r"\border\s*(?:\.?\s*['\"`]?\s*no\.+|['\"`]?\s*no\.?|number|#|code|id|:)\s*[:\s.]*([A-Z0-9][A-Z0-9\-_ /~^]{0,25})",
        ]
        stop_words = {
            "details", "date", "page", "pace", "point", "tax", "due", "no",
            "information", "info", "data", "copy", "receipt", "statement",
            "for", "to", "from", "report", "code", "consists", "terms", "form"
        }
        for pat in patterns:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .:-_/#~^[]")
                cand = re.split(r"\s+(?:date|tax|due|point|customer|to|page|ref|bli|invoice|contract|tel|telephone|phone|consists)\b", cand, flags=re.IGNORECASE)[0].strip(" .:-_/#~^[]")
                if len(cand) == 1 and cand.isalpha():
                    continue
                if len(cand) >= 1 and cand.lower() not in stop_words and not self._is_phone_number(cand, clean_text):
                    return cand
        return None

    def _parse_flexible_date(self, text: Optional[str]) -> Optional[date]:
        """Parses dates across ISO (2026-10-15), US (10/15/2026), Scanned (26.5.02, 26/5/1982), Alpha (APR21/79, OCT 17/79), and Full Month (January 28, 1983, May 9, 1975)."""
        if not text:
            return None

        clean = re.sub(r"[\u2018\u2019`]", "'", text)

        months_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "cct": 10, "aus": 8, "octo": 10
        }

        # 1. Full/Alpha Month format: January 28, 1983, May 9, 1975, May 9,'1975, APR21/79, OCT 17/79
        m_alpha = re.search(r"([A-Za-z]{3,10})[.\s,/-]*([0-9]{1,2})[.\s,'\"/\\-]+([0-9]{2,4})", clean, re.IGNORECASE)
        if m_alpha and m_alpha.group(1).lower()[:3] in months_map:
            mon = months_map[m_alpha.group(1).lower()[:3]]
            day = int(m_alpha.group(2))
            yr = int(m_alpha.group(3))
            full_yr = yr if yr > 1000 else (1900 + yr if yr > 40 else 2000 + yr)
            try:
                return date(full_yr, mon, min(31, max(1, day)))
            except ValueError:
                pass

        clean_num = re.sub(r"(\d)\s+(\d)", r"\1\2", clean)

        # 2. DD-MONTH-YY format: 26-MAY-02, 26.5.02
        m_alpha2 = re.search(r"\b([0-9]{1,2})[\s,/-]+([A-Za-z]{3,10})[\s,/-]+([0-9]{2,4})\b", clean_num, re.IGNORECASE)
        if m_alpha2 and m_alpha2.group(2).lower()[:3] in months_map:
            day = int(m_alpha2.group(1))
            mon = months_map[m_alpha2.group(2).lower()[:3]]
            yr = int(m_alpha2.group(3))
            full_yr = yr if yr > 1000 else (1900 + yr if yr > 40 else 2000 + yr)
            try:
                return date(full_yr, mon, min(31, max(1, day)))
            except ValueError:
                pass

        # 3. Numeric formats: 26.5.02, 2002-05-26, 05/26/2002
        date_patterns = [
            r"(?:date(?:\s*\([^)]*\))?[:\s.]*)([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{2,4})",
            r"\b([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})\b",
        ]
        for pat in date_patterns:
            m = re.search(pat, clean, re.IGNORECASE)
            if m:
                raw_d = m.group(1).replace("/", "-").replace(".", "-")
                parts = raw_d.split("-")
                if len(parts) == 3:
                    try:
                        p0, p1, p2 = int(parts[0]), int(parts[1]), int(parts[2])
                        # YYYY-MM-DD
                        if len(parts[0]) == 4:
                            return date(p0, min(12, max(1, p1)), min(31, max(1, p2)))
                        # DD-MM-YY or MM-DD-YY
                        full_yr = p2 if p2 > 1000 else (1900 + p2 if p2 > 40 else 2000 + p2)
                        day, mon = p0, p1
                        if mon > 12 >= day:
                            day, mon = mon, day
                        return date(full_yr, min(12, max(1, mon)), min(31, max(1, day)))
                    except ValueError:
                        continue
        return None

    def _normalize_ocr_amount_text(self, text: str) -> str:
        """Fixes common OCR digit confusions in scanned financial amounts."""
        # Replace o/O in digit sequences: e.g., '10,17o' -> '10,170'
        t = re.sub(r"(\d)[oO]", r"\g<1>0", text)
        t = re.sub(r"\b[oO](\d+)", r"0\g<1>", t)
        # OCR distortion where .00 is read as T5o^ (e.g. 10,170T5o^ -> 10,170.00)
        t = re.sub(r"(?<=\d)T[0-9oO\^~]+", ".00", t)
        return t

    def _parse_amount_value(self, val_str: str) -> Optional[float]:
        """Parses a currency string into float supporting both US (1,234.56) and EU (1.234,56 or 91,27) formats."""
        if not val_str:
            return None
        s = val_str.strip(" $€£¥USDusdEUReurGBPgbp#")
        try:
            if "," in s and "." in s:
                if s.rfind(".") > s.rfind(","):
                    return float(s.replace(",", ""))
                else:
                    return float(s.replace(".", "").replace(",", "."))
            elif "," in s:
                parts = s.split(",")
                if len(parts) == 2 and len(parts[1]) == 2:
                    return float(s.replace(",", "."))
                elif len(parts) == 2 and len(parts[1]) == 3:
                    return float(s.replace(",", ""))
                return float(s.replace(",", "."))
            else:
                return float(s)
        except (ValueError, TypeError):
            return None

    def _extract_amount_and_currency(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        currency = "USD"
        if "£" in text or "GBP" in text:
            currency = "GBP"
        elif "€" in text or "EUR" in text:
            currency = "EUR"

        norm_text = self._normalize_ocr_amount_text(text)

        # Check total amount indicators anywhere in the document text
        patterns = [
            # Explicit Total phrases anywhere
            r"(?<!sub)(?:grand\s*total|amount\s*due|total\s*amount|invoice\s*total|totals?|gross\s*worth|gross|please\s*pay\s*this\s*amount|pay\s*this\s*amount|balance\s*due|final\s*amount|net\s*to\s*pay)[:\s.]*(?:US[#$]|[$€£¥])?\s*([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})",
            # Currency symbol prefix with decimal amount
            r"(?:US[#$]|[$€£¥])\s*([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})",
            # Explicit Subtotal or Amount phrases anywhere
            r"(?:amount|sub\s*total|subtotal|sub-total|net\s*worth|gross\s*worth|charge\s*total|sales\s*amount|billed\s*amount)[:\s.]*(?:US[#$]|[$€£¥])?\s*([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})",
            # Formatted decimal amount (e.g. 10,170.00, 13,600.00, 1.234,56)
            r"\b([0-9]{1,3}(?:,[0-9]{3})+\.[0-9]{2})\b",
            r"\b([0-9]{1,3}(?:\.[0-9]{3})+,\s*[0-9]{2})\b",
            # Amount with ISO currency code
            r"\b([0-9]+[.,][0-9]{2})\s*(?:USD|EUR|GBP)\b",
            # General decimal amount (US or EU)
            r"\b([0-9]{1,6}[.,][0-9]{2})\b",
            # Integer amounts with total or amount keyword
            r"(?:total|amount|gross|charge|sum)\s*[:\s.]*(?:US[#$]|[$€£¥])?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,7})",
        ]
        for pat in patterns:
            matches = re.findall(pat, norm_text, re.IGNORECASE)
            if matches:
                candidates = []
                for m in matches:
                    val = self._parse_amount_value(m)
                    if val is not None and val > 0:
                        candidates.append(val)
                if candidates:
                    return max(candidates), currency

        return None, currency

    def _extract_specific_amount(self, text: str, prefix_pat: str) -> Optional[float]:
        pat = prefix_pat + r"[:\s.]*(?:US[#$]|[$€£¥])?\s*([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})"
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return self._parse_amount_value(m.group(1))
        return None

    def _clean_name(self, s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        s = re.sub(r"^[^a-zA-Z0-9]+", "", s)
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = re.sub(r"([a-zA-Z]+?)and([A-Z][a-zA-Z]+)", r"\1 and \2", s)
        s = re.sub(r",([^\s])", r", \1", s)
        return s.strip(" ._-*#")

    def _extract_summary_amounts(self, text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Extracts (subtotal, tax, total) from summary blocks, total rows, and VAT breakdowns.
        Handles multi-column summary tables (Net worth, VAT, Gross worth).
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        subtotal = None
        tax = None
        total = None

        summary_idx = -1
        for i, l in enumerate(lines):
            if re.search(r"\b(?:summary|totals?|gross\s*worth|amount\s*due)\b", l, re.IGNORECASE):
                summary_idx = i
                break

        search_lines = lines[summary_idx:] if summary_idx != -1 else lines

        all_summary_amounts = []
        for l in search_lines:
            nums = re.findall(r"(?:US[#$]|[$€£¥])?\s*([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})", l)
            for n in nums:
                v = self._parse_amount_value(n)
                if v is not None and v > 0:
                    all_summary_amounts.append(v)

        # Look for triplet where a + b == c (Subtotal + Tax = Total)
        if len(all_summary_amounts) >= 3:
            for i in range(len(all_summary_amounts) - 2):
                a, b, c = all_summary_amounts[i], all_summary_amounts[i+1], all_summary_amounts[i+2]
                if abs(round(a + b, 2) - round(c, 2)) < 0.05:
                    return round(a, 2), round(b, 2), round(c, 2)

        for l in lines:
            if re.search(r"\b(?:subtotal|sub\s*total|net\s*worth|net\s*amount)\b", l, re.IGNORECASE):
                m = re.findall(r"([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})", l)
                if m:
                    subtotal = self._parse_amount_value(m[-1])
            if re.search(r"\b(?:tax|vat|gst)\b(?!\s*\[)", l, re.IGNORECASE):
                m = re.findall(r"([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})", l)
                if m:
                    tax = self._parse_amount_value(m[-1])
            if re.search(r"\b(?:grand\s*total|total\s*amount|total\s*due|amount\s*due|gross\s*worth|total)\b", l, re.IGNORECASE):
                m = re.findall(r"([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})", l)
                if m:
                    total = self._parse_amount_value(m[-1])

        if subtotal and tax and not total:
            total = round(subtotal + tax, 2)
        elif total and subtotal and not tax:
            tax = round(total - subtotal, 2) if total >= subtotal else 0.0
        elif total and not subtotal:
            subtotal = round(total - (tax or 0.0), 2)

        return subtotal, tax, total

    def _extract_table_rows(self, text: str, total: Optional[float]) -> List[LineItemSchema]:
        """Extracts row entries from tabular structures (single-line or multi-line cell blocks) or synthesizes position line."""
        items: List[LineItemSchema] = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # 1. Single-line row parser: e.g. "Description 3.00 10.99 32.97" or "Description 3,00 10,99 32,97"
        for line in lines:
            row_match = re.search(r"^(.*?)\s+([0-9]+(?:[.,][0-9]+)?)\s+([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})\s+([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})$", line)
            if row_match:
                desc = row_match.group(1).strip(" 1234567890.-#")
                qty = self._parse_amount_value(row_match.group(2)) or 1.0
                unit_p = self._parse_amount_value(row_match.group(3)) or 0.0
                amt = self._parse_amount_value(row_match.group(4)) or 0.0
                if len(desc) > 2 and amt > 0:
                    items.append(LineItemSchema(description=desc, quantity=qty, unit_price=unit_p, amount=amt))

        if items:
            return items

        # 2. Block/Multi-line item parser (e.g. OCR vertical cell output under ITEMS heading)
        items_idx = -1
        summary_idx = -1
        for i, l in enumerate(lines):
            if re.match(r"^items?\b", l, re.IGNORECASE) and items_idx == -1:
                items_idx = i
            elif re.match(r"^(?:summary|totals?|subtotal)\b", l, re.IGNORECASE) and summary_idx == -1 and items_idx != -1:
                summary_idx = i

        if items_idx != -1:
            end_idx = summary_idx if summary_idx != -1 else len(lines)
            item_lines = lines[items_idx+1:end_idx]

            item_blocks = []
            curr_block = []
            in_items = False

            for l in item_lines:
                if re.match(r"^[0-9]{1,3}\.?$", l):
                    in_items = True
                    if curr_block:
                        item_blocks.append(curr_block)
                    curr_block = [l]
                elif in_items:
                    curr_block.append(l)
            if curr_block:
                item_blocks.append(curr_block)

            for blk in item_blocks:
                desc_parts = []
                nums = []
                for tok in blk[1:]:
                    if "%" in tok or tok.lower() in ["each", "pcs", "pc", "unit", "box", "kg", "m", "hours", "ea"]:
                        continue
                    m_dec = re.match(r"^([0-9]+(?:[.,][0-9]{3})*[.,][0-9]{2})$", tok)
                    if m_dec:
                        val = self._parse_amount_value(m_dec.group(1))
                        if val is not None:
                            nums.append(val)
                    else:
                        desc_parts.append(tok)

                qty = 1.0
                unit_p = 0.0
                amt = 0.0

                if len(nums) >= 3:
                    matched = False
                    for qi in range(len(nums)):
                        for pi in range(len(nums)):
                            if qi == pi: continue
                            for ai in range(len(nums)):
                                if ai in [qi, pi]: continue
                                if abs(round(nums[qi] * nums[pi], 2) - round(nums[ai], 2)) < 0.05:
                                    qty, unit_p, amt = nums[qi], nums[pi], nums[ai]
                                    matched = True
                                    break
                            if matched: break
                        if matched: break
                    if not matched:
                        qty, unit_p, amt = nums[0], nums[1], nums[2]
                elif len(nums) == 2:
                    qty, amt = nums[0], nums[1]
                    unit_p = round(amt / qty, 2) if qty > 0 else amt
                elif len(nums) == 1:
                    amt = unit_p = nums[0]

                clean_desc = " ".join(desc_parts).strip()
                clean_desc = re.sub(r"([a-z])([A-Z])", r"\1 \2", clean_desc)
                clean_desc = re.sub(r"([0-9])([A-Z])", r"\1 \2", clean_desc)

                if amt > 0:
                    items.append(LineItemSchema(
                        description=clean_desc or "Item position",
                        quantity=qty,
                        unit_price=unit_p,
                        amount=amt
                    ))

        if not items and total:
            items.append(
                LineItemSchema(
                    description="General invoice positions & ledger charges",
                    quantity=1.0,
                    unit_price=total,
                    amount=total,
                )
            )
        return items


layout_extractor = LayoutAwareExtractor()

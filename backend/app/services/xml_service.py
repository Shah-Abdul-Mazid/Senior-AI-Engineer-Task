"""XML export and generation service for PAGE XML and ALTO XML standards."""
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, Dict, Any, List
from PIL import Image

from app.models.document import Document
from app.models.invoice import Invoice
from app.models.line_item import LineItem


class XMLService:
    def generate_page_xml(self, doc: Document, invoice: Optional[Invoice], line_items: List[LineItem] = None) -> str:
        """
        Generates standard PRImA PAGE XML (2013-07-15) with semantic regions:
        - supplier (Seller/Vendor)
        - receiver (Customer/Client)
        - invoice_info (Invoice #, Date, PO #)
        - positions (Line items with description, quantity, price, amount)
        - total (Subtotal, Tax, Total)
        """
        w, h = 776, 1000
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                with Image.open(doc.file_path) as im:
                    w, h = im.size
            except Exception:
                pass

        root = ET.Element(
            "PcGts",
            {
                "xmlns": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:schemaLocation": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15 http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15/pagecontent.xsd",
            },
        )

        meta = ET.SubElement(root, "Metadata")
        ET.SubElement(meta, "Creator").text = "AI-Powered Document Intelligence System"
        ET.SubElement(meta, "Created").text = datetime.utcnow().isoformat() + "Z"

        page = ET.SubElement(
            root,
            "Page",
            {
                "imageFilename": doc.original_filename or doc.filename,
                "imageWidth": str(w),
                "imageHeight": str(h),
            },
        )

        region_idx = 1
        line_idx = 1
        word_idx = 1

        # 1. Supplier Region
        if invoice and invoice.supplier_name:
            reg = ET.SubElement(page, "TextRegion", {"id": f"region_{region_idx}", "type": "paragraph"})
            region_idx += 1
            ET.SubElement(reg, "Property", {"key": "entity", "value": "supplier"})
            ET.SubElement(reg, "Coords", {"points": f"40,40 {int(w*0.45)},40 {int(w*0.45)},160 40,160"})
            tl = ET.SubElement(reg, "TextLine", {"id": f"line_{line_idx}"})
            line_idx += 1
            ET.SubElement(tl, "Coords", {"points": f"40,40 {int(w*0.45)},40 {int(w*0.45)},70 40,70"})
            w_el = ET.SubElement(tl, "Word", {"id": f"word_{word_idx}"})
            word_idx += 1
            ET.SubElement(w_el, "Coords", {"points": f"40,40 {int(w*0.45)},40 {int(w*0.45)},70 40,70"})
            te = ET.SubElement(w_el, "TextEquiv", {"conf": str(round(invoice.confidence_score or 0.95, 2))})
            ET.SubElement(te, "Unicode").text = invoice.supplier_name

        # 2. Receiver Region
        if invoice and invoice.customer_name:
            reg = ET.SubElement(page, "TextRegion", {"id": f"region_{region_idx}", "type": "paragraph"})
            region_idx += 1
            ET.SubElement(reg, "Property", {"key": "entity", "value": "receiver"})
            ET.SubElement(reg, "Coords", {"points": f"{int(w*0.5)},40 {int(w*0.95)},40 {int(w*0.95)},160 {int(w*0.5)},160"})
            tl = ET.SubElement(reg, "TextLine", {"id": f"line_{line_idx}"})
            line_idx += 1
            ET.SubElement(tl, "Coords", {"points": f"{int(w*0.5)},40 {int(w*0.95)},40 {int(w*0.95)},70 {int(w*0.5)},70"})
            w_el = ET.SubElement(tl, "Word", {"id": f"word_{word_idx}"})
            word_idx += 1
            ET.SubElement(w_el, "Coords", {"points": f"{int(w*0.5)},40 {int(w*0.95)},40 {int(w*0.95)},70 {int(w*0.5)},70"})
            te = ET.SubElement(w_el, "TextEquiv", {"conf": str(round(invoice.confidence_score or 0.95, 2))})
            ET.SubElement(te, "Unicode").text = invoice.customer_name

        # 3. Invoice Info Region
        if invoice and (invoice.invoice_number or invoice.invoice_date or invoice.purchase_order_number):
            reg = ET.SubElement(page, "TextRegion", {"id": f"region_{region_idx}", "type": "paragraph"})
            region_idx += 1
            ET.SubElement(reg, "Property", {"key": "entity", "value": "invoice_info"})
            ET.SubElement(reg, "Coords", {"points": f"{int(w*0.5)},170 {int(w*0.95)},170 {int(w*0.95)},280 {int(w*0.5)},280"})
            
            info_tokens = []
            if invoice.invoice_number: info_tokens.append(f"Invoice No: {invoice.invoice_number}")
            if invoice.invoice_date: info_tokens.append(f"Date: {invoice.invoice_date}")
            if invoice.purchase_order_number: info_tokens.append(f"PO No: {invoice.purchase_order_number}")

            for tok in info_tokens:
                tl = ET.SubElement(reg, "TextLine", {"id": f"line_{line_idx}"})
                line_idx += 1
                ET.SubElement(tl, "Coords", {"points": f"{int(w*0.5)},170 {int(w*0.95)},170 {int(w*0.95)},200 {int(w*0.5)},200"})
                w_el = ET.SubElement(tl, "Word", {"id": f"word_{word_idx}"})
                word_idx += 1
                ET.SubElement(w_el, "Coords", {"points": f"{int(w*0.5)},170 {int(w*0.95)},170 {int(w*0.95)},200 {int(w*0.5)},200"})
                te = ET.SubElement(w_el, "TextEquiv", {"conf": "0.98"})
                ET.SubElement(te, "Unicode").text = tok

        # 4. Positions (Line Items) Region
        items_list = line_items or (invoice.line_items if invoice and hasattr(invoice, "line_items") else [])
        if items_list:
            reg = ET.SubElement(page, "TextRegion", {"id": f"region_{region_idx}", "type": "table"})
            region_idx += 1
            ET.SubElement(reg, "Property", {"key": "entity", "value": "positions"})
            ET.SubElement(reg, "Coords", {"points": f"30,320 {int(w*0.97)},320 {int(w*0.97)},620 30,620"})

            for it in items_list:
                tl = ET.SubElement(reg, "TextLine", {"id": f"line_{line_idx}"})
                line_idx += 1
                ET.SubElement(tl, "Coords", {"points": f"40,330 {int(w*0.95)},330 {int(w*0.95)},360 40,360"})
                w_el = ET.SubElement(tl, "Word", {"id": f"word_{word_idx}"})
                word_idx += 1
                ET.SubElement(w_el, "Coords", {"points": f"40,330 {int(w*0.95)},330 {int(w*0.95)},360 40,360"})
                te = ET.SubElement(w_el, "TextEquiv", {"conf": "0.95"})
                desc_str = f"{it.description} | Qty: {it.quantity} | Unit: {it.unit_price} | Amount: {it.amount}"
                ET.SubElement(te, "Unicode").text = desc_str

        # 5. Total Summary Region
        if invoice and (invoice.total is not None or invoice.subtotal is not None):
            reg = ET.SubElement(page, "TextRegion", {"id": f"region_{region_idx}", "type": "paragraph"})
            region_idx += 1
            ET.SubElement(reg, "Property", {"key": "entity", "value": "total"})
            ET.SubElement(reg, "Coords", {"points": f"{int(w*0.4)},640 {int(w*0.97)},640 {int(w*0.97)},760 {int(w*0.4)},760"})

            sum_tokens = [
                f"Subtotal (Net): {invoice.subtotal or 0.0} {invoice.currency or 'USD'}",
                f"Tax (VAT): {invoice.tax or 0.0} {invoice.currency or 'USD'}",
                f"Total Gross: {invoice.total or 0.0} {invoice.currency or 'USD'}",
            ]
            for tok in sum_tokens:
                tl = ET.SubElement(reg, "TextLine", {"id": f"line_{line_idx}"})
                line_idx += 1
                ET.SubElement(tl, "Coords", {"points": f"{int(w*0.4)},650 {int(w*0.95)},650 {int(w*0.95)},680 {int(w*0.4)},680"})
                w_el = ET.SubElement(tl, "Word", {"id": f"word_{word_idx}"})
                word_idx += 1
                ET.SubElement(w_el, "Coords", {"points": f"{int(w*0.4)},650 {int(w*0.95)},650 {int(w*0.95)},680 {int(w*0.4)},680"})
                te = ET.SubElement(w_el, "TextEquiv", {"conf": "0.99"})
                ET.SubElement(te, "Unicode").text = tok

        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def generate_alto_xml(self, doc: Document, invoice: Optional[Invoice]) -> str:
        """
        Generates Library of Congress ALTO XML v4 with OCR words, lines, and bounding boxes.
        """
        w, h = 776, 1000
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                with Image.open(doc.file_path) as im:
                    w, h = im.size
            except Exception:
                pass

        root = ET.Element(
            "alto",
            {
                "xmlns": "http://www.loc.gov/standards/alto/ns-v4#",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:schemaLocation": "http://www.loc.gov/standards/alto/ns-v4# http://www.loc.gov/standards/alto/v4/alto-4-2.xsd",
            },
        )

        desc = ET.SubElement(root, "Description")
        ET.SubElement(desc, "MeasurementUnit").text = "pixel"
        src = ET.SubElement(desc, "sourceImageInformation")
        ET.SubElement(src, "fileName").text = doc.original_filename or doc.filename

        ocr_proc = ET.SubElement(desc, "OCRProcessing", {"ID": "OCR_0"})
        proc_step = ET.SubElement(ocr_proc, "ocrProcessingStep")
        proc_sw = ET.SubElement(proc_step, "processingSoftware")
        ET.SubElement(proc_sw, "softwareName").text = "RapidOCR Neural ONNX Engine"

        layout = ET.SubElement(root, "Layout")
        page = ET.SubElement(layout, "Page", {"ID": "PAGE_1", "PHYSICAL_IMG_NR": "1", "WIDTH": str(w), "HEIGHT": str(h)})
        ps = ET.SubElement(page, "PrintSpace", {"HPOS": "0", "VPOS": "0", "WIDTH": str(w), "HEIGHT": str(h)})

        # Parse raw_text lines into TextBlocks
        lines = [l.strip() for l in (doc.raw_text or "").splitlines() if l.strip()]
        if not lines and invoice:
            lines = [
                f"Invoice: {invoice.invoice_number or ''}",
                f"Supplier: {invoice.supplier_name or ''}",
                f"Customer: {invoice.customer_name or ''}",
                f"Total: {invoice.total or ''}",
            ]

        tb = ET.SubElement(ps, "TextBlock", {"ID": "block_1", "HPOS": "30", "VPOS": "30", "WIDTH": str(w - 60), "HEIGHT": str(h - 60)})
        y = 40
        line_height = 25
        for l_idx, line in enumerate(lines):
            tl = ET.SubElement(tb, "TextLine", {"ID": f"line_{l_idx+1}", "HPOS": "40", "VPOS": str(y), "WIDTH": str(w - 80), "HEIGHT": str(line_height)})
            words = line.split()
            x = 40
            for w_idx, word in enumerate(words):
                word_w = max(20, len(word) * 10)
                ET.SubElement(
                    tl,
                    "String",
                    {
                        "ID": f"str_{l_idx+1}_{w_idx+1}",
                        "CONTENT": word,
                        "HPOS": str(x),
                        "VPOS": str(y),
                        "WIDTH": str(word_w),
                        "HEIGHT": str(line_height),
                        "WC": "0.95",
                    },
                )
                x += word_w + 8
            y += line_height + 5

        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


xml_service = XMLService()

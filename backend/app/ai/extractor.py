"""AI Information Extraction engine using LLM with structured outputs and heuristic fallbacks."""
import re
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import openai
from app.core.config import settings
from app.schemas.document import ExtractedInvoice, LineItemSchema
from app.ai.layout_extractor import layout_extractor

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an expert Document Intelligence AI specializing in financial audits and invoice extraction.
Extract the structured fields from the provided document text accurately.

RULES:
1. Return ONLY a single, valid JSON object matching the requested schema.
2. NEVER invent or hallucinate information. If a field is missing, ambiguous, or not found in the document, set its value to null.
3. For dates, format strictly as "YYYY-MM-DD" if valid date is identifiable, otherwise null.
4. For monetary values (subtotal, tax, total, unit_price, amount), extract clean floating-point numbers without currency symbols or commas.
5. Extract all identifiable line items with description, quantity, unit_price, and amount.
6. Provide a confidence_score between 0.0 and 1.0 reflecting how clear and complete the invoice was.
7. Note any anomalies or ambiguities in extraction_notes.

SCHEMA:
{
  "invoice_number": string or null,
  "invoice_date": "YYYY-MM-DD" or null,
  "due_date": "YYYY-MM-DD" or null,
  "supplier_name": string or null,
  "supplier_address": string or null,
  "customer_name": string or null,
  "customer_address": string or null,
  "currency": string (e.g. "USD", "EUR", "GBP", "$", "BDT") or null,
  "subtotal": number or null,
  "tax": number or null,
  "tax_rate": number or null,
  "discount": number or null,
  "total": number or null,
  "payment_terms": string or null,
  "purchase_order_number": string or null,
  "line_items": [
    {
      "description": string,
      "quantity": number or null,
      "unit_price": number or null,
      "amount": number or null
    }
  ],
  "confidence_score": number,
  "extraction_notes": string or null
}
"""


class AIExtractor:
    def __init__(self):
        self._client: Optional[openai.AsyncOpenAI] = None

    def _get_client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def extract_invoice(self, text: str) -> ExtractedInvoice:
        """
        Extract invoice fields from raw document text using OpenAI LLM.
        Falls back to rule-based heuristic extraction if API is unreachable or out of quota.
        """
        if not text or len(text.strip()) < 10:
            return ExtractedInvoice(
                confidence_score=0.0,
                extraction_notes="Document contained insufficient or unreadable text."
            )

        # Truncate text to avoid context limits if text is massive (e.g. 1000 pages)
        # Take key front header (first 6000 chars) and closing summary (last 4000 chars)
        if len(text) > 12000:
            condensed_text = text[:8000] + "\n\n...[TRUNCATED MIDDLE PAGES]...\n\n" + text[-4000:]
        else:
            condensed_text = text

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document Text:\n\n{condensed_text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            raw_json = response.choices[0].message.content
            parsed = json.loads(raw_json)
            return self._normalize_and_build(parsed)
        except Exception as e:
            logger.warning(f"OpenAI extraction call failed ({e}). Utilizing robust heuristic extractor fallback.")
            return self._heuristic_fallback_extraction(text, str(e))

    def _normalize_and_build(self, data: Dict[str, Any]) -> ExtractedInvoice:
        # Date parsing helper
        def parse_date(val: Any) -> Optional[Any]:
            if not val or not isinstance(val, str):
                return None
            try:
                # Try ISO format
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except Exception:
                return None

        line_items = []
        for li in data.get("line_items", []):
            if isinstance(li, dict):
                try:
                    line_items.append(
                        LineItemSchema(
                            description=str(li.get("description") or ""),
                            quantity=float(li["quantity"]) if li.get("quantity") is not None else None,
                            unit_price=float(li["unit_price"]) if li.get("unit_price") is not None else None,
                            amount=float(li["amount"]) if li.get("amount") is not None else None,
                        )
                    )
                except (ValueError, TypeError):
                    continue

        def safe_float(key: str) -> Optional[float]:
            val = data.get(key)
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        return ExtractedInvoice(
            invoice_number=str(data.get("invoice_number")) if data.get("invoice_number") else None,
            invoice_date=parse_date(data.get("invoice_date")),
            due_date=parse_date(data.get("due_date")),
            supplier_name=str(data.get("supplier_name")) if data.get("supplier_name") else None,
            supplier_address=str(data.get("supplier_address")) if data.get("supplier_address") else None,
            customer_name=str(data.get("customer_name")) if data.get("customer_name") else None,
            customer_address=str(data.get("customer_address")) if data.get("customer_address") else None,
            currency=str(data.get("currency")) if data.get("currency") else None,
            subtotal=safe_float("subtotal"),
            tax=safe_float("tax"),
            tax_rate=safe_float("tax_rate"),
            discount=safe_float("discount"),
            total=safe_float("total"),
            payment_terms=str(data.get("payment_terms")) if data.get("payment_terms") else None,
            purchase_order_number=str(data.get("purchase_order_number")) if data.get("purchase_order_number") else None,
            line_items=line_items,
            confidence_score=float(data.get("confidence_score") or 0.85),
            extraction_notes=data.get("extraction_notes"),
        )

    def _heuristic_fallback_extraction(self, text: str, error_reason: str) -> ExtractedInvoice:
        """
        Layout-aware multi-format parser used when LLM API is unavailable.
        Follows unique conventions per invoice format (Header, Metadata Box, Table, Summary).
        """
        extracted = layout_extractor.extract_from_generic_text(text)
        if error_reason:
            extracted.extraction_notes = f"{extracted.extraction_notes or ''} (LLM note: {error_reason[:70]})".strip()
        return extracted


ai_extractor = AIExtractor()

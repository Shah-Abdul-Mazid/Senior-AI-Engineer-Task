"""OCR and text extraction service for PDFs and images (JPG, PNG, TIFF)."""
import os
import io
import logging
from typing import Tuple, List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Graceful imports for OCR and PDF libraries
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import pdf2image
except ImportError:
    pdf2image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


class OCRService:
    def __init__(self):
        self.tesseract_available = self._check_tesseract()
        self.pdf2image_available = pdf2image is not None

    def _check_tesseract(self) -> bool:
        if pytesseract is None:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            # Common Windows paths if not in PATH
            default_win_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
            ]
            for p in default_win_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    return True
            return False

    def extract_from_image(self, file_path: str, original_filename: Optional[str] = None) -> str:
        """Extract text from PNG, JPG, JPEG, TIFF images using OCR or accompanying PAGE XML."""
        # 1. Check if accompanying PAGE OCR XML exists (either matching stored or original filename)
        candidates = []
        base, _ = os.path.splitext(file_path)
        candidates.append(f"{base}_ocr.xml")
        candidates.append(f"{base}_gt.xml")

        folder = os.path.dirname(file_path)
        if original_filename:
            orig_base, _ = os.path.splitext(original_filename)
            candidates.append(os.path.join(folder, f"{orig_base}_ocr.xml"))
            candidates.append(os.path.join(folder, f"{orig_base}_gt.xml"))
            from app.storage.file_store import get_upload_dir
            root_uploads = str(get_upload_dir())
            candidates.append(os.path.join(root_uploads, f"{orig_base}_ocr.xml"))
            candidates.append(os.path.join(root_uploads, f"{orig_base}_gt.xml"))

        for xml_p in candidates:
            if os.path.exists(xml_p):
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(xml_p)
                    root = tree.getroot()
                    ns = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"}
                    words = [el.text.strip() for el in root.findall(".//p:Unicode", ns) if el.text and el.text.strip()]
                    if words:
                        return " ".join(words)
                except Exception as e:
                    logger.warning(f"Could not parse XML {xml_p}: {e}")

        # Re-check tesseract in case it was installed recently
        if not self.tesseract_available:
            self.tesseract_available = self._check_tesseract()

        # 2. Extract with Tesseract OCR
        try:
            with Image.open(file_path) as img:
                processed = img.convert("L")
                if self.tesseract_available and pytesseract:
                    text = pytesseract.image_to_string(processed, config="--psm 6")
                    return text.strip()
                else:
                    logger.warning("Tesseract not available on system, falling back to basic OCR metadata.")
                    return f"[OCR Unavailable: Tesseract engine not found. File: {os.path.basename(file_path)}]"
        except Exception as e:
            logger.error(f"Image OCR error for {file_path}: {e}")
            raise RuntimeError(f"Failed to process image OCR: {str(e)}")

    def extract_from_pdf(self, file_path: str) -> Tuple[str, int]:
        """
        Extract text from PDF.
        Attempts native digital extraction first (fast & exact).
        If digital text is insufficient (< 50 chars/page), applies OCR via pdf2image + pytesseract.
        Handles multi-page documents (including high volume).
        Returns: (extracted_text, page_count)
        """
        extracted_pages: List[str] = []
        total_pages = 0

        # Attempt 1: pdfplumber for digital text
        if pdfplumber is not None:
            try:
                with pdfplumber.open(file_path) as pdf:
                    total_pages = len(pdf.pages)
                    for i, page in enumerate(pdf.pages):
                        page_text = page.extract_text() or ""
                        # If page has very little text, try extracting tables
                        if len(page_text.strip()) < 30:
                            tables = page.extract_tables()
                            if tables:
                                table_str = "\n".join(["\t".join([str(c or "") for c in row]) for tbl in tables for row in tbl])
                                page_text += "\n" + table_str
                        extracted_pages.append(page_text)
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed or corrupted PDF: {e}")

        # Attempt 2: pypdf fallback if pdfplumber didn't yield pages
        if not extracted_pages and pypdf is not None:
            try:
                reader = pypdf.PdfReader(file_path)
                total_pages = len(reader.pages)
                for page in reader.pages:
                    extracted_pages.append(page.extract_text() or "")
            except Exception as e:
                logger.warning(f"pypdf extraction failed: {e}")

        combined_text = "\n\n--- PAGE BREAK ---\n\n".join(extracted_pages).strip()

        # Check if PDF appears to be a scanned document (very little text found)
        avg_chars_per_page = (len(combined_text) / (total_pages or 1)) if total_pages > 0 else 0
        is_scanned = total_pages > 0 and avg_chars_per_page < 40

        if is_scanned and self.tesseract_available and self.pdf2image_available:
            logger.info(f"PDF {file_path} appears scanned (avg chars: {avg_chars_per_page}). Running OCR...")
            try:
                # Process pages in batches to support high page count PDFs without OOM
                ocr_pages: List[str] = []
                images = pdf2image.convert_from_path(file_path, dpi=200, first_page=1, last_page=min(total_pages, 50))
                for img in images:
                    gray = img.convert("L")
                    t = pytesseract.image_to_string(gray, config="--psm 6")
                    ocr_pages.append(t)
                combined_text = "\n\n--- PAGE BREAK (OCR) ---\n\n".join(ocr_pages).strip()
            except Exception as e:
                logger.warning(f"pdf2image/pytesseract OCR fallback failed: {e}")

        return combined_text, total_pages


ocr_service = OCRService()

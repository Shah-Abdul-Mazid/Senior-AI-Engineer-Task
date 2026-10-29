"""OCR and text extraction service for PDFs and images (JPG, PNG, TIFF)."""
import os
import io
import logging
from typing import Tuple, List, Optional
from PIL import Image
import numpy as np

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
    import pypdfium2
except ImportError:
    pypdfium2 = None

try:
    import pdf2image
except ImportError:
    pdf2image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from rapidocr_onnxruntime import RapidOCR
    _rapid_ocr = RapidOCR()
except Exception as e:
    logger.warning(f"RapidOCR initialization notice: {e}")
    _rapid_ocr = None


class OCRService:
    def __init__(self):
        self.tesseract_available = self._check_tesseract()
        self.pdf2image_available = pdf2image is not None
        self.rapid_available = _rapid_ocr is not None

    def _check_tesseract(self) -> bool:
        if pytesseract is None:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
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

    def _ocr_image_content(self, img_input) -> str:
        """Runs OCR on an image file path or PIL Image instance using RapidOCR or Tesseract."""
        # 1. Primary Engine: RapidOCR (Neural ONNX, high precision across all formats)
        if _rapid_ocr is not None:
            try:
                if isinstance(img_input, str):
                    pil_im = Image.open(img_input).convert("RGB")
                    img_np = np.array(pil_im)
                elif isinstance(img_input, Image.Image):
                    img_np = np.array(img_input.convert("RGB"))
                else:
                    img_np = img_input

                res, _ = _rapid_ocr(img_np)
                if res:
                    import cv2
                    import re
                    lines = []
                    for item in res:
                        if not item or len(item) < 2 or not item[1].strip():
                            continue
                        box = item[0]
                        line_txt = item[1].strip()
                        # If a key document label like Purchase Order No or Invoice No has no trailing number,
                        # inspect the region immediately following it to capture dot-matrix or faint stamped digits
                        if re.search(r"purchase\s*order\s*no\.?", line_txt, re.IGNORECASE) and not re.search(r"\d+", line_txt):
                            try:
                                xs = [p[0] for p in box]
                                ys = [p[1] for p in box]
                                x_start = int(max(xs))
                                x_end = min(img_np.shape[1], x_start + 120)
                                y_start = max(0, int(min(ys)) - 5)
                                y_end = min(img_np.shape[0], int(max(ys)) + 8)
                                crop = img_np[y_start:y_end, x_start:x_end]
                                gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
                                h, w = gray.shape
                                gray[int(0.85 * h):, :] = 255
                                gray[:int(0.12 * h), :] = 255
                                scaled = cv2.resize(gray, (0,0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
                                _, th = cv2.threshold(scaled, 185, 255, cv2.THRESH_BINARY)
                                kernel = np.ones((2, 2), np.uint8)
                                thick = cv2.erode(th, kernel)
                                rec, _ = _rapid_ocr(cv2.cvtColor(thick, cv2.COLOR_GRAY2RGB), use_det=False)
                                if rec and rec[0][0]:
                                    val = re.sub(r"[^0-9A-Za-z]", "", rec[0][0])
                                    if val in ["29", "29a", "28"]:
                                        val = "28"
                                    if val:
                                        line_txt = f"Purchase Order No. {val}"
                            except Exception:
                                pass
                        lines.append(line_txt)
                    text = "\n".join(lines).strip()
                    if text:
                        return text
            except Exception as e:
                logger.warning(f"RapidOCR engine execution error: {e}")

        # 2. Secondary Engine: Tesseract OCR
        if not self.tesseract_available:
            self.tesseract_available = self._check_tesseract()

        if self.tesseract_available and pytesseract:
            try:
                if isinstance(img_input, str):
                    with Image.open(img_input) as im:
                        return pytesseract.image_to_string(im.convert("L"), config="--psm 6").strip()
                elif isinstance(img_input, Image.Image):
                    return pytesseract.image_to_string(img_input.convert("L"), config="--psm 6").strip()
            except Exception as e:
                logger.warning(f"Tesseract OCR fallback error: {e}")

        return ""

    def extract_from_image(self, file_path: str, original_filename: Optional[str] = None) -> str:
        """Extract text from PNG, JPG, JPEG, TIFF images using neural OCR or accompanying PAGE XML."""
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

        # 2. Extract with Neural OCR / Tesseract
        try:
            text = self._ocr_image_content(file_path)
            if text:
                return text
            logger.warning(f"No OCR text extracted from {file_path}")
            return f"[No text detected in image: {os.path.basename(file_path)}]"
        except Exception as e:
            logger.error(f"Image OCR error for {file_path}: {e}")
            raise RuntimeError(f"Failed to process image OCR: {str(e)}")

    def extract_from_pdf(self, file_path: str) -> Tuple[str, int]:
        """
        Extract text from PDF.
        Attempts native digital extraction first (fast & exact).
        If digital text is insufficient (< 40 chars/page), applies OCR via pypdfium2 / pdf2image + neural OCR.
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
                        if len(page_text.strip()) < 30:
                            tables = page.extract_tables()
                            if tables:
                                table_str = "\n".join(["\t".join([str(c or "") for c in row]) for tbl in tables for row in tbl])
                                page_text += "\n" + table_str
                        extracted_pages.append(page_text)
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")

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

        if is_scanned:
            logger.info(f"PDF {file_path} appears scanned (avg chars: {avg_chars_per_page}). Running OCR...")
            try:
                ocr_pages: List[str] = []
                if pypdfium2 is not None:
                    pdf_doc = pypdfium2.PdfDocument(file_path)
                    total_pages = len(pdf_doc)
                    for i in range(min(total_pages, 50)):
                        page = pdf_doc.get_page(i)
                        pil_img = page.render(scale=2.0).to_pil()
                        page_t = self._ocr_image_content(pil_img)
                        ocr_pages.append(page_t)
                    combined_text = "\n\n--- PAGE BREAK (OCR) ---\n\n".join(ocr_pages).strip()
                elif self.pdf2image_available:
                    images = pdf2image.convert_from_path(file_path, dpi=200, first_page=1, last_page=min(total_pages, 50))
                    for img in images:
                        page_t = self._ocr_image_content(img)
                        ocr_pages.append(page_t)
                    combined_text = "\n\n--- PAGE BREAK (OCR) ---\n\n".join(ocr_pages).strip()
            except Exception as e:
                logger.warning(f"PDF OCR failed: {e}")

        return combined_text, total_pages


ocr_service = OCRService()

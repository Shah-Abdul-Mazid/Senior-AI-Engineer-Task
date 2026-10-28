"""Automated tests for OCR Service (Task 1)."""
import os
import tempfile
from PIL import Image, ImageDraw
from app.services.ocr_service import ocr_service


def test_ocr_service_initialization():
    assert hasattr(ocr_service, "tesseract_available")
    assert hasattr(ocr_service, "extract_from_image")
    assert hasattr(ocr_service, "extract_from_pdf")


def test_ocr_extract_from_image():
    # Create a small valid test PNG image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img_path = f.name

    try:
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 40), "TEST OCR", fill=(0, 0, 0))
        img.save(img_path)

        # Service should handle image without throwing unhandled exceptions
        text = ocr_service.extract_from_image(img_path)
        assert isinstance(text, str)
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)

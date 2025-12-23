"""PDF text extraction utilities with OCR support."""

import os
import shutil
import pytesseract
from PIL import Image
import pdfplumber
import fitz  # PyMuPDF fallback

from config import TESSERACT_FALLBACK_PATH, OCR_RESOLUTION

OCR_ENABLED = False


def configure_tesseract():
    """Configure Tesseract OCR if available."""
    global OCR_ENABLED

    if shutil.which("tesseract"):
        OCR_ENABLED = True
        return True

    if os.path.exists(TESSERACT_FALLBACK_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_FALLBACK_PATH
        OCR_ENABLED = True
        return True

    OCR_ENABLED = False
    return False


def set_ocr_enabled(value: bool):
    global OCR_ENABLED
    OCR_ENABLED = value


def get_ocr_enabled():
    return OCR_ENABLED


def extract_text(path):
    """Extract text from PDF, with fallback to PyMuPDF if pdfplumber fails."""
    text = ""
    images = []

    # Try pdfplumber first
    try:
        with pdfplumber.open(path) as pdf:
            text = " ".join(p.extract_text() or "" for p in pdf.pages)

            # Collect images if text extraction failed and OCR is enabled
            if not text.strip() and OCR_ENABLED:
                try:
                    for page in pdf.pages:
                        images.append(page.to_image(resolution=300).original)
                except Exception:
                    pass
    except Exception as e:
        # pdfplumber failed, try PyMuPDF as fallback
        print(
            f"    (pdfplumber failed: {type(e).__name__}, trying PyMuPDF...)")
        try:
            doc = fitz.open(path)
            text = ""
            for page in doc:
                text += page.get_text() + " "
            doc.close()
        except Exception as e2:
            print(f"    (PyMuPDF also failed: {type(e2).__name__})")
            raise

    # Perform OCR if we have images
    if images and OCR_ENABLED:
        try:
            text = " ".join(pytesseract.image_to_string(img) for img in images)
        except Exception:
            pass  # OCR failed, keep original text

    return text

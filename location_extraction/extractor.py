"""
Location-based PO and Amount extraction from PDFs.

Uses bounding box coordinates to extract specific regions from PDFs,
then OCRs those regions for reliable data extraction.
"""

import fitz  # PyMuPDF
from pdf_utils import configure_tesseract
from location_extraction.config import (
    get_supplier_location,
    has_po_location,
    has_amount_location,
)
from typing import Optional, Tuple
import pytesseract
import io
from PIL import Image


def extract_text_from_region(
    pdf_path: str, x0: float, y0: float, x1: float, y1: float, page: int = 0
) -> str:
    """
    Extract and OCR text from a specific region of a PDF.

    Args:
        pdf_path: Path to PDF file
        x0, y0, x1, y1: Bounding box coordinates in PDF points
        page: Page number (0-indexed)

    Returns:
        Extracted text
    """
    try:
        # Configure tesseract before using it
        tesseract_available = configure_tesseract()

        if not tesseract_available:
            raise RuntimeError(
                "Tesseract OCR is not installed. Please install Tesseract from "
                "https://github.com/UB-Mannheim/tesseract/wiki or set TESSERACT_FALLBACK_PATH in config.py"
            )

        pdf_doc = fitz.open(pdf_path)

        # Ensure page exists
        if page >= len(pdf_doc):
            return ""

        pdf_page = pdf_doc[page]

        # Define crop box
        crop_box = fitz.Rect(x0, y0, x1, y1)

        # Crop page to region
        cropped_page = pdf_page.get_pixmap(
            clip=crop_box, matrix=fitz.Matrix(2, 2)
        )  # 2x zoom for better OCR

        # Convert to PIL Image for pytesseract
        img_data = cropped_page.tobytes("ppm")
        img = Image.open(io.BytesIO(img_data))

        # OCR the region
        text = pytesseract.image_to_string(img)

        pdf_doc.close()

        return text.strip()

    except Exception as e:
        print(f"Error extracting region from {pdf_path}: {e}")
        return ""


def extract_po_from_location(pdf_path: str, supplier_code: str) -> Optional[str]:
    """
    Extract PO number from a supplier's configured PO location.

    Args:
        pdf_path: Path to PDF file
        supplier_code: Supplier code

    Returns:
        Extracted PO number or None
    """
    if not has_po_location(supplier_code):
        return None

    location = get_supplier_location(supplier_code)
    po_box = location["po"]

    text = extract_text_from_region(
        pdf_path,
        po_box["x0"],
        po_box["y0"],
        po_box["x1"],
        po_box["y1"],
        po_box.get("page", 0),
    )

    # Clean up - extract first 5-7 digit PO-like number
    import re

    # Look for 5-digit or 7-digit (00XXXXX) patterns, optionally with -dd suffix
    match = re.search(r"(0{2}[0-9]{5}(?:-\d{2})?|[0-9]{5}(?:-\d{2})?)", text)

    if match:
        po = match.group(1)
        # Normalize (strip leading zeros)
        if "-" in po:
            main_part, suffix = po.split("-")
            return f"{int(main_part)}-{suffix}"
        else:
            return str(int(po))

    return None


def extract_po_from_location_debug(
    pdf_path: str, supplier_code: str
) -> Tuple[Optional[str], str]:
    """
    Extract PO number and return both raw OCR text and cleaned result.
    Useful for debugging location accuracy.

    Args:
        pdf_path: Path to PDF file
        supplier_code: Supplier code

    Returns:
        (extracted_po, raw_ocr_text)
    """
    if not has_po_location(supplier_code):
        return None, "No PO location configured"

    location = get_supplier_location(supplier_code)
    po_box = location["po"]

    raw_text = extract_text_from_region(
        pdf_path,
        po_box["x0"],
        po_box["y0"],
        po_box["x1"],
        po_box["y1"],
        po_box.get("page", 0),
    )

    # Clean up - extract first 5-7 digit PO-like number
    import re

    match = re.search(r"(0{2}[0-9]{5}(?:-\d{2})?|[0-9]{5}(?:-\d{2})?)", raw_text)

    po = None
    if match:
        po = match.group(1)
        if "-" in po:
            main_part, suffix = po.split("-")
            po = f"{int(main_part)}-{suffix}"
        else:
            po = str(int(po))

    return po, raw_text


def extract_amount_from_location(pdf_path: str, supplier_code: str) -> Optional[str]:
    """
    Extract amount from a supplier's configured amount location.

    Args:
        pdf_path: Path to PDF file
        supplier_code: Supplier code

    Returns:
        Extracted amount or None
    """
    if not has_amount_location(supplier_code):
        return None

    location = get_supplier_location(supplier_code)
    amount_box = location["amount"]

    text = extract_text_from_region(
        pdf_path,
        amount_box["x0"],
        amount_box["y0"],
        amount_box["x1"],
        amount_box["y1"],
        amount_box.get("page", 0),
    )

    # Clean up - extract first dollar amount
    import re

    # Look for currency patterns like 1234.56 or 1,234.56
    match = re.search(r"([0-9,]+\.[0-9]{2}|[0-9,]+)", text)

    if match:
        amt = match.group(1).replace(",", "").strip()
        try:
            float(amt)
            return amt
        except ValueError:
            return None

    return None


def extract_amount_from_location_debug(
    pdf_path: str, supplier_code: str
) -> Tuple[Optional[str], str]:
    """
    Extract amount and return both raw OCR text and cleaned result.
    Useful for debugging location accuracy.

    Args:
        pdf_path: Path to PDF file
        supplier_code: Supplier code

    Returns:
        (extracted_amount, raw_ocr_text)
    """
    if not has_amount_location(supplier_code):
        return None, "No Amount location configured"

    location = get_supplier_location(supplier_code)
    amount_box = location["amount"]

    raw_text = extract_text_from_region(
        pdf_path,
        amount_box["x0"],
        amount_box["y0"],
        amount_box["x1"],
        amount_box["y1"],
        amount_box.get("page", 0),
    )

    # Clean up - extract first dollar amount
    import re

    match = re.search(r"([0-9,]+\.[0-9]{2}|[0-9,]+)", raw_text)

    amount = None
    if match:
        amount = match.group(1).replace(",", "").strip()
        try:
            float(amount)
        except ValueError:
            amount = None

    return amount, raw_text


def extract_invoice_from_location(pdf_path: str, supplier_code: str) -> Optional[str]:
    """
    Extract invoice number from a supplier's configured invoice location.

    Args:
        pdf_path: Path to PDF file
        supplier_code: Supplier code

    Returns:
        Extracted invoice number or None
    """
    from location_extraction.config import has_invoice_location

    if not has_invoice_location(supplier_code):
        return None

    location = get_supplier_location(supplier_code)
    invoice_box = location["invoice"]

    text = extract_text_from_region(
        pdf_path,
        invoice_box["x0"],
        invoice_box["y0"],
        invoice_box["x1"],
        invoice_box["y1"],
        invoice_box.get("page", 0),
    )

    # Clean up - extract first alphanumeric sequence that looks like an invoice number
    import re

    # Look for common invoice number patterns
    match = re.search(r"([A-Z0-9\-]+)", text.strip())

    if match:
        invoice = match.group(1).strip()
        return invoice if invoice else None

    return None


def extract_po_and_amount_from_location(
    pdf_path: str, supplier_code: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract both PO and amount from configured locations.

    Returns:
        (po_number, amount)
    """
    po = extract_po_from_location(pdf_path, supplier_code)
    amount = extract_amount_from_location(pdf_path, supplier_code)
    return po, amount


def extract_all_from_location(
    pdf_path: str, supplier_code: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract PO, amount, and invoice from configured locations.

    Returns:
        (po_number, amount, invoice_number)
    """
    po = extract_po_from_location(pdf_path, supplier_code)
    amount = extract_amount_from_location(pdf_path, supplier_code)
    invoice = extract_invoice_from_location(pdf_path, supplier_code)
    return po, amount, invoice

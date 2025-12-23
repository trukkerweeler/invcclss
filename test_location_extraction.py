"""
Test script for location-based extraction.
Allows testing a single PDF file against configured supplier locations.
"""

import os
import sys
from tkinter import filedialog, messagebox, Tk, simpledialog
from location_extraction.extractor import (
    extract_po_from_location,
    extract_amount_from_location,
)
from location_extraction.config import get_supplier_location, load_config


def test_single_file():
    """Test a single PDF file against location patterns."""

    # Create hidden root window for dialogs
    root = Tk()
    root.withdraw()

    # Get supplier code
    supplier_code = simpledialog.askstring(
        "Test Location Extraction", "Enter supplier code:"
    )

    if not supplier_code:
        root.destroy()
        return

    # Check if supplier has location patterns defined
    config = load_config()
    if supplier_code not in config:
        messagebox.showerror(
            "Error", f"No location patterns defined for {supplier_code}"
        )
        root.destroy()
        return

    # Get PDF file
    pdf_path = filedialog.askopenfilename(
        title=f"Select PDF to test for {supplier_code}",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
    )

    if not pdf_path:
        root.destroy()
        return

    # Extract using configured locations
    print(f"\n{'='*60}")
    print(f"Testing: {os.path.basename(pdf_path)}")
    print(f"Supplier: {supplier_code}")
    print(f"{'='*60}\n")

    location = get_supplier_location(supplier_code)

    # Test PO extraction
    if "po" in location:
        print("PO Location:", location["po"])
        po = extract_po_from_location(pdf_path, supplier_code)
        print(f"Extracted PO: {po if po else 'NOT FOUND'}\n")
    else:
        print("No PO location configured\n")

    # Test Amount extraction
    if "amount" in location:
        print("Amount Location:", location["amount"])
        amount = extract_amount_from_location(pdf_path, supplier_code)
        print(f"Extracted Amount: {amount if amount else 'NOT FOUND'}\n")
    else:
        print("No Amount location configured\n")

    print(f"{'='*60}")

    # Show results in dialog
    result_text = f"Supplier: {supplier_code}\n\n"
    if "po" in location:
        po = extract_po_from_location(pdf_path, supplier_code)
        result_text += f"PO: {po if po else 'NOT FOUND'}\n"
    if "amount" in location:
        amount = extract_amount_from_location(pdf_path, supplier_code)
        result_text += f"Amount: {amount if amount else 'NOT FOUND'}\n"

    messagebox.showinfo("Test Results", result_text)

    root.destroy()


if __name__ == "__main__":
    test_single_file()

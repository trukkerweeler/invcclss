"""GUI for Invoice Classifier application."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from config import APP_TITLE, DEFAULT_LOG_HEIGHT, DEFAULT_LOG_WIDTH
from file_ops import rename_file
from pdf_utils import extract_text, get_ocr_enabled, set_ocr_enabled
from classifier import (
    load_profiles,
    save_profiles,
    train_supplier_profiles,
    classify_invoice,
)
from location_extraction.extractor import (
    extract_po_from_location,
    extract_amount_from_location,
)
from location_extraction.config import get_supplier_location, load_config
from document_processor import DocumentProcessor


class InvoiceClassifierApp:
    """Main GUI application for invoice classification."""

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.profiles = load_profiles()
        self.vectorizer = None
        self.sample_vectors = []
        self.sample_labels = []

        # Create menu bar
        menubar = tk.Menu(root)
        root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="Document Processor", command=self.open_document_processor
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(
            label="Test Location Extraction", command=self.test_location_extraction
        )

        # Buttons
        tk.Button(root, text="Add Sample Invoices", command=self.add_samples).pack()
        tk.Button(
            root, text="Classify New Invoices", command=self.classify_invoices
        ).pack()

        # OCR Toggle
        self.ocr_var = tk.BooleanVar(value=get_ocr_enabled())
        self.ocr_check = tk.Checkbutton(
            root, text="Enable OCR", variable=self.ocr_var, command=self.toggle_ocr
        )
        self.ocr_check.pack()

        # Log
        self.log = tk.Text(root, height=DEFAULT_LOG_HEIGHT, width=DEFAULT_LOG_WIDTH)
        self.log.pack()
        self.log.insert(
            tk.END, f"OCR status: {'Enabled' if get_ocr_enabled() else 'Disabled'}\n"
        )

    def toggle_ocr(self):
        """Toggle OCR functionality on/off."""
        set_ocr_enabled(self.ocr_var.get())
        self.log.insert(
            tk.END, f"OCR manually {'enabled' if self.ocr_var.get() else 'disabled'}\n"
        )

    def open_document_processor(self):
        """Open the document processor in a new window."""
        processor_window = tk.Toplevel(self.root)
        processor_window.geometry("1400x900")
        app = DocumentProcessor(processor_window)
        self.log.insert(tk.END, "Document Processor opened\n")

    def add_samples(self):
        """Add sample invoices for training."""
        files = filedialog.askopenfilenames(title="Select Sample PDFs")
        supplier = simpledialog.askstring("Supplier", "Enter supplier name:")
        if supplier and files:
            for f in files:
                text = extract_text(f)
                self.profiles.setdefault(supplier, []).append(text)
            save_profiles(self.profiles)
            self.log.insert(tk.END, f"Added {len(files)} samples for {supplier}\n")

    def classify_invoices(self):
        """Classify and rename new invoices based on trained profiles."""
        if not self.profiles:
            messagebox.showerror(
                "Error", "No supplier profiles available. Add samples first."
            )
            return
        self.vectorizer, self.sample_vectors, self.sample_labels = (
            train_supplier_profiles(self.profiles)
        )
        files = filedialog.askopenfilenames(title="Select Invoices to Classify")
        for f in files:
            text = extract_text(f)
            supplier, invoice_date, confidence = classify_invoice(
                text,
                self.vectorizer,
                self.sample_vectors,
                self.sample_labels,
                threshold=0.3,
            )

            filename = os.path.basename(f)
            if supplier == "UNKNOWN":
                self.log.insert(
                    tk.END,
                    f"Skipped {filename} - confidence too low ({confidence:.3f})\n",
                )
                continue

            suffix = f"{invoice_date}_{supplier}" if invoice_date else supplier
            new_path = rename_file(f, suffix)
            self.log.insert(
                tk.END,
                f"Renamed to {os.path.basename(new_path)} (confidence: {confidence:.3f})\n",
            )

    def test_location_extraction(self):
        """Test a single PDF file against configured location patterns."""
        # Get supplier code
        supplier_code = simpledialog.askstring(
            "Test Location Extraction", "Enter supplier code:"
        )

        if not supplier_code:
            return

        # Check if supplier has location patterns defined
        config = load_config()
        if supplier_code not in config:
            messagebox.showerror(
                "Error", f"No location patterns defined for {supplier_code}"
            )
            return

        # Get PDF file
        pdf_path = filedialog.askopenfilename(
            title=f"Select PDF to test for {supplier_code}",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )

        if not pdf_path:
            return

        # Extract using configured locations
        self.log.insert(self.log.tk.END, f"\n{'='*60}\n")
        self.log.insert(self.log.tk.END, f"Testing: {os.path.basename(pdf_path)}\n")
        self.log.insert(self.log.tk.END, f"Supplier: {supplier_code}\n")
        self.log.insert(self.log.tk.END, f"{'='*60}\n")

        location = get_supplier_location(supplier_code)

        # Test PO extraction
        if "po" in location:
            self.log.insert(self.log.tk.END, f"PO Location: {location['po']}\n")
            po = extract_po_from_location(pdf_path, supplier_code)
            self.log.insert(
                self.log.tk.END, f"Extracted PO: {po if po else 'NOT FOUND'}\n"
            )
        else:
            self.log.insert(self.log.tk.END, "No PO location configured\n")

        # Test Amount extraction
        if "amount" in location:
            self.log.insert(self.log.tk.END, f"Amount Location: {location['amount']}\n")
            amount = extract_amount_from_location(pdf_path, supplier_code)
            self.log.insert(
                self.log.tk.END,
                f"Extracted Amount: {amount if amount else 'NOT FOUND'}\n",
            )
        else:
            self.log.insert(self.log.tk.END, "No Amount location configured\n")

        self.log.insert(self.log.tk.END, f"{'='*60}\n\n")
        self.log.see(self.log.tk.END)

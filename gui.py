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


class InvoiceClassifierApp:
    """Main GUI application for invoice classification."""

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.profiles = load_profiles()
        self.vectorizer = None
        self.sample_vectors = []
        self.sample_labels = []

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

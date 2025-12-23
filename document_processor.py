"""
Document processor with side-by-side PDF viewer and form editor.
Allows iterating through PDF files, extracting data via location and text patterns,
and manually editing/saving extracted data.
"""

import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import fitz  # PyMuPDF

from pdf_utils import extract_text, configure_tesseract
from location_extraction.extractor import (
    extract_po_from_location,
    extract_amount_from_location,
)
from location_extraction.config import (
    get_supplier_location,
    has_po_location,
    has_amount_location,
)
from classifier import load_profiles
from db import (
    get_supplier_profile,
    save_extraction_result,
    get_extraction_result,
)


class DocumentProcessor:
    """Process documents with side-by-side PDF and form display."""

    def __init__(self, root):
        self.root = root
        self.root.title("Document Processor - PDF Viewer & Editor")

        # State
        self.current_pdf_path = None
        self.current_supplier_code = None
        self.pdf_document = None
        self.current_page = 0
        self.file_list = []
        self.current_file_index = 0

        # Progress tracking
        self.files_saved = 0
        self.files_skipped = 0
        self.already_saved_files = set()

        # Extract data
        self.extracted_data = {
            "filename": "",
            "supplier_code": "",
            "po_number": "",
            "amount": "",
            "check_no": "",
            "receiver_id": "",
        }

        # Create menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Folder", command=self.browse_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Create UI
        self.create_layout()

    def create_layout(self):
        """Create the main layout with left PDF panel and right form panel."""

        # Top toolbar
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Browse Folder", command=self.browse_folder).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Previous", command=self.previous_document).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Next", command=self.next_document).pack(
            side=tk.LEFT, padx=2
        )

        self.file_label = ttk.Label(toolbar, text="No file loaded")
        self.file_label.pack(side=tk.LEFT, padx=10)

        # Main content area
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left side - PDF viewer
        left_frame = ttk.LabelFrame(main_frame, text="PDF Viewer")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.pdf_canvas = tk.Canvas(left_frame, bg="gray", width=600, height=800)
        self.pdf_canvas.pack(fill=tk.BOTH, expand=True)

        pdf_toolbar = ttk.Frame(left_frame)
        pdf_toolbar.pack(fill=tk.X, pady=5)

        ttk.Button(pdf_toolbar, text="Prev Page", command=self.prev_pdf_page).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(pdf_toolbar, text="Next Page", command=self.next_pdf_page).pack(
            side=tk.LEFT, padx=2
        )
        self.page_label = ttk.Label(pdf_toolbar, text="Page: -")
        self.page_label.pack(side=tk.LEFT, padx=10)

        # Right side - Form editor
        right_frame = ttk.LabelFrame(main_frame, text="Extracted Data")
        right_frame.pack(
            side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(5, 0), width=400
        )

        # Form fields
        fields_frame = ttk.Frame(right_frame)
        fields_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.form_fields = {}
        field_specs = [
            ("filename", "Filename:", False),
            ("supplier_code", "Supplier Code:", True),
            ("po_number", "PO Number:", True),
            ("amount", "Amount:", True),
            ("check_no", "Check No:", True),
            ("receiver_id", "Receiver ID:", True),
        ]

        for field_name, label_text, editable in field_specs:
            frame = ttk.Frame(fields_frame)
            frame.pack(fill=tk.X, pady=5)

            ttk.Label(frame, text=label_text, width=15).pack(side=tk.LEFT)

            if field_name == "filename":
                # Filename is read-only
                var = tk.StringVar()
                entry = ttk.Entry(frame, textvariable=var, state="readonly")
            else:
                var = tk.StringVar()
                entry = ttk.Entry(frame, textvariable=var)

            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.form_fields[field_name] = {
                "var": var,
                "widget": entry,
                "editable": editable,
            }

        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)

        ttk.Button(
            button_frame, text="Extract Data", command=self.extract_data_from_pdf
        ).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Save Record", command=self.save_record).pack(
            fill=tk.X, pady=2
        )
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).pack(
            fill=tk.X, pady=2
        )

        # Progress section
        progress_frame = ttk.LabelFrame(right_frame, text="Progress", padding=5)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(fill=tk.X, pady=3)

        self.progress_label = ttk.Label(
            progress_frame, text="0/0 saved", font=("Arial", 9)
        )
        self.progress_label.pack()

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_folder(self):
        """Browse and select a folder of PDFs to process."""
        folder = filedialog.askdirectory(title="Select folder with PDFs")
        if not folder:
            return

        # Find all PDF files
        self.file_list = sorted([str(p) for p in Path(folder).glob("*.pdf")])

        if not self.file_list:
            messagebox.showwarning(
                "No PDFs", "No PDF files found in the selected folder."
            )
            return

        # Check which files are already saved in database
        already_saved = set()
        for filepath in self.file_list:
            filename = Path(filepath).name
            try:
                result = get_extraction_result(filename)
                if result:
                    already_saved.add(filepath)
            except Exception:
                pass  # File not in database, continue

        # Reset progress tracking - count already saved files
        self.current_file_index = 0
        self.files_saved = len(already_saved)
        self.files_skipped = 0
        self.already_saved_files = already_saved
        self.update_progress()

        # Find first unsaved file to load
        first_unsaved = None
        for i, filepath in enumerate(self.file_list):
            if filepath not in already_saved:
                self.current_file_index = i
                first_unsaved = filepath
                break

        if first_unsaved:
            self.load_document(first_unsaved)
            self.status_var.set(
                f"Loaded {len(self.file_list)} PDFs ({len(already_saved)} already saved)"
            )
        else:
            messagebox.showinfo(
                "All Complete",
                f"All {len(self.file_list)} files in this folder have been processed!",
            )
            self.status_var.set("All files processed!")

    def load_document(self, filepath: str):
        """Load a PDF document and extract filename info."""
        self.current_pdf_path = filepath

        # Close previous document
        if self.pdf_document:
            self.pdf_document.close()

        # Open new document
        try:
            self.pdf_document = fitz.open(filepath)
            self.current_page = 0

            # Parse filename to get supplier code
            filename = Path(filepath).name
            self.extracted_data["filename"] = filename
            self.form_fields["filename"]["var"].set(filename)

            # Update file label with progress
            if self.file_list:
                progress_text = f"File {self.current_file_index + 1}/{len(self.file_list)} - {self.files_saved} saved"
                self.file_label.config(text=progress_text)

            # Try to extract supplier code from filename pattern: YYYY-MM_XXXXX_
            match = re.match(r"\d{4}-\d{2}_([A-Z0-9]+)_", filename)
            if match:
                supplier_code = match.group(1)
                self.current_supplier_code = supplier_code
                self.extracted_data["supplier_code"] = supplier_code
                self.form_fields["supplier_code"]["var"].set(supplier_code)
                self.status_var.set(f"Loaded: {filename} (Supplier: {supplier_code})")
            else:
                self.current_supplier_code = None
                self.status_var.set(
                    f"Loaded: {filename} (No supplier code in filename)"
                )

            # Display first page
            self.display_pdf_page(0)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open PDF: {e}")
            self.status_var.set("Error loading PDF")

    def display_pdf_page(self, page_num: int):
        """Display a specific page of the PDF."""
        if not self.pdf_document or page_num < 0 or page_num >= len(self.pdf_document):
            return

        self.current_page = page_num

        # Render page to image
        page = self.pdf_document[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))  # 1.5x zoom
        img_data = pix.tobytes("ppm")

        # Convert to PIL Image
        from io import BytesIO

        img = Image.open(BytesIO(img_data))

        # Convert to PhotoImage
        self.pdf_photo = ImageTk.PhotoImage(img)

        # Display on canvas
        self.pdf_canvas.delete("all")
        self.pdf_canvas.create_image(0, 0, image=self.pdf_photo, anchor=tk.NW)
        self.pdf_canvas.config(scrollregion=self.pdf_canvas.bbox("all"))

        self.page_label.config(text=f"Page: {page_num + 1}/{len(self.pdf_document)}")

    def prev_pdf_page(self):
        """Go to previous PDF page."""
        if self.pdf_document:
            self.display_pdf_page(max(0, self.current_page - 1))

    def next_pdf_page(self):
        """Go to next PDF page."""
        if self.pdf_document:
            self.display_pdf_page(
                min(len(self.pdf_document) - 1, self.current_page + 1)
            )

    def previous_document(self):
        """Load previous document in the list."""
        if self.file_list and self.current_file_index > 0:
            self.current_file_index -= 1
            self.load_document(self.file_list[self.current_file_index])
            self.file_label.config(
                text=f"File {self.current_file_index + 1}/{len(self.file_list)}"
            )

    def next_document(self):
        """Load next document in the list, skipping already-saved files."""
        if self.file_list and self.current_file_index < len(self.file_list) - 1:
            # Find next unsaved file
            for i in range(self.current_file_index + 1, len(self.file_list)):
                if self.file_list[i] not in self.already_saved_files:
                    self.current_file_index = i
                    self.load_document(self.file_list[self.current_file_index])
                    self.file_label.config(
                        text=f"File {self.current_file_index + 1}/{len(self.file_list)} - {self.files_saved} saved"
                    )
                    return

            # If no unsaved files found, show message
            messagebox.showinfo("Complete", "All remaining files have been processed!")
            self.status_var.set("All files in folder processed!")

    def extract_data_from_pdf(self):
        """Extract data from PDF using location patterns, then text patterns."""
        if not self.current_pdf_path:
            messagebox.showwarning("No PDF", "Please load a PDF first")
            return

        supplier_code = self.extracted_data.get("supplier_code")
        if not supplier_code:
            messagebox.showwarning(
                "No Supplier", "Supplier code must be identified first"
            )
            return

        self.status_var.set("Extracting data...")
        self.root.update()

        try:
            # Try location-based extraction first
            if has_po_location(supplier_code):
                po = extract_po_from_location(self.current_pdf_path, supplier_code)
                if po:
                    self.extracted_data["po_number"] = po
                    self.form_fields["po_number"]["var"].set(po)

            if has_amount_location(supplier_code):
                amount = extract_amount_from_location(
                    self.current_pdf_path, supplier_code
                )
                if amount:
                    self.extracted_data["amount"] = str(amount)
                    self.form_fields["amount"]["var"].set(str(amount))

            # Fall back to text pattern extraction for missing fields
            if not self.extracted_data.get("po_number") or not self.extracted_data.get(
                "amount"
            ):
                text = extract_text(self.current_pdf_path)

                # Try text patterns from profiles
                profiles = load_profiles()

                # Look for PO patterns if not found by location
                if not self.extracted_data.get("po_number"):
                    po = self._extract_by_patterns(
                        text, ["PO", "PO NO", "PO#", "Purchase Order"]
                    )
                    if po:
                        self.extracted_data["po_number"] = po
                        self.form_fields["po_number"]["var"].set(po)

                # Look for amount patterns if not found by location
                if not self.extracted_data.get("amount"):
                    amount = self._extract_by_patterns(
                        text, ["Total", "Amount", "Invoice Total"]
                    )
                    if amount:
                        self.extracted_data["amount"] = amount
                        self.form_fields["amount"]["var"].set(amount)

            self.status_var.set("Data extracted. Review and edit as needed, then save.")

        except Exception as e:
            messagebox.showerror("Extraction Error", f"Failed to extract data: {e}")
            self.status_var.set("Extraction failed")

    def _extract_by_patterns(self, text: str, patterns: list) -> Optional[str]:
        """Extract value following text patterns."""
        text_lower = text.lower()

        for pattern in patterns:
            # Look for pattern followed by colon, space, or equals
            idx = text_lower.find(pattern.lower())
            if idx != -1:
                # Extract line after pattern
                end_idx = text.find("\n", idx)
                if end_idx == -1:
                    line = text[idx + len(pattern) :]
                else:
                    line = text[idx + len(pattern) : end_idx]

                # Clean up and extract value
                line = line.strip()
                if line.startswith(":") or line.startswith("="):
                    line = line[1:].strip()

                # Extract first numeric value or dollar amount
                match = re.search(r"[\$]?[\d,]+\.?\d*", line)
                if match:
                    return match.group(0)

        return None

    def update_progress(self):
        """Update progress bar and label."""
        if self.file_list:
            total_files = len(self.file_list)
            progress_percent = (self.files_saved / total_files) * 100
            self.progress_var.set(progress_percent)
            self.progress_label.config(
                text=f"{self.files_saved}/{total_files} saved  |  {self.files_skipped} skipped"
            )
        else:
            self.progress_var.set(0)
            self.progress_label.config(text="0/0 saved")

    def save_record(self):
        """Save the extracted record to the database."""
        if not self.current_pdf_path:
            messagebox.showwarning("No PDF", "Please load a PDF first")
            return

        # Get current form values
        data = {}
        for field_name, field_info in self.form_fields.items():
            data[field_name] = field_info["var"].get()

        supplier_code = data.get("supplier_code")
        if not supplier_code:
            messagebox.showwarning("Missing Data", "Supplier code is required")
            return

        try:
            # Save to database
            save_extraction_result(
                filename=data.get("filename"),
                file_path=self.current_pdf_path,
                supplier_code=supplier_code,
                po_number=data.get("po_number"),
                amount=data.get("amount"),
                check_no=data.get("check_no"),
                receiver_id=data.get("receiver_id"),
                human_field="Y",  # User edited this record
            )

            # Mark file as saved
            self.already_saved_files.add(self.current_pdf_path)

            # Update progress
            self.files_saved += 1
            self.update_progress()

            messagebox.showinfo("Success", f"Record saved for {data.get('filename')}")
            self.status_var.set(f"Saved: {data.get('filename')}")

            # Move to next document
            if len(self.file_list) > 0:
                self.next_document()

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save record: {e}")

    def clear_form(self):
        """Clear all form fields."""
        for field_name, field_info in self.form_fields.items():
            if field_info["editable"]:
                field_info["var"].set("")
            if field_name == "supplier_code":
                # Keep supplier code if it was extracted from filename
                if self.current_supplier_code:
                    field_info["var"].set(self.current_supplier_code)


def run_document_processor():
    """Run the document processor application."""
    root = tk.Tk()
    root.geometry("1400x900")
    app = DocumentProcessor(root)
    root.mainloop()


if __name__ == "__main__":
    run_document_processor()

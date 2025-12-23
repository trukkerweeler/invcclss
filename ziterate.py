"""
PO Number extraction from PDF files with batch processing support.
Iterates through PDFs, extracts PO numbers, and saves to JSON with progress tracking.
Includes visual confirmation UI for extracted PO numbers.
"""

import os
import re
import json
import glob
import io
from pathlib import Path
from pdf_utils import extract_text, configure_tesseract
from classifier import load_profiles, save_profiles
from db import (
    get_po_profiles, save_po_profiles, add_classification_samples,
    add_supplier_profile, get_supplier_profile, get_all_supplier_profiles,
    save_extraction_result, get_extraction_result, get_unprocessed_files,
    update_extraction_status
)
from typing import Dict, Optional, List, Tuple
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
import fitz  # PyMuPDF

# Configuration
SCAN_DIRECTORY = r"C:\Users\tim\OneDrive\Documents\Work\CI\APScans"
RESULTS_FILE = "po_extraction_results.json"
PROGRESS_FILE = "po_extraction_progress.json"
UNCONFIRMED_FILE = "po_unconfirmed.json"
SUPPLIER_PROFILES_FILE = "supplier_profiles.json"
PO_DETECTION_PROFILES_FILE = "po_detection_profiles.json"

# PO number patterns - Looking for 5 digit POs (e.g., 40085) or 7 digit with leading 00 (e.g., 0040085)
# Optional -dd suffix for line numbers (e.g., 40085-05 or 0040085-05)
PO_PATTERNS = [
    # PO/PO./P.O./PURCHASE ORDER/Order followed by number
    r"(?:P\.?\s*O\.?|PO|PURCHASE\s+ORDER|Order)\s*[#:\s]+([0-9]{5}(?:-\d{2})?|0{2}[0-9]{5}(?:-\d{2})?)",
    # PO NUMBER / PO #
    r"(?:PO|Purchase\s+Order)\s+(?:Number|#)?\s*([0-9]{5}(?:-\d{2})?|0{2}[0-9]{5}(?:-\d{2})?)",
    # Just the PO number on its own line - 5 or 7 digits
    r"^([0-9]{5}(?:-\d{2})?|0{2}[0-9]{5}(?:-\d{2})?)$",
    # PO after phone number ending (4 digits) - e.g., "-5590 0040644-00" matches 40644-00
    r"-\d{4}\s+([0-9]{5}(?:-\d{2})?|0{2}[0-9]{5}(?:-\d{2})?)",
]


def load_progress() -> Dict:
    """Load processing progress from file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"completed": [], "failed": []}
    return {"completed": [], "failed": []}


def save_progress(progress: Dict):
    """Save processing progress to file."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def load_results() -> Dict:
    """Load existing results from file."""
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_results(results: Dict):
    """Save results to JSON file."""
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def extract_po_number(text: str) -> List[str]:
    """Extract all potential PO numbers from text using multiple patterns."""
    # Normalize and collapse digit-only whitespace that can be introduced by OCR
    text_upper = text.upper()
    collapsed_upper = re.sub(r"(?<=\d)\s+(?=\d)", "", text_upper)
    po_matches = set()

    for pattern in PO_PATTERNS:
        # Try matching on collapsed text first (handles OCR splits like '00407 48')
        matches = re.findall(pattern, collapsed_upper,
                             re.IGNORECASE | re.MULTILINE)
        if not matches:
            matches = re.findall(pattern, text_upper,
                                 re.IGNORECASE | re.MULTILINE)
        for match in matches:
            # Validate format: 5 digits or 7 digits (00XXXXX), optionally with -dd suffix
            if re.match(r"^([0-9]{5}|0{2}[0-9]{5})(-\d{2})?$", match):
                # Strip leading zeros from the main number part
                if "-" in match:
                    # Handle format like "0040085-05" or "40085-05"
                    main_part, suffix = match.split("-")
                    # Convert to int to strip zeros, back to string
                    main_part = str(int(main_part))
                    po_matches.add(f"{main_part}-{suffix}")
                else:
                    # Handle format like "0040085" or "40085"
                    po_matches.add(str(int(match)))

    return sorted(list(po_matches), key=lambda x: int(x.split("-")[0]))


# PO detection profiles are persisted via SQLite (db.py)


def extract_amount_from_text(text: str, supplier: Optional[str] = None) -> Optional[str]:
    """Extract amount from text, optionally using supplier-specific patterns.

    Args:
        text: Document text
        supplier: Supplier code to use supplier-specific patterns

    Returns:
        Extracted amount as string, or None if not found
    """
    po_profiles = get_po_profiles()

    # Helper to clean and validate amount string
    def _clean_amount(s: str) -> Optional[str]:
        if not s:
            return None
        amt = s.replace(",", "").replace("$", "").strip()
        # remove trailing non-numeric chars
        m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", amt)
        if m:
            try:
                float(m.group(1))
                return m.group(1)
            except ValueError:
                return None
        return None

    # Try supplier-specific patterns first (patterns may be plain labels or full regexes)
    if supplier and supplier in po_profiles:
        supplier_profile = po_profiles[supplier]
        amount_patterns = supplier_profile.get("amount_patterns", [])
        for pattern in amount_patterns:
            # Try treating pattern as a regex first
            try:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    # If pattern contains a capturing group, prefer it
                    if m.groups():
                        amt = _clean_amount(m.group(1))
                        if amt:
                            return amt
                    # Otherwise try finding a numeric amount inside the match
                    amt = _clean_amount(m.group(0))
                    if amt:
                        return amt
            except re.error:
                # Not a valid regex - fall back to label + amount search
                match = re.search(
                    rf"{re.escape(pattern)}\s*[:\$\-]*\s*([0-9,]+\.?[0-9]*)", text, re.IGNORECASE)
                if match:
                    amt = _clean_amount(match.group(1))
                    if amt:
                        return amt

    # Stronger generic amount patterns as fallback
    generic_patterns = [
        r"(?:Total|Invoice\s*Total|Amount\s*Due|Amount|Balance\s*Due)\s*[:\-]*\s*\$?\s*([0-9,]+\.[0-9]{2})",
        r"Subtotal\s*[:\-]*\s*\$?\s*([0-9,]+\.[0-9]{2})",
        r"\$\s*([0-9,]+\.[0-9]{2})",
    ]

    for pattern in generic_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amt = _clean_amount(match.group(1))
            if amt:
                return amt

    return None


def extract_po_with_supplier_profile(text: str, supplier: Optional[str] = None) -> List[str]:
    """Extract PO numbers using supplier-specific patterns, with fallback to generic patterns.

    Args:
        text: Document text
        supplier: Supplier code to use supplier-specific patterns

    Returns:
        List of extracted PO numbers
    """
    po_profiles = get_po_profiles()
    # Collapse digit whitespace to recover numbers split by OCR
    collapsed_text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    po_matches = set()
    blan1_match_found = False
    elad01_match_found = False

    # Hard-coded supplier-specific patterns
    if supplier == "BLAN1":
        # BLAN1: POs appear after "5590" (phone number ending)
        # Try both original and collapsed text to handle OCR splits
        # Example: "972-5590 0040702-00" should match "40702-00"
        # Pattern order matters: try 7-digit (00XXXXX) FIRST before 5-digit to avoid partial matches
        pattern = r"5590\s+(0{2}[0-9]{5}(?:-\d{2})?|[0-9]{5}(?:-\d{2})?)"

        # Try on collapsed text first (in case digits are split)
        match = re.search(pattern, collapsed_text, re.IGNORECASE)
        if not match:
            # Try on original text
            match = re.search(pattern, text, re.IGNORECASE)

        # DEBUG: Print what we're searching for
        if not match:
            print(f"[DEBUG BLAN1] Pattern not found. Searching for: 5590")
            print(
                f"[DEBUG BLAN1] Collapsed text contains '5590': {'5590' in collapsed_text}")
            print(
                f"[DEBUG BLAN1] Original text contains '5590': {'5590' in text}")
            # Show lines that contain digits and "0040702"
            if "0040702" in text:
                print(f"[DEBUG BLAN1] Found '0040702' in text")
                # Find context around it
                idx = text.find("0040702")
                print(
                    f"[DEBUG BLAN1] Context: ...{text[max(0, idx-50):idx+50]}...")

        if match:
            po = match.group(1)
            # Normalize PO (strip leading zeros)
            if "-" in po:
                main_part, suffix = po.split("-")
                po = f"{int(main_part)}-{suffix}"
            else:
                po = str(int(po))
            po_matches.add(po)
            blan1_match_found = True  # Mark that we found a BLAN1 match

    # Hard-coded supplier-specific patterns for ASSP01
    if supplier == "ASSP01":
        # ASSP01: POs appear after "PO#" label
        # Try both original and collapsed text to handle OCR splits
        # Example: "PO# 0040676-00" should match "40676-00"
        # Pattern order matters: try 7-digit (00XXXXX) FIRST before 5-digit to avoid partial matches
        pattern = r"PO#\s+(0{2}[0-9]{5}(?:-\d{2})?|[0-9]{5}(?:-\d{2})?)"

        # Try on collapsed text first (in case digits are split)
        match = re.search(pattern, collapsed_text, re.IGNORECASE)
        if not match:
            # Try on original text
            match = re.search(pattern, text, re.IGNORECASE)

        if match:
            po = match.group(1)
            # Normalize PO (strip leading zeros)
            if "-" in po:
                main_part, suffix = po.split("-")
                po = f"{int(main_part)}-{suffix}"
            else:
                po = str(int(po))
            po_matches.add(po)

    # Hard-coded supplier-specific patterns for ELAD01
    if supplier == "ELAD01":
        # ELAD01: Use generic patterns but only keep the first match
        generic_matches = extract_po_number(text)
        if generic_matches:
            po_matches.add(generic_matches[0])  # Only add first match
            # Set flag to skip generic pattern fallback later
            elad01_match_found = True

    # Try supplier-specific patterns first (from database)
    if supplier and supplier in po_profiles:
        supplier_profile = po_profiles[supplier]
        po_patterns = supplier_profile.get("po_patterns", [])
        for pattern_label in po_patterns:
            # Search for the pattern label followed by a PO number
            # Handles formats like "PO/Rel 0040303-00"
            # Try on collapsed_text first to handle OCR splits
            pattern = rf"{re.escape(pattern_label)}\s+([0-9]{{5}}(?:-\d{{2}})?|0{{2}}[0-9]{{5}}(?:-\d{{2}})?)?"
            match = re.search(pattern, collapsed_text, re.IGNORECASE)
            if not match:
                match = re.search(pattern, text, re.IGNORECASE)
            if match:
                po = match.group(1)
                # Normalize PO (strip leading zeros)
                if "-" in po:
                    main_part, suffix = po.split("-")
                    po = f"{int(main_part)}-{suffix}"
                else:
                    po = str(int(po))
                po_matches.add(po)

    # Fall back to generic patterns only if no specific supplier match was found
    # For BLAN1 and ELAD01, don't use generic patterns if we found a match (avoid conflicting matches)
    if supplier == "BLAN1":
        # For BLAN1, only use generic patterns if BLAN1 pattern didn't match
        if not blan1_match_found and not po_matches:
            generic_matches = extract_po_number(text)
            po_matches.update(generic_matches)
    elif supplier == "ELAD01":
        # For ELAD01, only use generic patterns if we didn't already find a match
        # (ELAD01 already extracts first match only, so skip generic if found)
        if not elad01_match_found and not po_matches:
            generic_matches = extract_po_number(text)
            if generic_matches:
                po_matches.add(generic_matches[0])  # Only first match
    else:
        # For other suppliers, use generic if nothing matched
        if not po_matches:
            generic_matches = extract_po_number(text)
            po_matches.update(generic_matches)

    return sorted(list(po_matches), key=lambda x: int(x.split("-")[0]))


def extract_supplier_code(filename: str) -> Optional[str]:
    """Extract supplier code from filename.

    Example: '2023-03_AFFI1_SKM_C36825121315590 8.pdf' -> 'AFFI1'
    Pattern: YYYY-MM_SUPPLIERCODE_...
    """
    match = re.search(r'^\d{4}-\d{2}_([A-Z0-9]+)_', filename)
    return match.group(1) if match else None


def open_supplier_profile_manager():
    """Open GUI to manage supplier training profiles and PO detection patterns."""
    root = tk.Tk()
    root.title("Supplier Profile Manager")
    root.geometry("700x550")

    profiles = load_profiles()
    po_profiles = get_po_profiles()

    # Title
    ttk.Label(root, text="Supplier Training Profiles & PO Detection",
              font=("Arial", 14, "bold")).pack(pady=10)

    # Notebook for tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Tab 1: Supplier Classification
    class_frame = ttk.Frame(notebook)
    notebook.add(class_frame, text="Supplier Classification")

    ttk.Label(class_frame, text="Training samples for supplier classification (for gui.py)",
              font=("Arial", 10), foreground="gray").pack(pady=5)

    # Scrollable list
    canvas1 = tk.Canvas(class_frame, bg='white', highlightthickness=0)
    scrollbar1 = ttk.Scrollbar(
        class_frame, orient="vertical", command=canvas1.yview)
    scroll_frame1 = ttk.Frame(canvas1)

    scroll_frame1.bind(
        "<Configure>",
        lambda e: canvas1.configure(scrollregion=canvas1.bbox("all"))
    )

    canvas1.create_window((0, 0), window=scroll_frame1, anchor="nw")
    canvas1.configure(yscrollcommand=scrollbar1.set)

    if profiles:
        for supplier, samples in profiles.items():
            ttk.Label(scroll_frame1, text=f"{supplier}: {len(samples)} samples",
                      font=("Arial", 10)).pack(anchor=tk.W, pady=5)
    else:
        ttk.Label(scroll_frame1, text="No profiles yet. Add samples to get started.",
                  font=("Arial", 10), foreground="orange").pack(anchor=tk.W, pady=10)

    canvas1.pack(side="left", fill="both", expand=True)
    scrollbar1.pack(side="right", fill="y")

    # Tab 2: PO Detection
    po_frame = ttk.Frame(notebook)
    notebook.add(po_frame, text="PO Detection Patterns")

    ttk.Label(po_frame, text="PO and Amount detection patterns per supplier",
              font=("Arial", 10), foreground="gray").pack(pady=5)

    # Scrollable list for PO profiles
    canvas2 = tk.Canvas(po_frame, bg='white', highlightthickness=0)
    scrollbar2 = ttk.Scrollbar(
        po_frame, orient="vertical", command=canvas2.yview)
    scroll_frame2 = ttk.Frame(canvas2)

    scroll_frame2.bind(
        "<Configure>",
        lambda e: canvas2.configure(scrollregion=canvas2.bbox("all"))
    )

    canvas2.create_window((0, 0), window=scroll_frame2, anchor="nw")
    canvas2.configure(yscrollcommand=scrollbar2.set)

    if po_profiles:
        for supplier, profile in po_profiles.items():
            po_patterns = len(profile.get("po_patterns", []))
            amt_patterns = len(profile.get("amount_patterns", []))
            samples = len(profile.get("samples", []))
            ttk.Label(scroll_frame2, text=f"{supplier}: {po_patterns} PO patterns, {amt_patterns} amount patterns, {samples} samples",
                      font=("Arial", 10)).pack(anchor=tk.W, pady=5)
    else:
        ttk.Label(scroll_frame2, text="No PO detection profiles yet.",
                  font=("Arial", 10), foreground="orange").pack(anchor=tk.W, pady=10)

    canvas2.pack(side="left", fill="both", expand=True)
    scrollbar2.pack(side="right", fill="y")

    # Buttons
    button_frame = ttk.Frame(root)
    button_frame.pack(fill=tk.X, padx=10, pady=10)

    def add_classification_samples():
        """Add training samples for supplier classification."""
        files = filedialog.askopenfilenames(
            title="Select Sample PDFs for Supplier Classification",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not files:
            return

        supplier = simpledialog.askstring("Supplier Code",
                                          "Enter supplier code (e.g., AFFI1):",
                                          parent=root)
        if not supplier:
            return

        supplier = supplier.upper().strip()

        # Extract text from PDFs and add to profiles
        count = 0
        for filepath in files:
            try:
                text = extract_text(filepath)
                profiles.setdefault(supplier, []).append(text)
                count += 1
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to process {os.path.basename(filepath)}: {str(e)}")

        save_profiles(profiles)
        messagebox.showinfo(
            "Success", f"Added {count} samples for supplier {supplier}")
        root.destroy()
        open_supplier_profile_manager()  # Refresh the window

    def add_po_detection():
        """Add PO detection patterns for a supplier."""
        supplier = simpledialog.askstring("Supplier Code",
                                          "Enter supplier code (e.g., AFFI1):",
                                          parent=root)
        if not supplier:
            return

        supplier = supplier.upper().strip()

        # Ask for PO patterns
        po_pattern_text = simpledialog.askstring("PO Patterns",
                                                 "Enter PO label patterns (comma-separated).\nExample: PO Number:,Purchase Order #,Order #",
                                                 parent=root)
        if not po_pattern_text:
            return

        po_patterns = [p.strip() for p in po_pattern_text.split(",")]

        # Ask for amount patterns
        amt_pattern_text = simpledialog.askstring("Amount Patterns",
                                                  "Enter amount label patterns (comma-separated).\nExample: Total:,Amount Due:,Invoice Total",
                                                  parent=root)
        if not amt_pattern_text:
            return

        amount_patterns = [p.strip() for p in amt_pattern_text.split(",")]

        # Ask for sample PDFs
        files = filedialog.askopenfilenames(
            title="Select Sample PDFs for PO Detection Training",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )

        samples = []
        for filepath in files:
            try:
                text = extract_text(filepath)
                samples.append(text)
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to process {os.path.basename(filepath)}: {str(e)}")

        # Save PO detection profile
        po_profiles[supplier] = {
            "po_patterns": po_patterns,
            "amount_patterns": amount_patterns,
            "samples": samples
        }
        save_po_profiles(po_profiles)

        messagebox.showinfo("Success",
                            f"Added PO detection profile for {supplier}\n"
                            f"PO patterns: {len(po_patterns)}\n"
                            f"Amount patterns: {len(amount_patterns)}\n"
                            f"Samples: {len(samples)}")
        root.destroy()
        open_supplier_profile_manager()  # Refresh the window

    ttk.Button(button_frame, text="Add Classification Samples",
               command=add_classification_samples).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Add PO Detection Profile",
               command=add_po_detection).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Close",
               command=root.destroy).pack(side=tk.LEFT, padx=5)

    root.mainloop()


def open_batch_learn():
    """Batch-select PDFs, preview OCR, validate PO/amount, and save samples for a supplier."""
    files = filedialog.askopenfilenames(title="Select PDFs for Batch Learn", filetypes=[
                                        ("PDF files", "*.pdf"), ("All files", "*.*")])
    if not files:
        return

    supplier = simpledialog.askstring(
        "Supplier", "Enter supplier code to associate with these samples:")
    if not supplier:
        return

    configure_tesseract()

    entries = []
    for f in files:
        try:
            txt = extract_text(f)
        except Exception:
            txt = ""
        po = extract_po_with_supplier_profile(txt, supplier)
        amt = extract_amount_from_text(txt, supplier)
        entries.append({"file": f, "text": txt, "po": po, "amount": amt})

    win = tk.Tk()
    win.title(f"Batch Learn: {supplier}")
    win.geometry("900x600")

    info = ttk.Label(
        win, text=f"Selected {len(entries)} files for supplier {supplier}", font=("Arial", 12))
    info.pack(pady=6)

    canvas = tk.Canvas(win)
    frame = ttk.Frame(canvas)
    vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    canvas.create_window((0, 0), window=frame, anchor='nw')

    def on_frame_config(event):
        canvas.configure(scrollregion=canvas.bbox('all'))

    frame.bind('<Configure>', on_frame_config)

    checks = []
    for i, e in enumerate(entries):
        row = ttk.Frame(frame, relief=tk.RIDGE, padding=6)
        row.pack(fill=tk.X, padx=6, pady=4)
        var = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(row, variable=var)
        chk.pack(side=tk.LEFT)
        fname = os.path.basename(e['file'])
        lbl = ttk.Label(row, text=fname)
        lbl.pack(side=tk.LEFT, padx=8)
        po_lbl = ttk.Label(row, text=f"PO: {e['po'] if e['po'] else 'None'}")
        po_lbl.pack(side=tk.LEFT, padx=8)
        amt_lbl = ttk.Label(
            row, text=f"Amt: {e['amount'] if e['amount'] else 'None'}")
        amt_lbl.pack(side=tk.LEFT, padx=8)

        def make_show(text, fname=fname):
            def _show():
                twin = tk.Toplevel(win)
                twin.title(f"OCR: {fname}")
                txtw = tk.Text(twin, wrap=tk.WORD)
                txtw.pack(fill=tk.BOTH, expand=True)
                for ln, line in enumerate(text.split('\n'), 1):
                    txtw.insert(tk.END, f"{ln:4d}: {line}\n")
                txtw.config(state=tk.DISABLED)
            return _show

        ttk.Button(row, text="Show OCR", command=make_show(
            e['text'])).pack(side=tk.RIGHT, padx=6)
        checks.append((var, e))

    btn_frame = ttk.Frame(win)
    btn_frame.pack(fill=tk.X, padx=8, pady=8)

    def save_selected():
        selected_texts = [e['text'] for v, e in checks if v.get()]
        if not selected_texts:
            messagebox.showinfo("No selection", "No files selected to save")
            return
        add_classification_samples(supplier, selected_texts)
        po_profiles = get_po_profiles()
        prof = po_profiles.get(supplier, {})
        samples = prof.get('samples', [])
        samples.extend(selected_texts)
        prof['samples'] = samples
        po_profiles[supplier] = prof
        save_po_profiles(po_profiles)
        messagebox.showinfo(
            "Saved", f"Saved {len(selected_texts)} samples for {supplier}")

    def configure_patterns():
        """Open dialog to configure PO and amount patterns for this supplier."""
        config_win = tk.Toplevel(win)
        config_win.title(f"Configure Patterns: {supplier}")
        config_win.geometry("600x400")

        ttk.Label(config_win, text=f"PO Patterns for {supplier}", font=(
            "Arial", 12, "bold")).pack(pady=10)

        # Get current patterns
        po_profiles = get_po_profiles()
        current_po = po_profiles.get(supplier, {}).get("po_patterns", [])
        current_amt = po_profiles.get(supplier, {}).get("amount_patterns", [])

        # PO Patterns
        ttk.Label(config_win, text="PO Pattern Labels (one per line):",
                  font=("Arial", 10)).pack(anchor=tk.W, padx=10, pady=5)
        po_text = tk.Text(config_win, height=6, width=60)
        po_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=False)
        po_text.insert(tk.END, "\n".join(current_po))

        ttk.Label(config_win, text="Examples: 'PO#', '5590', 'PO/Rel'",
                  font=("Arial", 9, "italic")).pack(anchor=tk.W, padx=10)

        # Amount Patterns
        ttk.Label(config_win, text="Amount Pattern Labels (one per line):", font=(
            "Arial", 10)).pack(anchor=tk.W, padx=10, pady=(15, 5))
        amt_text = tk.Text(config_win, height=6, width=60)
        amt_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=False)
        amt_text.insert(tk.END, "\n".join(current_amt))

        ttk.Label(config_win, text="Examples: 'Total', 'Amount Due', 'Invoice Total'", font=(
            "Arial", 9, "italic")).pack(anchor=tk.W, padx=10)

        def save_patterns():
            po_patterns = [line.strip() for line in po_text.get(
                "1.0", tk.END).split("\n") if line.strip()]
            amt_patterns = [line.strip() for line in amt_text.get(
                "1.0", tk.END).split("\n") if line.strip()]

            po_profiles = get_po_profiles()
            po_profiles[supplier] = {
                "po_patterns": po_patterns,
                "amount_patterns": amt_patterns
            }
            save_po_profiles(po_profiles)
            messagebox.showinfo("Saved", f"Patterns saved for {supplier}")
            config_win.destroy()

        button_frame = ttk.Frame(config_win)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Save Patterns",
                   command=save_patterns).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel",
                   command=config_win.destroy).pack(side=tk.LEFT, padx=5)

    ttk.Button(btn_frame, text="Save Selected as Samples",
               command=save_selected, width=30).pack(pady=5, anchor=tk.E)
    ttk.Button(btn_frame, text="Configure Patterns",
               command=configure_patterns, width=30).pack(pady=5, anchor=tk.E)
    ttk.Button(btn_frame, text="Close", command=win.destroy, width=30).pack(
        pady=5, anchor=tk.E)

    win.mainloop()


class POConfirmationUI:
    """Visual confirmation UI for PO number extraction."""

    def __init__(self, pdf_path: str, extracted_pos: List[str], filename: str):
        self.pdf_path = pdf_path
        self.extracted_pos = extracted_pos
        self.filename = filename
        self.confirmed_po = None
        self.manual_po = None
        self.amount = None
        self.check_no = None
        self.receiver_id = None
        self.skip = False
        self.skip_remaining = False
        self.manual_entry = None  # Initialize before use
        self.amount_entry = None  # Initialize before use
        self.check_no_entry = None  # Initialize before use
        self.receiver_id_entry = None  # Initialize before use

        # Create window
        self.root = tk.Tk()
        self.root.title(f"PO Confirmation - {filename}")
        self.root.geometry("1400x900")

        # Create main container with left/right layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Control panel (left side - 25%)
        left_frame = ttk.Frame(main_frame, width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        left_frame.pack_propagate(False)
        self.create_control_panel(left_frame)

        # PDF display (right side - 75%)
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.create_pdf_canvas(right_frame)

        # Bind keyboard shortcuts (after manual_entry is created)
        self.root.bind('<Escape>', lambda e: self.skip_file())
        self.root.bind('<s>', lambda e: self.skip_file())
        self.root.bind('<S>', lambda e: self.skip_remaining_batch())
        self.root.bind('<n>', lambda e: self.confirm_no_po())

    def create_pdf_canvas(self, parent_frame):
        """Create canvas to display first page of PDF."""
        frame = ttk.LabelFrame(parent_frame, text="PDF Preview", padding=5)
        frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Canvas for PDF - take up all available space
        self.canvas = tk.Canvas(frame, bg="gray", cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Try to render first page of PDF
        try:
            doc = fitz.open(self.pdf_path)
            if len(doc) > 0:
                page = doc[0]
                # Render page at 150 DPI
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img_data = pix.tobytes("ppm")

                # Convert to PIL Image
                from io import BytesIO
                img = Image.open(BytesIO(img_data))

                # Scale to fit canvas
                img.thumbnail((1080, 720), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
                self.canvas.config(width=img.width, height=img.height)
            doc.close()
        except Exception as e:
            self.canvas.create_text(450, 300, text=f"Could not render PDF\n{str(e)}",
                                    fill="white", font=("Arial", 12))

    def create_control_panel(self, parent_frame):
        """Create control panel with PO options and buttons."""
        # Create scrollable frame for controls
        canvas = tk.Canvas(parent_frame, bg='gray95', highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            parent_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Main control frame inside scrollable area
        frame = ttk.LabelFrame(
            scrollable_frame, text="PO Number Selection", padding=8)
        frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # Extracted POs display
        if self.extracted_pos:
            ttk.Label(frame, text="Extracted PO options:", font=(
                "Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

            for po in self.extracted_pos:
                btn_frame = ttk.Frame(frame)
                btn_frame.pack(anchor=tk.W, pady=2)

                btn = ttk.Button(btn_frame, text=f"Select: {po}",
                                 command=lambda p=po: self._copy_po_to_manual(p))
                btn.pack(side=tk.LEFT)
                ttk.Label(btn_frame, text="", font=(
                    "Arial", 9)).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Label(frame, text="No PO numbers automatically detected",
                      foreground="orange", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        # Manual entry
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(frame, text="Or enter manually (5 digits: 40085 or 7 digits: 0040085, optional -dd):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        entry_frame = ttk.Frame(frame)
        entry_frame.pack(anchor=tk.W, pady=5)

        self.manual_entry = ttk.Entry(
            entry_frame, width=30, font=("Arial", 10))
        self.manual_entry.pack(side=tk.LEFT, padx=5)

        # Amount entry
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(frame, text="Enter Amount (optional):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        amount_frame = ttk.Frame(frame)
        amount_frame.pack(anchor=tk.W, pady=5)

        self.amount_entry = ttk.Entry(
            amount_frame, width=20, font=("Arial", 10))
        self.amount_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(amount_frame, text="Save",
                   command=self.confirm_manual).pack(side=tk.LEFT, padx=2)

        # Check No entry
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(frame, text="Check No (optional):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        check_no_frame = ttk.Frame(frame)
        check_no_frame.pack(anchor=tk.W, pady=5)

        self.check_no_entry = ttk.Entry(
            check_no_frame, width=20, font=("Arial", 10))
        self.check_no_entry.pack(side=tk.LEFT, padx=5)

        # ReceiverID entry
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(frame, text="ReceiverID (optional):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        receiver_id_frame = ttk.Frame(frame)
        receiver_id_frame.pack(anchor=tk.W, pady=5)

        self.receiver_id_entry = ttk.Entry(
            receiver_id_frame, width=20, font=("Arial", 10))
        self.receiver_id_entry.pack(side=tk.LEFT, padx=5)

        # Action buttons
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        button_frame = ttk.Frame(frame)
        button_frame.pack(anchor=tk.CENTER, pady=10)

        ttk.Button(button_frame, text="Skip File (S)",
                   command=self.skip_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Mark as No PO (N)",
                   command=self.confirm_no_po).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Skip Remaining (Shift+S)",
                   command=self.skip_remaining_batch).pack(side=tk.LEFT, padx=5)

        # Keyboard shortcuts help
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        help_text = "Keyboard: S = Skip, N = No PO, Shift+S = Skip Remaining, Enter = Confirm Manual"
        ttk.Label(frame, text=help_text, font=("Arial", 8),
                  foreground="gray").pack(anchor=tk.W, pady=5)

        # Set focus to manual entry field
        self.manual_entry.focus()

    def _get_amount(self) -> Optional[str]:
        """Get and validate amount from entry field."""
        if not self.amount_entry:
            return None
        amount = self.amount_entry.get().strip()
        if not amount:
            return None
        # Clean up amount - remove currency symbols and spaces
        amount = amount.replace("$", "").replace(",", "").strip()
        # Validate it's a number
        try:
            float(amount)
            return amount
        except ValueError:
            messagebox.showwarning(
                "Invalid Amount", "Amount must be a valid number")
            return None

    def _get_check_no(self) -> Optional[str]:
        """Get check number from entry field."""
        if not self.check_no_entry:
            return None
        check_no = self.check_no_entry.get().strip()
        return check_no if check_no else None

    def _get_receiver_id(self) -> Optional[str]:
        """Get receiver ID from entry field."""
        if not self.receiver_id_entry:
            return None
        receiver_id = self.receiver_id_entry.get().strip()
        return receiver_id if receiver_id else None

    def _copy_po_to_manual(self, po: str):
        """Copy extracted PO to manual entry field."""
        self.manual_entry.delete(0, tk.END)
        self.manual_entry.insert(0, po)
        self.manual_entry.focus()

    def confirm_po(self, po: str):
        """Confirm selected PO."""
        self.confirmed_po = po
        self.amount = self._get_amount()
        self.check_no = self._get_check_no()
        self.receiver_id = self._get_receiver_id()
        self.root.destroy()

    def confirm_manual(self):
        """Confirm manually entered PO."""
        po = self.manual_entry.get().strip().upper()
        if not po:
            messagebox.showwarning("Empty Entry", "Please enter a PO number")
            return
        if not re.match(r"^([0-9]{5}|0{2}[0-9]{5})(-\d{2})?$", po):
            messagebox.showerror(
                "Invalid Format", "PO must be 5 digits (e.g., 40085) or 7 digits with leading 00 (e.g., 0040085), optionally with -dd suffix")
            return
        # Strip leading zeros
        if "-" in po:
            main_part, suffix = po.split("-")
            po = f"{int(main_part)}-{suffix}"
        else:
            po = str(int(po))
        self.confirmed_po = po
        self.amount = self._get_amount()
        self.check_no = self._get_check_no()
        self.receiver_id = self._get_receiver_id()
        self.root.destroy()

    def skip_file(self):
        """Skip this file."""
        self.skip = True
        self.root.destroy()

    def skip_remaining_batch(self):
        """Skip all remaining files in batch."""
        self.skip = True
        self.skip_remaining = True
        self.root.destroy()

    def confirm_no_po(self):
        """Mark as no PO found."""
        self.confirmed_po = None
        self.amount = self._get_amount()
        self.check_no = self._get_check_no()
        self.receiver_id = self._get_receiver_id()
        self.root.destroy()

    def show(self) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], bool, bool]:
        """Show UI and return (confirmed_po, amount, check_no, receiver_id, skip, skip_remaining)."""
        self.root.mainloop()
        return self.confirmed_po, self.amount, self.check_no, self.receiver_id, self.skip, self.skip_remaining


def match_supplier_from_filename(filename: str) -> Optional[str]:
    """Match supplier code from filename pattern YYYY-MM_SUPPLIERCODE_..."""
    match = re.search(r'^\d{4}-\d{2}_([A-Z0-9]+)_', filename)
    return match.group(1) if match else None


def create_manual_entry_ui(pdf_path: str, filename: str, text: str, po_candidates: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Display PDF with input fields for manual PO and amount entry."""
    win = tk.Tk()
    win.title(f"Manual Entry: {filename}")
    win.geometry("1400x800")

    # File info at top
    info_frame = ttk.Frame(win)
    info_frame.pack(fill=tk.X, padx=10, pady=10)
    ttk.Label(info_frame, text=f"File: {filename}", font=(
        "Arial", 10, "bold")).pack(anchor=tk.W)

    # Extracted candidates
    cand_text = ", ".join(po_candidates) if po_candidates else "None found"
    ttk.Label(info_frame, text=f"PO Candidates: {cand_text}", font=(
        "Arial", 9)).pack(anchor=tk.W)

    # Main container with left/right layout
    main_frame = ttk.Frame(win)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # LEFT SIDE: Entry fields (vertical)
    entry_frame = ttk.LabelFrame(main_frame, text="Manual Entry Fields")
    entry_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

    # PO Number
    ttk.Label(entry_frame, text="PO Number:", font=("Arial", 10)).pack(
        anchor=tk.W, padx=5, pady=(10, 2))
    po_var = tk.StringVar(value=po_candidates[0] if po_candidates else "")
    po_entry = ttk.Entry(entry_frame, textvariable=po_var, width=20)
    po_entry.pack(anchor=tk.W, padx=5, pady=(0, 3))

    # PO candidate buttons
    if po_candidates:
        ttk.Label(entry_frame, text="Candidates:", font=("Arial", 9)).pack(
            anchor=tk.W, padx=5, pady=(3, 2))
        candidates_frame = ttk.Frame(entry_frame)
        candidates_frame.pack(anchor=tk.W, padx=5, pady=(0, 8), fill=tk.X)

        def make_select_po(po):
            def select_po():
                po_var.set(po)
            return select_po

        for po in po_candidates:
            ttk.Button(candidates_frame, text=po, width=10,
                       command=make_select_po(po)).pack(side=tk.TOP, pady=2, fill=tk.X)
    else:
        # Add spacing if no candidates
        ttk.Label(entry_frame, text="").pack(pady=(0, 8))

    # Amount
    ttk.Label(entry_frame, text="Amount:", font=("Arial", 10)).pack(
        anchor=tk.W, padx=5, pady=(10, 2))
    amount_var = tk.StringVar()
    amount_entry = ttk.Entry(entry_frame, textvariable=amount_var, width=20)
    amount_entry.pack(anchor=tk.W, padx=5, pady=(0, 8))

    # Check No
    ttk.Label(entry_frame, text="Check No:", font=("Arial", 10)).pack(
        anchor=tk.W, padx=5, pady=(10, 2))
    check_var = tk.StringVar()
    check_entry = ttk.Entry(entry_frame, textvariable=check_var, width=20)
    check_entry.pack(anchor=tk.W, padx=5, pady=(0, 8))

    # Receiver ID
    ttk.Label(entry_frame, text="Receiver ID:", font=("Arial", 10)).pack(
        anchor=tk.W, padx=5, pady=(10, 2))
    receiver_var = tk.StringVar()
    receiver_entry = ttk.Entry(
        entry_frame, textvariable=receiver_var, width=20)
    receiver_entry.pack(anchor=tk.W, padx=5, pady=(0, 20))

    # Buttons on left side
    button_frame = ttk.Frame(entry_frame)
    button_frame.pack(anchor=tk.W, padx=5, pady=10, fill=tk.X)

    result = {"po": None, "amount": None,
              "check": None, "receiver": None, "save": False}

    def save_and_close():
        result["po"] = po_var.get().strip() or None
        result["amount"] = amount_var.get().strip() or None
        result["check"] = check_var.get().strip() or None
        result["receiver"] = receiver_var.get().strip() or None
        result["save"] = True
        win.destroy()

    def skip():
        result["save"] = False
        win.destroy()

    ttk.Button(button_frame, text="Save & Continue",
               command=save_and_close, width=18).pack(pady=5)
    ttk.Button(button_frame, text="Skip File",
               command=skip, width=18).pack(pady=5)

    # RIGHT SIDE: PDF preview (larger)
    pdf_frame = ttk.LabelFrame(main_frame, text="PDF Preview (First Page)")
    pdf_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    try:
        pdf_doc = fitz.open(pdf_path)
        page = pdf_doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(
            0.75, 0.75))  # 75% scale for larger display
        img_data = pix.tobytes("ppm")
        img = Image.open(io.BytesIO(img_data))

        photo = ImageTk.PhotoImage(img)

        pdf_label = ttk.Label(pdf_frame, image=photo)
        pdf_label.image = photo  # Keep a reference!
        pdf_label.pack(fill=tk.BOTH, expand=True)
        pdf_doc.close()
    except Exception as e:
        ttk.Label(pdf_frame, text=f"Could not load PDF: {e}").pack()

    win.mainloop()
    return result["po"], result["amount"], result["check"], result["receiver"]


def process_file_with_supplier(pdf_path: str, filename: str) -> Dict:
    """
    Process a single file: identify supplier, extract PO/amount using profile,
    display manual entry UI if needed, save to database.
    """
    result = {
        "filename": filename,
        "path": pdf_path,
        "supplier": None,
        "po_number": None,
        "amount": None,
        "check_no": None,
        "receiver_id": None,
        "human_field": "N",
        "status": "pending",
        "notes": ""
    }

    try:
        # Step 1: Extract text
        text = extract_text(pdf_path)
        result["notes"] += "Text extracted. "

        # Step 2: Match supplier from filename
        supplier_code = match_supplier_from_filename(filename)
        if not supplier_code:
            result["notes"] += "Could not extract supplier from filename. "
            result["status"] = "error"
            return result

        result["supplier"] = supplier_code
        supplier_profile = get_supplier_profile(supplier_code)
        result["notes"] += f"Supplier matched: {supplier_code}. "

        # Step 3: Extract PO using supplier profile
        po_candidates = extract_po_with_supplier_profile(text, supplier_code)
        if po_candidates:
            result["po_number"] = po_candidates[0]
            result["notes"] += f"PO extracted: {result['po_number']}. "
        else:
            result["notes"] += "No PO found. "

        # Step 4: Extract amount
        amount = extract_amount_from_text(text, supplier_code)
        if amount:
            try:
                result["amount"] = float(amount)
                result["notes"] += f"Amount extracted: {amount}. "
            except ValueError:
                result["notes"] += f"Amount parse error: {amount}. "

        # Step 5: Check if data is complete
        if result["po_number"] and result["amount"]:
            result["status"] = "complete"
            result["human_field"] = "N"
            result["notes"] += "Complete extraction."
        else:
            result["status"] = "incomplete"
            result["human_field"] = "Y"  # Needs human review/entry
            result["notes"] += "Incomplete - opening manual entry UI. "

            # Show manual entry UI
            po, amount, check, receiver = create_manual_entry_ui(
                pdf_path, filename, text, po_candidates or []
            )
            if po is not None or amount is not None:
                if po:
                    result["po_number"] = po
                if amount:
                    try:
                        result["amount"] = float(amount)
                    except (ValueError, TypeError):
                        pass
                if check:
                    result["check_no"] = check
                if receiver:
                    result["receiver_id"] = receiver
                result["notes"] += "Manual entry completed. "
                result["status"] = "complete_manual"
            else:
                result["notes"] += "Manual entry skipped by user. "

        # Step 6: Save to database
        save_extraction_result(
            filename=filename,
            file_path=pdf_path,
            supplier_code=supplier_code,
            po_number=result["po_number"],
            amount=result["amount"],
            check_no=result["check_no"],
            receiver_id=result["receiver_id"],
            human_field=result["human_field"],
            status=result["status"]
        )
        update_extraction_status(filename, result["status"], result["notes"])
        result["notes"] += "Saved to database. "

    except Exception as e:
        import traceback
        result["status"] = "error"
        result["notes"] += f"Error: {str(e)}. {traceback.format_exc()}"
        update_extraction_status(filename, "error", result["notes"])

    return result


def process_batch_improved(batch_size: int = 10) -> tuple:
    """
    Process unprocessed PDFs using supplier-based workflow.

    Returns:
        tuple: (processed_count, complete_count, incomplete_count, error_count)
    """
    configure_tesseract()

    # Get all PDF files
    pdf_pattern = os.path.join(SCAN_DIRECTORY, "*.pdf")
    pdf_files = sorted(glob.glob(pdf_pattern))

    if not pdf_files:
        print(f"No PDF files found in {SCAN_DIRECTORY}")
        return 0, 0, 0, 0

    # Find unprocessed files
    unprocessed = []
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        result = get_extraction_result(filename)
        if not result or result["status"] == "pending":
            unprocessed.append(pdf_path)

    if not unprocessed:
        print("All files have been processed!")
        return 0, 0, 0, 0

    # Process batch
    batch = unprocessed[:batch_size]
    processed_count = 0
    complete_count = 0
    incomplete_count = 0
    error_count = 0

    print(
        f"\nProcessing batch: {len(batch)} files (of {len(unprocessed)} unprocessed)")
    print("=" * 70)

    for i, pdf_path in enumerate(batch, 1):
        filename = os.path.basename(pdf_path)
        print(f"\n[{i}/{len(batch)}] {filename}")

        result = process_file_with_supplier(pdf_path, filename)
        processed_count += 1

        if result["status"] in ["complete", "complete_manual"]:
            print(
                f"  ✓ Complete: PO={result['po_number']}, Amount={result['amount']}")
            complete_count += 1
        elif result["status"] == "incomplete":
            print(
                f"  ⚠ Incomplete: PO={result['po_number']}, Amount={result['amount']}")
            incomplete_count += 1
        elif result["status"] == "error":
            print(f"  ✗ Error: {result['notes']}")
            error_count += 1

    print("\n" + "=" * 70)
    print(
        f"Batch complete: {complete_count} complete, {incomplete_count} incomplete, {error_count} errors")
    print(
        f"Total processed: {len(unprocessed)} / {len(pdf_files)} files remaining")

    return processed_count, complete_count, incomplete_count, error_count


def process_batch(batch_size: int = 10, start_from: int = 0, with_confirmation: bool = True) -> tuple:
    """
    Process PDFs in batches.

    Args:
        batch_size: Number of files to process in this batch
        start_from: Starting index (for resuming)
        with_confirmation: Show visual confirmation UI for extracted POs

    Returns:
        tuple: (processed_count, success_count, failed_count)
    """
    # Get all PDF files
    pdf_pattern = os.path.join(SCAN_DIRECTORY, "*.pdf")
    pdf_files = sorted(glob.glob(pdf_pattern))

    if not pdf_files:
        print(f"No PDF files found in {SCAN_DIRECTORY}")
        return 0, 0, 0

    # Load progress
    progress = load_progress()
    results = load_results()
    completed_files = set(progress.get("completed", []))

    # Filter out already processed files
    files_to_process = [
        f for f in pdf_files if os.path.basename(f) not in completed_files]

    if not files_to_process:
        print("All files have been processed!")
        return 0, 0, 0

    # Get batch
    batch = files_to_process[start_from: start_from + batch_size]

    processed_count = 0
    success_count = 0
    failed_count = 0

    print(
        f"\nProcessing batch: {len(batch)} files (of {len(files_to_process)} remaining)")
    print("=" * 60)

    for i, pdf_path in enumerate(batch, 1):
        filename = os.path.basename(pdf_path)
        print(f"\n[{i}/{len(batch)}] Processing: {filename}")

        try:
            # Extract text from PDF
            try:
                text = extract_text(pdf_path)
            except FileNotFoundError:
                print(f"  ✗ File not found: {pdf_path}")
                raise
            except OSError as ose:
                print(f"  ✗ File access error: {ose}")
                raise

            # Extract PO numbers
            po_candidates = extract_po_number(text)

            confirmed_po = None
            skipped = False
            skip_remaining = False

            # Visual confirmation if enabled
            amount = None
            check_no = None
            receiver_id = None
            if with_confirmation:
                print("  Opening confirmation dialog...")
                ui = POConfirmationUI(pdf_path, po_candidates, filename)
                confirmed_po, amount, check_no, receiver_id, skipped, skip_remaining = ui.show()

                if skipped:
                    print(f"  ⊘ File skipped by user")
                    progress["completed"].append(filename)
                    processed_count += 1

                    if skip_remaining:
                        print(f"\n  ⊘⊘ Skipping remaining files in batch")
                        break
                    continue
            else:
                # Auto-confirm first match
                confirmed_po = po_candidates[0] if po_candidates else None

            # Store result
            results[filename] = {
                "path": pdf_path,
                "po_number": confirmed_po,
                "amount": amount,
                "check_no": check_no,
                "receiver_id": receiver_id,
                "candidates": po_candidates,
                "human_review": "Y" if confirmed_po else "N",
                "status": "confirmed" if confirmed_po else "no_po_found"
            }

            # Update progress
            progress["completed"].append(filename)

            if confirmed_po:
                print(f"  ✓ PO confirmed: {confirmed_po}")
                success_count += 1
            else:
                print(f"  ✗ No PO recorded for document")

            processed_count += 1

        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"  ✗ Error processing file: {error_msg}")
            print(f"     File: {pdf_path}")
            traceback.print_exc()
            progress["failed"].append(
                {"filename": filename, "error": error_msg})
            results[filename] = {
                "path": pdf_path,
                "po_number": None,
                "amount": None,
                "check_no": None,
                "receiver_id": None,
                "human_review": "N",
                "status": "error",
                "error": error_msg
            }
            failed_count += 1
            processed_count += 1

    # Save progress and results
    save_progress(progress)
    save_results(results)

    print("\n" + "=" * 60)
    print(f"Batch complete: {success_count}/{processed_count} successful")
    print(
        f"Total progress: {len(progress['completed'])} completed, {len(progress['failed'])} failed")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"Progress saved to: {PROGRESS_FILE}")

    return processed_count, success_count, failed_count


def get_status() -> Dict:
    """Get current processing status."""
    progress = load_progress()
    results = load_results()

    pdf_pattern = os.path.join(SCAN_DIRECTORY, "*.pdf")
    total_files = len(glob.glob(pdf_pattern))

    return {
        "total_files": total_files,
        "completed": len(progress["completed"]),
        "failed": len(progress["failed"]),
        "remaining": total_files - len(progress["completed"]) - len(progress["failed"]),
        "po_found_count": sum(1 for r in results.values() if r.get("po_number"))
    }


def test_single_file():
    """Test PO/Amount extraction on a single file."""
    root = tk.Tk()
    root.title("Test Single File")
    root.geometry("900x700")

    ttk.Label(root, text="Test PO/Amount Detection",
              font=("Arial", 14, "bold")).pack(pady=10)

    selected_file = None
    extracted_text = None

    def select_file():
        nonlocal selected_file
        selected_file = filedialog.askopenfilename(
            title="Select PDF to Test",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if selected_file:
            file_label.config(
                text=f"Selected: {os.path.basename(selected_file)}")
            test_button.config(state=tk.NORMAL)
            test_location_button.config(state=tk.NORMAL)
            show_ocr_button.config(state=tk.NORMAL)

    def run_test():
        nonlocal extracted_text
        if not selected_file:
            messagebox.showerror("Error", "Please select a file first")
            return

        # Extract supplier code from filename
        filename = os.path.basename(selected_file)
        supplier = extract_supplier_code(filename)

        result_text.config(state=tk.NORMAL)
        result_text.delete(1.0, tk.END)

        result_text.insert(tk.END, f"File: {filename}\n")
        result_text.insert(
            tk.END, f"Supplier: {supplier if supplier else 'Unknown'}\n")
        result_text.insert(tk.END, "=" * 60 + "\n\n")

        try:
            # Extract text from PDF
            extracted_text = extract_text(selected_file)
            result_text.insert(
                tk.END, f"Text extracted ({len(extracted_text)} chars)\n\n")

            # Try to extract PO using supplier profile
            po_results = extract_po_with_supplier_profile(
                extracted_text, supplier)
            result_text.insert(tk.END, f"PO Detection Results:\n")
            result_text.insert(
                tk.END, f"  Extracted POs: {po_results if po_results else 'None found'}\n\n")

            # Try to extract amount using supplier profile
            amount = extract_amount_from_text(extracted_text, supplier)
            result_text.insert(tk.END, f"Amount Detection Results:\n")
            result_text.insert(
                tk.END, f"  Extracted Amount: {amount if amount else 'None found'}\n\n")

            # Show supplier profile details if available
            po_profiles = get_po_profiles()
            if supplier and supplier in po_profiles:
                profile = po_profiles[supplier]
                result_text.insert(tk.END, f"Supplier Profile Details:\n")
                result_text.insert(
                    tk.END, f"  PO Patterns: {profile.get('po_patterns', [])}\n")
                result_text.insert(
                    tk.END, f"  Amount Patterns: {profile.get('amount_patterns', [])}\n")
            else:
                result_text.insert(
                    tk.END, f"No supplier profile found for {supplier}\n")
                result_text.insert(tk.END, f"Using generic PO patterns\n")

        except Exception as e:
            result_text.insert(tk.END, f"Error: {str(e)}\n")
            import traceback
            result_text.insert(tk.END, traceback.format_exc())

        result_text.config(state=tk.DISABLED)

    def test_location_based():
        """Test using location-based extraction (bounding boxes)."""
        if not selected_file:
            messagebox.showerror("Error", "Please select a file first")
            return

        filename = os.path.basename(selected_file)
        supplier = extract_supplier_code(filename)

        result_text.config(state=tk.NORMAL)
        result_text.delete(1.0, tk.END)

        result_text.insert(tk.END, f"File: {filename}\n")
        result_text.insert(
            tk.END, f"Supplier: {supplier if supplier else 'Unknown'}\n")
        result_text.insert(tk.END, "=" * 60 + "\n")
        result_text.insert(
            tk.END, "LOCATION-BASED EXTRACTION (Bounding Boxes)\n")
        result_text.insert(tk.END, "=" * 60 + "\n\n")

        try:
            from location_extraction import (
                extract_po_from_location,
                extract_amount_from_location,
                has_po_location,
                has_amount_location,
            )

            if not has_po_location(supplier):
                result_text.insert(
                    tk.END, f"❌ No PO location calibrated for {supplier}\n")
                result_text.insert(
                    tk.END, f"   Use Option 7 to calibrate locations first\n")
            else:
                po = extract_po_from_location(selected_file, supplier)
                result_text.insert(
                    tk.END, f"PO (from location): {po if po else 'None found'}\n")

            if not has_amount_location(supplier):
                result_text.insert(
                    tk.END, f"❌ No Amount location calibrated for {supplier}\n")
            else:
                amount = extract_amount_from_location(selected_file, supplier)
                result_text.insert(
                    tk.END, f"Amount (from location): {amount if amount else 'None found'}\n")

        except Exception as e:
            result_text.insert(tk.END, f"Error: {str(e)}\n")
            import traceback
            result_text.insert(tk.END, traceback.format_exc())

        result_text.config(state=tk.DISABLED)

    def show_ocr_text():
        """Show the extracted OCR text in a new window."""
        if extracted_text is None:
            messagebox.showinfo(
                "Info", "Please run test first to extract text")
            return

        ocr_window = tk.Toplevel(root)
        ocr_window.title("Extracted OCR Text")
        ocr_window.geometry("900x700")

        ttk.Label(ocr_window, text="Full Extracted Text (for pattern development)",
                  font=("Arial", 12, "bold")).pack(pady=10)

        # Text widget with scrollbar
        text_frame = ttk.Frame(ocr_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ocr_text = tk.Text(text_frame, height=30, width=100, wrap=tk.WORD)
        ocr_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame, command=ocr_text.yview)
        ocr_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Insert text with line numbers
        for i, line in enumerate(extracted_text.split('\n'), 1):
            ocr_text.insert(tk.END, f"{i:4d}: {line}\n")

        ocr_text.config(state=tk.DISABLED)

        # Copy button
        def copy_all():
            ocr_window.clipboard_clear()
            ocr_window.clipboard_append(extracted_text)
            messagebox.showinfo("Copied", "All text copied to clipboard")

        button_frame = ttk.Frame(ocr_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(button_frame, text="Copy All Text",
                   command=copy_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close",
                   command=ocr_window.destroy).pack(side=tk.LEFT, padx=5)

    # File selection frame
    file_frame = ttk.LabelFrame(root, text="Select File", padding=10)
    file_frame.pack(fill=tk.X, padx=10, pady=10)

    file_label = ttk.Label(
        file_frame, text="No file selected", foreground="gray")
    file_label.pack(side=tk.LEFT, padx=5)

    ttk.Button(file_frame, text="Browse...",
               command=select_file).pack(side=tk.LEFT, padx=5)

    # Results frame
    results_frame = ttk.LabelFrame(root, text="Detection Results", padding=10)
    results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    result_text = tk.Text(results_frame, height=20,
                          width=100, state=tk.DISABLED)
    result_text.pack(fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(result_text, command=result_text.yview)
    result_text.config(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Button frame
    button_frame = ttk.Frame(root)
    button_frame.pack(fill=tk.X, padx=10, pady=10)

    test_button = ttk.Button(
        button_frame, text="Test Extraction", command=run_test, state=tk.DISABLED)
    test_button.pack(side=tk.LEFT, padx=5)

    test_location_button = ttk.Button(
        button_frame, text="Test Location-Based", command=test_location_based, state=tk.DISABLED)
    test_location_button.pack(side=tk.LEFT, padx=5)

    show_ocr_button = ttk.Button(
        button_frame, text="Show OCR Text", command=show_ocr_text, state=tk.DISABLED)
    show_ocr_button.pack(side=tk.LEFT, padx=5)

    ttk.Button(button_frame, text="Close",
               command=root.destroy).pack(side=tk.LEFT, padx=5)

    root.mainloop()


def main(use_ui: bool = True):
    """
    Main entry point with menu system.

    Args:
        use_ui: Enable visual confirmation UI (default True)
    """
    # Configure OCR if available
    configure_tesseract()

    # Show main menu
    root = tk.Tk()
    root.title("Invoice Processing Suite")
    root.geometry("500x800")

    ttk.Label(root, text="Invoice Processing Suite",
              font=("Arial", 16, "bold")).pack(pady=20)

    ttk.Label(root, text="Select a workflow:",
              font=("Arial", 12)).pack(pady=10)

    button_frame = ttk.Frame(root)
    button_frame.pack(pady=20)

    def launch_classifier():
        """Launch invoice classifier to rename files by supplier."""
        root.destroy()
        from classifier import (
            load_profiles,
            save_profiles,
            train_supplier_profiles,
            classify_invoice,
        )
        from file_ops import rename_file
        from pdf_utils import get_ocr_enabled, set_ocr_enabled

        app_root = tk.Tk()
        app_root.title("Invoice Classifier")

        profiles = load_profiles()
        vectorizer = None
        sample_vectors = []
        sample_labels = []

        # Buttons
        tk.Button(app_root, text="Add Sample Invoices",
                  command=add_samples).pack()
        tk.Button(app_root, text="Classify New Invoices",
                  command=classify_invoices).pack()

        # OCR Toggle
        ocr_var = tk.BooleanVar(value=get_ocr_enabled())
        ocr_check = tk.Checkbutton(
            app_root, text="Enable OCR", variable=ocr_var, command=toggle_ocr
        )
        ocr_check.pack()

        # Log
        log = tk.Text(app_root, height=20, width=80)
        log.pack()
        log.insert(
            tk.END, f"OCR status: {'Enabled' if get_ocr_enabled() else 'Disabled'}\n")

        def toggle_ocr():
            set_ocr_enabled(ocr_var.get())
            log.insert(
                tk.END, f"OCR manually {'enabled' if ocr_var.get() else 'disabled'}\n")

        def add_samples():
            files = filedialog.askopenfilenames(title="Select Sample PDFs")
            supplier = simpledialog.askstring(
                "Supplier", "Enter supplier name:")
            if supplier and files:
                for f in files:
                    text = extract_text(f)
                    profiles.setdefault(supplier, []).append(text)
                save_profiles(profiles)
                log.insert(
                    tk.END, f"Added {len(files)} samples for {supplier}\n")

        def classify_invoices():
            if not profiles:
                messagebox.showerror(
                    "Error", "No supplier profiles available. Add samples first."
                )
                return
            nonlocal vectorizer, sample_vectors, sample_labels
            vectorizer, sample_vectors, sample_labels = (
                train_supplier_profiles(profiles)
            )
            files = filedialog.askopenfilenames(
                title="Select Invoices to Classify")
            for f in files:
                text = extract_text(f)
                supplier, invoice_date, confidence = classify_invoice(
                    text,
                    vectorizer,
                    sample_vectors,
                    sample_labels,
                    threshold=0.3,
                )

                filename = os.path.basename(f)
                if supplier == "UNKNOWN":
                    log.insert(
                        tk.END,
                        f"Skipped {filename} - confidence too low ({confidence:.3f})\n",
                    )
                    continue

                suffix = f"{invoice_date}_{supplier}" if invoice_date else supplier
                new_path = rename_file(f, suffix)
                log.insert(
                    tk.END,
                    f"Renamed to {os.path.basename(new_path)} (confidence: {confidence:.3f})\n",
                )

        app_root.mainloop()

    def launch_profile_manager():
        """Launch PO/Amount profile manager."""
        root.destroy()
        open_supplier_profile_manager()

    def launch_po_extraction():
        """Launch PO/Amount extraction with profiles."""
        root.destroy()
        run_processing_loop(use_ui)

    def launch_improved_extraction():
        """Launch improved PO/Amount extraction with supplier matching and manual entry."""
        root.destroy()
        run_improved_processing_loop()

    def launch_test():
        """Launch single file test."""
        root.destroy()
        test_single_file()
        main(use_ui)  # Return to main menu after test

    def launch_batch_learn():
        """Launch batch learn UI for multi-selecting files to add samples and validate patterns."""
        root.destroy()
        open_batch_learn()
        main(use_ui)
    ttk.Button(button_frame, text="1. Classify Invoices\n(Rename by Supplier)",
               command=launch_classifier, width=40).pack(pady=10)

    ttk.Button(button_frame, text="2. Build PO/Amount Profiles\n(Train Detection Patterns)",
               command=launch_profile_manager, width=40).pack(pady=10)

    ttk.Button(button_frame, text="3. Test Single File\n(Validate Patterns)",
               command=launch_test, width=40).pack(pady=10)

    ttk.Button(button_frame, text="4. Batch Learn & Validate\n(Multi-select samples)",
               command=launch_batch_learn, width=40).pack(pady=10)

    ttk.Button(button_frame, text="5. Extract PO/Amount (Legacy)\n(Apply Detection Profiles)",
               command=launch_po_extraction, width=40).pack(pady=10)

    ttk.Button(button_frame, text="6. Extract with Supplier Matching (NEW)\n(Improved workflow)",
               command=launch_improved_extraction, width=40).pack(pady=10)

    def launch_location_extraction():
        """Launch location-based PO/Amount extraction."""
        root.destroy()
        from location_extraction.ui import calibrate_supplier_locations

        calibrate_supplier_locations()
        main(use_ui)

    ttk.Button(button_frame, text="7. Configure Location Mapping (NEW)\n(Calibrate supplier invoice layout)",
               command=launch_location_extraction, width=40).pack(pady=10)

    def exit_app():
        """Exit the application properly."""
        import sys
        root.quit()
        root.destroy()
        sys.exit(0)

    ttk.Button(button_frame, text="Exit",
               command=exit_app, width=40).pack(pady=10)

    root.mainloop()


def run_processing_loop(use_ui: bool = True):
    """Main processing loop."""
    while True:
        # Show status
        status = get_status()
        print("\nPO Number Extraction Status")
        print("=" * 60)
        print(f"Total PDFs in directory: {status['total_files']}")
        print(f"Already processed: {status['completed']}")
        print(f"Failed: {status['failed']}")
        print(f"Remaining: {status['remaining']}")
        print(f"POs found so far: {status['po_found_count']}")
        print("=" * 60)

        # Process next batch
        if status['remaining'] > 0:
            # Default batch size of 10
            batch_size = min(10, status['remaining'])
            print(f"\nProcessing batch of {batch_size} files...")
            process_batch(batch_size=batch_size, with_confirmation=use_ui)

            # Ask if user wants to continue
            root = tk.Tk()
            root.withdraw()  # Hide the main window

            continue_processing = messagebox.askyesno(
                "Continue Processing",
                "Batch complete! Process another batch?"
            )
            root.destroy()

            if not continue_processing:
                print("\nProcessing halted by user.")
                break
        else:
            print("\n✓ All files have been processed!")
            break


def run_improved_processing_loop():
    """Improved processing loop with supplier matching and manual entry."""
    while True:
        # Get PDF files and count unprocessed
        pdf_pattern = os.path.join(SCAN_DIRECTORY, "*.pdf")
        pdf_files = sorted(glob.glob(pdf_pattern))

        if not pdf_files:
            print(f"No PDF files found in {SCAN_DIRECTORY}")
            break

        # Count unprocessed
        unprocessed_count = 0
        complete_count = 0
        incomplete_count = 0
        error_count = 0

        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            result = get_extraction_result(filename)
            if not result or result["status"] == "pending":
                unprocessed_count += 1
            elif result["status"] in ["complete", "complete_manual"]:
                complete_count += 1
            elif result["status"] == "incomplete":
                incomplete_count += 1
            else:
                error_count += 1

        # Show status
        print("\nImproved PO Extraction Status")
        print("=" * 70)
        print(f"Total PDFs in directory: {len(pdf_files)}")
        print(
            f"Complete: {complete_count} | Incomplete: {incomplete_count} | Error: {error_count}")
        print(f"Unprocessed: {unprocessed_count}")
        print("=" * 70)

        if unprocessed_count > 0:
            batch_size = min(10, unprocessed_count)
            print(f"\nProcessing batch of {batch_size} files...")
            processed, complete, incomplete, errors = process_batch_improved(
                batch_size=batch_size)

            # Ask if user wants to continue
            root = tk.Tk()
            root.withdraw()
            continue_processing = messagebox.askyesno(
                "Continue Processing",
                f"Batch complete!\nComplete: {complete} | Incomplete: {incomplete} | Errors: {errors}\n\nProcess another batch?"
            )
            root.destroy()

            if not continue_processing:
                print("\nProcessing halted by user.")
                break
        else:
            print("\n✓ All files have been processed!")
            break


if __name__ == "__main__":
    import sys
    # Use --no-ui flag to disable visual confirmation
    use_ui = "--no-ui" not in sys.argv
    main(use_ui=use_ui)

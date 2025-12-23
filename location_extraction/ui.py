"""
UI for mapping/calibrating PO and Amount locations on sample invoices.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import io
from location_extraction.config import add_supplier_location, get_supplier_location


def calibrate_supplier_locations():
    """Interactive UI to define PO and Amount locations for a supplier."""

    # Get supplier code
    supplier_code = simpledialog.askstring(
        "Supplier Code",
        "Enter supplier code to calibrate:"
    )
    if not supplier_code:
        return

    # Get sample PDF
    pdf_path = filedialog.askopenfilename(
        title=f"Select sample invoice for {supplier_code}",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
    )
    if not pdf_path:
        return

    # Create calibration window
    win = tk.Tk()
    win.title(f"Calibrate {supplier_code} - PO & Amount Locations")
    win.geometry("1200x800")

    # Load PDF first page
    try:
        pdf_doc = fitz.open(pdf_path)
        page = pdf_doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))  # 1.5x zoom
        img_data = pix.tobytes("ppm")
        img = Image.open(io.BytesIO(img_data))
        pdf_doc.close()
    except Exception as e:
        messagebox.showerror("Error", f"Could not load PDF: {e}")
        return

    # State for selections
    state = {
        "po_rect": None,
        "amount_rect": None,
        "start_point": None,
        "current_mode": None,  # "po" or "amount"
    }

    # Create frame with PDF canvas
    canvas_frame = ttk.Frame(win)
    canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH,
                      expand=True, padx=10, pady=10)

    ttk.Label(canvas_frame, text="Click and drag to define regions (scroll with mouse wheel)",
              font=("Arial", 10)).pack()

    # Canvas with scrollbar for PDF display
    canvas_container = ttk.Frame(canvas_frame)
    canvas_container.pack(fill=tk.BOTH, expand=True, pady=10)

    canvas = tk.Canvas(canvas_container, cursor="crosshair", bg="white")
    scrollbar = ttk.Scrollbar(
        canvas_container, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    photo = ImageTk.PhotoImage(img)
    canvas.photo = photo
    canvas_image = canvas.create_image(0, 0, image=photo, anchor=tk.NW)
    canvas.config(scrollregion=canvas.bbox("all"))

    # Mouse wheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    canvas.bind("<MouseWheel>", _on_mousewheel)

    # Right panel for controls
    control_frame = ttk.Frame(win)
    control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

    ttk.Label(control_frame, text="Calibration",
              font=("Arial", 12, "bold")).pack(pady=10)

    # PO section
    ttk.Label(control_frame, text="1. Select PO Location", font=(
        "Arial", 11, "bold")).pack(anchor=tk.W, pady=(10, 5))

    def start_po_selection():
        state["current_mode"] = "po"
        messagebox.showinfo(
            "PO Selection", "Click and drag on the PDF to select PO region")

    ttk.Button(control_frame, text="Define PO Region",
               command=start_po_selection, width=25).pack(pady=5, fill=tk.X)

    po_label = ttk.Label(control_frame, text="PO: Not set", foreground="red")
    po_label.pack(anchor=tk.W, padx=5)

    # Amount section
    ttk.Label(control_frame, text="2. Select Amount Location", font=(
        "Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

    def start_amount_selection():
        state["current_mode"] = "amount"
        messagebox.showinfo(
            "Amount Selection", "Click and drag on the PDF to select Amount region")

    ttk.Button(control_frame, text="Define Amount Region",
               command=start_amount_selection, width=25).pack(pady=5, fill=tk.X)

    amount_label = ttk.Label(
        control_frame, text="Amount: Not set", foreground="red")
    amount_label.pack(anchor=tk.W, padx=5)

    # Preview section
    ttk.Label(control_frame, text="3. Save Locations", font=(
        "Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

    def save_locations():
        if not state["po_rect"] or not state["amount_rect"]:
            messagebox.showerror(
                "Error", "Both PO and Amount regions must be defined")
            return

        po_box = {
            "x0": state["po_rect"]["x0"],
            "y0": state["po_rect"]["y0"],
            "x1": state["po_rect"]["x1"],
            "y1": state["po_rect"]["y1"],
            "page": 0
        }

        amount_box = {
            "x0": state["amount_rect"]["x0"],
            "y0": state["amount_rect"]["y0"],
            "x1": state["amount_rect"]["x1"],
            "y1": state["amount_rect"]["y1"],
            "page": 0
        }

        add_supplier_location(supplier_code, po_box, amount_box)
        messagebox.showinfo("Success", f"Locations saved for {supplier_code}")
        win.destroy()

    ttk.Button(control_frame, text="Save Locations",
               command=save_locations, width=25).pack(pady=5, fill=tk.X)

    ttk.Button(control_frame, text="Cancel", command=win.destroy,
               width=25).pack(pady=5, fill=tk.X)

    # Canvas event handlers for drawing rectangles
    def on_canvas_press(event):
        # Get scroll offset
        scroll_y = canvas.yview()[0] * canvas.bbox("all")[3]
        state["start_point"] = (event.x, event.y + scroll_y)

    def on_canvas_drag(event):
        if not state["start_point"] or not state["current_mode"]:
            return

        # Get scroll offset
        scroll_y = canvas.yview()[0] * canvas.bbox("all")[3]

        # Clear previous rectangle for current mode
        tag = f"{state['current_mode']}_rect"
        canvas.delete(tag)

        x0, y0 = state["start_point"]
        x1 = event.x
        y1 = event.y + scroll_y

        # Draw rectangle (adjust for scroll when displaying)
        display_y0 = y0 - scroll_y
        display_y1 = y1 - scroll_y
        canvas.create_rectangle(
            x0, display_y0, x1, display_y1, outline="red", width=2, tags=tag)

    def on_canvas_release(event):
        if not state["start_point"] or not state["current_mode"]:
            return

        # Get scroll offset
        scroll_y = canvas.yview()[0] * canvas.bbox("all")[3]

        x0, y0 = state["start_point"]
        x1 = event.x
        y1 = event.y + scroll_y

        # Normalize coordinates
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0

        # Store rectangle (scale back to PDF coordinates based on 1.5x zoom)
        rect = {"x0": x0 / 1.5, "y0": y0 / 1.5, "x1": x1 / 1.5, "y1": y1 / 1.5}

        if state["current_mode"] == "po":
            state["po_rect"] = rect
            po_label.config(
                text=f"PO: ({rect['x0']:.0f}, {rect['y0']:.0f}) - ({rect['x1']:.0f}, {rect['y1']:.0f})", foreground="green")
        elif state["current_mode"] == "amount":
            state["amount_rect"] = rect
            amount_label.config(
                text=f"Amount: ({rect['x0']:.0f}, {rect['y0']:.0f}) - ({rect['x1']:.0f}, {rect['y1']:.0f})", foreground="green")

        state["current_mode"] = None
        state["start_point"] = None

    canvas.bind("<Button-1>", on_canvas_press)
    canvas.bind("<B1-Motion>", on_canvas_drag)
    canvas.bind("<ButtonRelease-1>", on_canvas_release)

    # Load existing locations if available
    existing = get_supplier_location(supplier_code)
    if existing:
        if "po" in existing:
            po_box = existing["po"]
            state["po_rect"] = po_box
            po_label.config(
                text=f"PO: ({po_box['x0']:.0f}, {po_box['y0']:.0f}) - ({po_box['x1']:.0f}, {po_box['y1']:.0f})", foreground="green")
        if "amount" in existing:
            amt_box = existing["amount"]
            state["amount_rect"] = amt_box
            amount_label.config(
                text=f"Amount: ({amt_box['x0']:.0f}, {amt_box['y0']:.0f}) - ({amt_box['x1']:.0f}, {amt_box['y1']:.0f})", foreground="green")

    win.mainloop()

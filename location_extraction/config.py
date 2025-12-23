"""
Location configuration for PO/Amount/Invoice extraction by bounding box.

Each supplier can have PO, Amount, and Invoice locations defined as bounding boxes.
Coordinates are in PDF points (1/72 inch).
At least one location must be defined per supplier.

Format: {
    "supplier_code": {
        "po": {
            "x0": float,      # Left edge
            "y0": float,      # Top edge
            "x1": float,      # Right edge
            "y1": float,      # Bottom edge
            "page": int       # Page number (0-indexed)
        },
        "amount": {...},    # Optional
        "invoice": {...}    # Optional
    }
}
"""

import json
import os
from typing import Dict, Optional

CONFIG_FILE = "location_mappings.json"


def load_config() -> Dict:
    """Load location mappings from JSON file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_config(config: Dict):
    """Save location mappings to JSON file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def add_supplier_location(
    supplier_code: str,
    po_box: Optional[Dict] = None,
    amount_box: Optional[Dict] = None,
    invoice_box: Optional[Dict] = None,
):
    """
    Add or update location mappings for a supplier.

    Args:
        supplier_code: Supplier code
        po_box: {x0, y0, x1, y1, page} (optional)
        amount_box: {x0, y0, x1, y1, page} (optional)
        invoice_box: {x0, y0, x1, y1, page} (optional)

    Raises:
        ValueError: If no location boxes are provided
    """
    if not any([po_box, amount_box, invoice_box]):
        raise ValueError(
            "At least one location (PO, Amount, or Invoice) must be defined"
        )

    config = load_config()
    config[supplier_code] = {}

    if po_box:
        config[supplier_code]["po"] = po_box
    if amount_box:
        config[supplier_code]["amount"] = amount_box
    if invoice_box:
        config[supplier_code]["invoice"] = invoice_box

    save_config(config)


def get_supplier_location(supplier_code: str) -> Optional[Dict]:
    """Get location mappings for a supplier."""
    config = load_config()
    return config.get(supplier_code)


def has_po_location(supplier_code: str) -> bool:
    """Check if supplier has PO location defined."""
    location = get_supplier_location(supplier_code)
    return location is not None and "po" in location


def has_amount_location(supplier_code: str) -> bool:
    """Check if supplier has Amount location defined."""
    location = get_supplier_location(supplier_code)
    return location is not None and "amount" in location


def has_invoice_location(supplier_code: str) -> bool:
    """Check if supplier has Invoice location defined."""
    location = get_supplier_location(supplier_code)
    return location is not None and "invoice" in location

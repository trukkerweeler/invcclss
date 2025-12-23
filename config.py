"""Configuration constants for Invoice Classifier application."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get computer name and set path accordingly
COMPUTER_NAME = os.getenv("COMPUTER_NAME")
SCAN_PATH = os.getenv("SCAN_PATH")

# Fallback path if not on Quality-Mgr
DEFAULT_SCAN_PATH = r"C:\Users\TimK\Documents\Python\invcclss\scans"

# Use SCAN_PATH if computer matches, otherwise use default
ACTIVE_SCAN_PATH = (
    SCAN_PATH if os.environ.get("COMPUTERNAME") == COMPUTER_NAME else DEFAULT_SCAN_PATH
)

# UI Configuration
DEFAULT_LOG_HEIGHT = 15
DEFAULT_LOG_WIDTH = 80
APP_TITLE = "Invoice Classifier"

# File paths
PROFILE_PATH = (
    r"C:\Users\TimK\OneDrive\Documents\Work\CI\APScans\supplier_profiles.json"
)

# Tesseract OCR paths
TESSERACT_FALLBACK_PATH = (
    r"C:\Users\TimK\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

# OCR Configuration
OCR_RESOLUTION = 300

# Date extraction patterns (use [^\n] instead of \s to avoid capturing multiple lines)
# Allow various separators between words to handle OCR errors (-, space, period, etc.)
DATE_PATTERNS = [
    # Handles "BILLING DATE", "BILLING-DATE", "BILLING.DATE", etc.
    r"BILLING[\s\-\.]*DATE[:\s]*([^\n]+)",
    # Handles "BILL DATE", "BILL-DATE", "BILL.DATE", etc.
    r"BILL[\s\-\.]*DATE[:\s]*([^\n]+)",
    # Handles "INVOICE DATE", "INVOICE-DATE", "INVOICE.DATE", etc.
    r"INVOICE[\s\-\.]*DATE[:\s]*([^\n]+)",
    # Handles "STATEMENT DATE", "Statement Date:", etc.
    r"STATEMENT[\s\-\.]*DATE[:\s]*([^\n]+)",
    r"ACCOUNT\s+SUMMARY\s+AS\s+OF[:\s]*([^\n]+)",
    # Catches "COMMERCIAL 10/04/2024" format
    r"COMMERCIAL\s+(\d{1,2}/\d{1,2}/\d{4})",
    # Catches "through SEP 30, 2024" format
    r"through[\s\-\.]*([A-Z]{3}\s+\d{1,2},?\s+\d{4})",
    # Catches "Charge if paid by 11/30/2024" format
    r"CHARGE[\s\-\.]*IF[\s\-\.]*PAID[\s\-\.]*BY[:\s]*([^\n]+)",
    # Catches "DUE DATE 12/10/2024" format
    r"DUE[\s\-\.]*DATE[:\s]*([^\n]+)",
]

# Date format parsing
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%b %d, %Y",  # Dec 04, 2024
    "%b %d %Y",  # Dec 04 2024
    "%d %b %Y",  # 04 Dec 2024
    "%d %b, %Y",  # 04 Dec, 2024
    "%B %d, %Y",  # December 04, 2024
    "%B %d %Y",  # December 04 2024
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d.%m.%Y",
]
DATE_OUTPUT_FORMAT = "%Y-%m"

# Invoice Classification & PO Extraction - Workflow Improvements

## Summary of Changes

This document outlines the improvements made to the invoice processing workflow, including supplier matching, automated data extraction, and manual entry UI for incomplete data.

## Issues Fixed

### 1. Regex Syntax Warnings ✓

**Problem:** Invalid escape sequence warnings on lines 204 and 208

```
SyntaxWarning: invalid escape sequence '\d'
```

**Solution:**

- Updated regex pattern building to use raw f-strings (`rf"..."`) to properly handle backslash escape sequences
- Changed from:
  ```python
  f"{re.escape(pattern_label)}\\s+([0-9]{{5}}(?:-\d{{2}})?|0{{2}}[0-9]{{5}}(?:-\d{{2}})?)"
  ```
- To:
  ```python
  rf"{re.escape(pattern_label)}\s+([0-9]{{5}}(?:-\d{{2}})?|0{{2}}[0-9]{{5}}(?:-\d{{2}})?)?"
  ```

## New Features

### 2. Enhanced Database Schema

Added three new tables to `invoice_system.db`:

#### `supplier_profiles` table

Stores supplier information for matching against filename patterns.

```sql
CREATE TABLE supplier_profiles (
    supplier_code TEXT PRIMARY KEY,
    name TEXT,
    description TEXT
);
```

#### `extraction_results` table

Tracks all extracted PO and amount data with complete audit trail.

```sql
CREATE TABLE extraction_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    file_path TEXT,
    supplier_code TEXT,
    po_number TEXT,
    amount REAL,
    check_no TEXT,
    receiver_id TEXT,
    human_field TEXT DEFAULT 'N',
    status TEXT DEFAULT 'pending',
    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `processing_progress` table

Tracks progress and status of each file processed.

```sql
CREATE TABLE processing_progress (
    filename TEXT PRIMARY KEY,
    status TEXT DEFAULT 'pending',
    processed_date TIMESTAMP,
    notes TEXT
);
```

### 3. Improved Supplier Matching Workflow

#### New Function: `match_supplier_from_filename(filename: str) -> Optional[str]`

- Extracts supplier code from filename pattern: `YYYY-MM_SUPPLIERCODE_...`
- Example: `2023-03_AFFI1_SKM_C36825121315590.pdf` → `AFFI1`

#### New Function: `process_file_with_supplier(pdf_path: str, filename: str) -> Dict`

Complete workflow for a single file:

1. **Extract Text** - OCR text from PDF
2. **Match Supplier** - Extract supplier code from filename
3. **Supplier Profile Lookup** - Get PO/amount patterns for supplier
4. **Extract PO** - Use supplier-specific patterns or generic patterns
5. **Extract Amount** - Use supplier-specific patterns or generic patterns
6. **Check Completeness** - If both PO and amount found:
   - Mark as `complete`, `human_field='N'`
   - Save to database
7. **Manual Entry (if incomplete)** - Display PDF with input fields:
   - User can manually enter PO, Amount, Check No, Receiver ID
   - Save manually entered data
8. **Database Tracking** - Record all results with status

### 4. Manual Entry UI

#### New Function: `create_manual_entry_ui(pdf_path, filename, text, po_candidates) -> Tuple`

Displays an interactive form with:

- **File info** - Shows filename and PO candidates found
- **Input fields:**
  - PO Number (pre-filled with first candidate if available)
  - Amount
  - Check No (optional)
  - Receiver ID (optional)
- **PDF Preview** - First page of PDF at 50% scale for reference
- **Buttons:**
  - "Save & Continue" - Save entered data and process next file
  - "Skip File" - Skip this file without saving

Features:

- Pre-fills PO field with highest confidence match
- Shows visual PDF reference while entering data
- Non-blocking manual data entry
- Graceful skip option

### 5. Improved Batch Processing

#### New Function: `process_batch_improved(batch_size: int = 10) -> tuple`

- Processes unprocessed files from database
- Uses supplier matching and profile-based extraction
- Shows detailed progress for each file
- Returns: (processed_count, complete_count, incomplete_count, error_count)

#### New Function: `run_improved_processing_loop()`

- Main loop for improved workflow
- Shows status dashboard:
  - Total PDFs
  - Complete | Incomplete | Error | Unprocessed
- Processes in batches of 10
- Prompts user between batches
- Continues until all files processed

## Workflow Comparison

### Legacy Workflow (Still Available)

1. Extract PO using generic or learned patterns
2. Show confirmation UI
3. Save to JSON results file
4. Track progress in JSON

### New Improved Workflow (Recommended)

1. Match supplier from filename
2. Extract PO using supplier-specific patterns
3. Extract amount using supplier-specific patterns
4. Check if data is complete
5. If incomplete, show PDF with manual entry form
6. Save all results to SQLite database
7. Track progress in database with notes

## New Database Functions (db.py)

### Supplier Profile Management

- `add_supplier_profile(supplier_code, name, description)` - Add/update supplier
- `get_supplier_profile(supplier_code)` - Get supplier details
- `get_all_supplier_profiles()` - List all suppliers

### Results Management

- `save_extraction_result(...)` - Save PO/amount extraction
- `get_extraction_result(filename)` - Get result for file
- `get_unprocessed_files()` - List files pending processing
- `update_extraction_status(filename, status, notes)` - Update progress

## Updated Main Menu

Menu option 6 (NEW): "Extract with Supplier Matching (NEW)"

- Uses improved workflow
- Supplier-based extraction
- Manual entry for incomplete data
- Full database tracking

Menu option 5 (Legacy): "Extract PO/Amount (Legacy)"

- Original workflow
- Still available for compatibility
- Uses JSON storage

## Status Values

| Status            | Description                           |
| ----------------- | ------------------------------------- |
| `pending`         | Not yet processed                     |
| `complete`        | PO and amount automatically extracted |
| `complete_manual` | Manually completed by user in UI      |
| `incomplete`      | Could not extract all required fields |
| `error`           | Error during processing               |

## Human Field Values

| Value | Meaning                         |
| ----- | ------------------------------- |
| `Y`   | Human review/entry was required |
| `N`   | Fully automated extraction      |

## Usage Example

```python
# Process a single file
result = process_file_with_supplier(
    pdf_path="C:\\path\\to\\file.pdf",
    filename="2023-03_AFFI1_SKM_C36825121315590.pdf"
)

# result contains:
# {
#     "filename": "2023-03_AFFI1_SKM_C36825121315590.pdf",
#     "supplier": "AFFI1",
#     "po_number": "40085",
#     "amount": 250.50,
#     "check_no": None,
#     "receiver_id": None,
#     "human_field": "N",  # or "Y" if manual entry was used
#     "status": "complete",
#     "notes": "Text extracted. Supplier matched: AFFI1. PO extracted: 40085..."
# }
```

## Next Steps

1. **Initialize Database:** First run will automatically create tables
2. **Configure Suppliers:** Use menu option 2 to build PO/Amount profiles
3. **Process Batch:** Use menu option 6 for improved extraction
4. **Monitor Progress:** Check database tables for detailed extraction status

## Benefits

✓ Supplier-specific extraction patterns
✓ Automatic detection and extraction
✓ Visual PDF reference during manual entry
✓ Complete audit trail in database
✓ Track human vs. automated extraction
✓ Better handling of incomplete extractions
✓ No more regex escape sequence warnings

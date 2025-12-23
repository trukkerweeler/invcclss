# Quick Start - Document Processor

## What Changed

A new **Document Processor** module has been added that provides a complete workflow for:

- Browsing PDF files in a folder
- Displaying PDFs on the left side
- Showing extracted data on the right side
- Manually editing fields
- Saving records with filename association

## Key Features

✅ **Filename Pattern Recognition**: Automatically extracts supplier code from filenames like `2025-01_BLAN1_invoice.pdf`

✅ **Two-Tier Data Extraction**:

1.  First tries location-based patterns (if configured for supplier)
2.  Falls back to text pattern matching if not found

✅ **Side-by-Side Layout**: PDF on left, editable form fields on right

✅ **Batch Processing**: Navigate through multiple files with Previous/Next buttons

✅ **Database Integration**: Saves extracted data with filename association

✅ **Kept Testing Tools**: Original "Test Location Extraction" menu item still available

## How to Use

### 1. Start the Application

```
python main.py
```

### 2. Open Document Processor

- Click: **File** → **Document Processor**
- Opens in a new window

### 3. Select a Folder

- Click **"Browse Folder"**
- Choose folder with PDF files
- First PDF loads automatically

### 4. Extract Data

- PDF displays on left
- Click **"Extract Data"** button
- Right panel shows extracted values:
  - Supplier Code (from filename)
  - PO Number (from location or text patterns)
  - Amount (from location or text patterns)
  - Check No, Receiver ID (optional fields)

### 5. Review & Edit

- All fields are editable (except filename)
- Correct any values as needed
- Use PDF page navigation if needed

### 6. Save

- Click **"Save Record"**
- Data saves to database with filename association
- Automatically moves to next file
- Or use **Previous/Next** to manually navigate

### 7. Clear Form

- Click **"Clear Form"** to reset editable fields
- Supplier Code from filename is preserved

## File Pattern Recognition

The application recognizes filenames like:

```
2025-01_BLAN1_invoice.pdf
2024-12_ROCK2_statement.pdf
2025-02_GILM1_po.pdf
```

Format: `YYYY-MM_SUPPLIERCODE_*`

The supplier code is automatically extracted and trusted.

## Data Extraction Strategy

### Primary: Location-Based (if configured)

Uses bounding box coordinates from `location_mappings.json` for precise field extraction using OCR.

### Fallback: Text Pattern Matching

Searches for keywords like "PO", "Total", "Amount" and extracts numeric values.

## Database Record

Each saved record includes:

- `filename`: PDF filename
- `supplier_code`: From filename pattern
- `po_number`: Extracted or edited
- `amount`: Extracted or edited
- `check_no`: Optional
- `receiver_id`: Optional
- `human_field`: Marked 'Y' (user confirmed)
- `status`: 'pending' for review if needed

## For Troubleshooting

**Still available in Tools menu:**

- **Test Location Extraction**: Test a single PDF against supplier patterns

Use this to verify location mappings are correct before batch processing.

## Tips

1. **Before bulk processing**: Test a sample PDF with your supplier code using Tools → Test Location Extraction
2. **Location mappings**: Define them in `location_mappings.json` for better extraction
3. **Supplier codes**: Keep filenames consistent with pattern for automatic recognition
4. **Review mode**: Always review extracted data before saving
5. **Navigation**: Use Previous/Next to go through files, or browse folder again to restart

## Files Modified/Created

**New:**

- `document_processor.py` - Main processor module
- `DOCUMENT_PROCESSOR_GUIDE.md` - Full documentation

**Updated:**

- `gui.py` - Added File menu with Document Processor option, kept Tools menu

## Example Workflow

1. Scanned invoices named: `2025-01_BLAN1_001.pdf`, `2025-01_BLAN1_002.pdf`, etc.
2. Open Document Processor
3. Browse to folder
4. For each file:
   - PDF shows on left
   - Supplier code "BLAN1" extracted automatically from filename
   - Click "Extract Data" to get PO and amount
   - Review values
   - Edit if needed
   - Click "Save Record"
   - Moves to next file
5. All records saved with filenames in database

# Document Processor Implementation

## Overview

A new document processor module has been created that provides a side-by-side PDF viewer and form editor for batch processing invoice/document files.

## Features Implemented

### 1. File Iteration & Browsing

- **Browse Folder**: Select a folder containing PDF files
- **File Navigation**: Previous/Next buttons to iterate through documents
- **File List**: Maintains sorted list of all PDFs in folder
- **File Counter**: Shows current file position (e.g., "File 2/10")

### 2. Filename Pattern Parsing

- Automatically parses filenames with pattern: `YYYY-MM_XXXXX_*`
- Extracts supplier code (XXXXX portion) automatically
- Associates supplier code with the record
- Trusts the supplier code from the filename

### 3. PDF Display (Left Side)

- Full PDF viewer with PyMuPDF (fitz)
- Page navigation (Previous/Next buttons)
- Page counter showing current page position
- Zoom rendering for better OCR compatibility
- Canvas-based display with auto-scrolling

### 4. Form Fields (Right Side)

- **Filename** (read-only): Auto-populated from selected file
- **Supplier Code** (editable): Auto-populated from filename pattern
- **PO Number** (editable): Extracted or manually entered
- **Amount** (editable): Extracted or manually entered
- **Check No** (editable): Optional field
- **Receiver ID** (editable): Optional field

### 5. Data Extraction Strategy

**Two-tier extraction approach:**

1. **First Priority**: Location-based patterns (if configured for supplier)
   - Uses bounding box coordinates from `location_mappings.json`
   - OCRs the specific region for accurate extraction
2. **Second Priority**: Text patterns (if location extraction fails)
   - Searches PDF text for keywords: "PO", "PO NO", "PO#", "Purchase Order", "Total", "Amount", "Invoice Total"
   - Extracts numeric values following these patterns
   - Fallback to ensure data is extracted even without location mappings

### 6. Save Functionality

- **Save Record Button**: Saves extracted/edited data to database
- **Database Association**:
  - Links record to original filename
  - Stores file path for reference
  - Marks record as human-edited (Y)
  - Sets status as 'pending' for review if needed
- **Auto-Advance**: After saving, automatically moves to next document
- **Validation**: Ensures supplier code is present before saving

### 7. Form Management

- **Extract Data Button**: Runs extraction pipeline (location → text patterns)
- **Clear Form Button**: Resets editable fields (keeps supplier code from filename)
- **Status Bar**: Shows processing status and messages

### 8. Navigation

- **Top Toolbar**: Browse, Previous, Next buttons with file counter
- **PDF Toolbar**: Page navigation for multi-page documents
- **Form Buttons**: Extract, Save, Clear

## File Structure

### New Files

- **document_processor.py**: Main module with DocumentProcessor class
  - DocumentProcessor class: Main UI controller
  - run_document_processor(): Entry point function

### Modified Files

- **gui.py**: Updated to include Document Processor menu option
  - Added File menu with "Document Processor" option
  - Added open_document_processor() method to launch in new window
  - Kept existing Tools menu for troubleshooting tests

## Database Integration

Saves to `extraction_results` table with:

- `filename`: PDF filename with path
- `file_path`: Full path to PDF
- `supplier_code`: Extracted from filename pattern
- `po_number`: From location or text patterns
- `amount`: From location or text patterns
- `check_no`: Optional, user-entered
- `receiver_id`: Optional, user-entered
- `human_field`: Marked 'Y' (user confirmed/edited)
- `status`: Set to 'pending'
- `extraction_date`: Current timestamp

## Usage Workflow

1. **Launch Document Processor**

   - From main application: File → Document Processor
   - Opens in new window (non-blocking)

2. **Select Folder**

   - Click "Browse Folder"
   - Choose folder containing PDFs
   - Application loads and displays first PDF

3. **View & Extract**

   - Left panel shows PDF with page navigation
   - Click "Extract Data" to run extraction pipeline
   - Right panel shows extracted values

4. **Review & Edit**

   - Fields are editable (except filename)
   - Review extracted values
   - Correct any errors manually

5. **Save**

   - Click "Save Record" when satisfied
   - Record saved to database with filename association
   - Automatically advances to next document

6. **Repeat**
   - Process continues through all files in folder
   - Can navigate with Previous/Next buttons at any time

## Configuration Requirements

### Location Mappings (location_mappings.json)

Define bounding boxes for suppliers to enable location-based extraction:

```json
{
  "SUPPCODE": {
    "po": {
      "x0": 100,
      "y0": 200,
      "x1": 300,
      "y1": 250,
      "page": 0
    },
    "amount": {
      "x0": 400,
      "y0": 500,
      "x1": 550,
      "y1": 550,
      "page": 0
    }
  }
}
```

### Supplier Profiles

Maintained in database/supplier_profiles.json for supplier identification

## Testing & Troubleshooting

**Original test functions preserved in Tools menu:**

- Test Location Extraction: Single PDF test for configuration validation

**Recommended testing workflow:**

1. Start with known suppliers that have location patterns configured
2. Use Test Location Extraction to verify settings
3. Then process batch in Document Processor

## Error Handling

- **No PDFs found**: Warning message shown
- **PDF load failure**: Error message with details
- **Extraction errors**: Graceful fallback to next method
- **Save errors**: User is notified with error details

## Status Messages

- "Ready" - Application initialized
- "Loaded: [filename] (Supplier: [code])" - File loaded successfully
- "Data extracted. Review and edit..." - Extraction complete
- "Saved: [filename]" - Record successfully saved
- "Error loading PDF" - PDF failed to load

## Notes for Future Enhancements

- Could add keyboard shortcuts (Enter=Save, →/←=Next/Prev)
- Could add undo/redo for form fields
- Could add a preview of extracted fields confidence
- Could add bulk import/export features
- Could add supplier code override if filename pattern doesn't match

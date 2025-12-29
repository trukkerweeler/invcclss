# PDF Magnifier Feature for Option 6

## Overview

Option 6 ("Extract with Supplier Matching") now includes an enhanced PDF magnifier tool that allows you to zoom in and out of documents while reviewing them.

## Features

### 1. **Zoom Slider**

- Located at the top of the PDF preview panel
- Range: 50% to 300%
- Displays current zoom level as a percentage
- Smoothly zooms in/out for detailed inspection

### 2. **Mouse Wheel Zooming**

- Scroll up with mouse wheel to zoom in
- Scroll down with mouse wheel to zoom out
- Zoom adjusts in 10% increments
- Works with standard scroll wheels on Windows and Linux

### 3. **Pan/Drag Navigation**

- When zoomed in, you can pan around the document
- Middle-click and drag to move the view around
- Useful for navigating large zoomed-in areas
- Horizontal and vertical scrollbars appear when zoomed

### 4. **Reset Button**

- Quickly reset zoom to 100%
- Returns pan position to default
- Useful to get back to full view after zooming

## How to Use

### Zooming In

**Option A:** Use the slider

1. Locate the "Zoom:" slider at the top of the PDF preview
2. Drag right to zoom in (up to 300%)
3. Drag left to zoom out (down to 50%)

**Option B:** Use mouse wheel

1. Position cursor over the PDF
2. Scroll wheel up to zoom in
3. Scroll wheel down to zoom out

### Navigating Zoomed Documents

1. When zoomed in beyond 100%, the scrollbars will appear
2. You can:
   - Click and drag with middle mouse button to pan
   - Use scrollbars to navigate
   - Use arrow keys to scroll

### Returning to Normal View

- Click the "Reset" button to return to 100% zoom
- Or manually set the slider back to 100%

## Use Cases

- **Finding Small Details:** Zoom to 150-200% to locate fine print, small numbers, or signatures
- **Reading Document Headers:** Zoom to specific areas to clearly read supplier names, invoice numbers, etc.
- **Quality Control:** Verify extracted data by zooming into the original document
- **PO Number Verification:** Zoom in on the PO field to confirm the extracted number is correct

## Technical Details

### Supported PDF Formats

- Standard PDF files
- Multi-page PDFs (only first page is displayed for now)
- Image-based PDFs (scanned documents)

### Performance

- Smooth zooming up to 300%
- Real-time updates as you adjust the slider
- Efficient image scaling using high-quality resampling

### Keyboard Shortcuts

- Not yet implemented, but scrollbars and drag operations work

## Future Enhancements

Potential additions for future versions:

- Multi-page navigation
- OCR text overlay with highlighting
- Measurement tools
- Annotation capabilities
- Save zoomed views

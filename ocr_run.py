from pdf_utils import configure_tesseract, get_ocr_enabled, extract_text
import sys


def main(path):
    print('Configuring Tesseract...')
    ok = configure_tesseract()
    print('TESSERACT_OK', ok, 'OCR_ENABLED', get_ocr_enabled())
    try:
        txt = extract_text(path)
        print('CHARS:', len(txt))
        print('PREVIEW:')
        if txt:
            print(txt[:2000])
        else:
            print('<EMPTY>')
    except Exception as e:
        print('ERROR', e)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python ocr_run.py <pdf_path>')
        sys.exit(2)
    main(sys.argv[1])

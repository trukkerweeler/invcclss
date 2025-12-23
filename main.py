from tkinter import Tk
from gui import InvoiceClassifierApp
from pdf_utils import configure_tesseract

if __name__ == "__main__":
    configure_tesseract()
    root = Tk()
    app = InvoiceClassifierApp(root)
    root.mainloop()
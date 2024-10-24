import io
import re
import PyPDF2
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage
import pytesseract
from pdf2image import convert_from_path


def parse_pdf(pdf_path):
    """
    Parse a PDF file into plain text, handling both single-column and double-column layouts.
    First tries PyPDF2, then falls back to pdfminer, and finally uses OCR for images.
    
    :param pdf_path: str, path to the PDF file
    :return: str, extracted text from the PDF
    """
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
        if not text.strip():
            raise Exception("PyPDF2 failed to extract text")
        return text
    except Exception:
        try:
            # If PyPDF2 fails, fall back to pdfminer
            text = ""
            resource_manager = PDFResourceManager()
            fake_file_handle = io.StringIO()
            converter = TextConverter(resource_manager, fake_file_handle, laparams=LAParams())
            page_interpreter = PDFPageInterpreter(resource_manager, converter)
            
            with open(pdf_path, 'rb') as fh:
                for page in PDFPage.get_pages(fh, caching=True, check_extractable=True):
                    page_interpreter.process_page(page)
                text = fake_file_handle.getvalue()
            converter.close()
            fake_file_handle.close()
            
            if not text.strip():
                raise Exception("pdfminer failed to extract text")
            return text
        except Exception:
            # If both PyPDF2 and pdfminer fail, use OCR
            text = ""
            images = convert_from_path(pdf_path)
            for image in images:
                text += pytesseract.image_to_string(image)
            return text


def clean_text(text):
    """
    Clean the extracted text by removing extra whitespace and joining hyphenated words.
    
    :param text: str, input text to clean
    :return: str, cleaned text
    """
    text = re.sub(r'<latexit[^>]*>(.*?)</latexit>', '', text)
    text = ' '.join(text.split())
    text = re.sub(r'(\w+)-\s*\s*(\w+)', r'\1\2', text)

    return text


def parse_and_clean_pdf(pdf_path):
    """
    Parse a PDF file, clean the extracted text, and save it to a txt file.
    
    :param pdf_path: str, path to the PDF file
    :return: str, path to the saved txt file
    """
    raw_text = parse_pdf(pdf_path)
    cleaned_text = clean_text(raw_text)
    return cleaned_text

import io
import os
import re
import warnings
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage

# Filter PyPDF2 warnings about float objects
warnings.filterwarnings('ignore', category=UserWarning, module='PyPDF2')


def download_pdf(filename, url, output_dir):
    """
    Download a PDF file and save it to the specified directory.
    
    :param title: str, title of the paper
    :param url: str, URL of the PDF
    :param output_dir: str, directory to save the PDF
    """
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _download_with_retry():
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to download PDF: HTTP {response.status_code}")
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath

    try:
        return _download_with_retry()
    except Exception as e:
        print(f"Failed to download after retries: {str(e)}")
        return None


def parse_pdf(pdf_path, use_pypdf2=False):
    """
    Parse a PDF file into plain text, handling both single-column and double-column layouts.
    Uses pdfminer by default, falls back to OCR for images, and optionally can use PyPDF2.
    
    :param pdf_path: str, path to the PDF file
    :param use_pypdf2: bool, whether to use PyPDF2 as the first method (default: False)
    :return: str, extracted text from the PDF
    """
    if use_pypdf2:
        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text()
            if text.strip():
                return text
        except Exception:
            pass  # Fall through to pdfminer if PyPDF2 fails

    # Try pdfminer first
    try:
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
        
        if text.strip():
            return text
    except Exception:
        pass

    # If pdfminer fails, use OCR as last resort
    try:
        text = ""
        images = convert_from_path(pdf_path)
        for image in images:
            text += pytesseract.image_to_string(image)
        return text
    except Exception as e:
        print(f"All PDF parsing methods failed. Last error: {str(e)}")
        return ""


def clean_text(text):
    """
    Clean the extracted text by removing extra whitespace and removing non-UTF-8 characters.
    
    :param text: str, input text to clean
    :return: str, cleaned text
    """
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Remove non-UTF-8 characters
    text = ''.join(char for char in text if ord(char) < 128)
        
    return text

import os
from typing import Optional

from docx import Document
from PyPDF2 import PdfReader
import docx2txt
from PIL import Image

def extract_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())

def extract_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(para.text for para in doc.paragraphs)

def extract_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def extract_content(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[-1].lower()
    if ext == ".pdf":
        return extract_pdf(path)
    elif ext == ".docx":
        try:
            return extract_docx(path)
        except Exception:
            return docx2txt.process(path)
    elif ext == ".txt":
        return extract_txt(path)
    else:
        return None

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.app.services.script_parser.deterministic import ParserError

TEXT_EXTENSIONS = frozenset({".txt", ".text", ".script", ".fountain", ".md"})
PDF_EXTENSION = ".pdf"


def extract_script_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension in TEXT_EXTENSIONS:
        return _decode_text(content)
    if extension == PDF_EXTENSION:
        return _extract_pdf_text(content)
    raise ParserError("unsupported script file type; use TXT, TEXT, SCRIPT, FOUNTAIN, MD, or PDF")


def _decode_text(content: bytes) -> str:
    if not content:
        raise ParserError("uploaded script file is empty")
    if b"\x00" in content:
        raise ParserError("uploaded text file appears to be binary")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.strip():
            return text
    raise ParserError("uploaded text file could not be decoded")


def _extract_pdf_text(content: bytes) -> str:
    if not content:
        raise ParserError("uploaded PDF is empty")
    try:
        reader = PdfReader(BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, OSError, ValueError) as error:
        raise ParserError("uploaded PDF could not be read") from error
    if not text.strip():
        raise ParserError("PDF contains no extractable text; OCR is required for scanned scripts")
    return text

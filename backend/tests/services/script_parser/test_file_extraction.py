from io import BytesIO

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from backend.app.services.script_parser import ParserError
from backend.app.services.script_parser.file_extraction import (
    _decode_text,
    _extract_pdf_text,
    extract_script_text,
)


def test_extract_script_text_decodes_utf8_and_cp1252() -> None:
    assert extract_script_text("play.txt", b"SCENE 1\nHAMLET: Hello") == ("SCENE 1\nHAMLET: Hello")
    assert _decode_text("JOS\u00c9".encode("cp1252")) == "JOS\u00c9"


def test_extract_script_text_supports_script_extension() -> None:
    assert extract_script_text("play.script", b"SCENE 1") == "SCENE 1"


def test_extract_script_text_rejects_unsupported_binary_and_empty_files() -> None:
    with pytest.raises(ParserError, match="unsupported"):
        extract_script_text("play.docx", b"content")
    with pytest.raises(ParserError, match="binary"):
        extract_script_text("play.txt", b"bad\x00data")
    with pytest.raises(ParserError, match="empty"):
        extract_script_text("play.txt", b"")


def test_pdf_without_text_requests_ocr() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    content = BytesIO()
    writer.write(content)
    with pytest.raises(ParserError, match="OCR is required"):
        _extract_pdf_text(content.getvalue())


def test_text_pdf_is_extracted() -> None:
    content = BytesIO()
    canvas = Canvas(content)
    canvas.drawString(72, 720, "SCENE 1 - Palace")
    canvas.drawString(72, 700, "ALADDIN: Hello")
    canvas.save()
    text = extract_script_text("aladdin.pdf", content.getvalue())
    assert "SCENE 1 - Palace" in text
    assert "ALADDIN: Hello" in text


def test_invalid_pdf_is_rejected() -> None:
    with pytest.raises(ParserError, match="could not be read"):
        extract_script_text("play.pdf", b"not a pdf")

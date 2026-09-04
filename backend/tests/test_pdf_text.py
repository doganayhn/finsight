import logging
import sys
from io import BytesIO

import pytest
from pdf_factory import synthetic_pdf
from pypdf import PdfWriter

from app.modules.imports.exceptions import PDFTextExtractionError
from app.modules.imports.parsers.pdf_text import extract_pdf_text


def test_extract_preserves_page_boundaries_and_hides_text_repr():
    doc = extract_pdf_text(synthetic_pdf(["SYNTHETIC PRIVATE TEXT", "second page"]))
    assert [p.number for p in doc.pages] == [1, 2]
    assert "SYNTHETIC PRIVATE TEXT" in doc.pages[0].text
    assert "second page" in doc.pages[1].text
    assert "SYNTHETIC PRIVATE TEXT" not in repr(doc)
    assert not hasattr(doc, "metadata")


@pytest.mark.parametrize("content", [b"not a PDF PRIVATE_SENTINEL", b"%PDF-1.7\nPRIVATE_SENTINEL"])
def test_malformed_pdf_has_safe_error(content, caplog):
    with pytest.raises(PDFTextExtractionError) as error:
        extract_pdf_text(content)
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert not caplog.records


def test_encrypted_pdf_rejected():
    with pytest.raises(PDFTextExtractionError, match="Encrypted"):
        extract_pdf_text(synthetic_pdf(["synthetic"], encrypted=True))


@pytest.mark.parametrize("blank_page", [True, False])
def test_no_text_layer_or_pages_fail_without_ocr(blank_page):
    writer = PdfWriter()
    if blank_page:
        writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    with pytest.raises(PDFTextExtractionError, match="no usable text layer|no pages"):
        extract_pdf_text(output.getvalue())


def test_upstream_diagnostics_are_not_logged_or_chained(monkeypatch, caplog):
    from app.modules.imports.parsers import pdf_text

    logger = logging.getLogger("pypdf._reader")
    original_filters = list(logger.filters)

    def fail(*args, **kwargs):
        logger.warning("PRIVATE_SENTINEL")
        raise ValueError("PRIVATE_SENTINEL")

    monkeypatch.setattr(pdf_text, "PdfReader", fail)
    with pytest.raises(PDFTextExtractionError) as error:
        extract_pdf_text(b"%PDF-1.7")
    assert str(error.value) == "PDF text extraction failed"
    assert error.value.__suppress_context__
    assert not caplog.records
    assert logger.filters == original_filters


def test_lazy_upstream_logger_cannot_leak_source_tokens(monkeypatch, caplog):
    from app.modules.imports.parsers import pdf_text

    name = "pypdf._synthetic_diagnostic"
    monkeypatch.setitem(sys.modules, name, pdf_text)
    assert name not in logging.Logger.manager.loggerDict

    def fail(*args, **kwargs):
        logging.getLogger(name).warning("PRIVATE_SENTINEL")
        raise ValueError("PRIVATE_SENTINEL")

    monkeypatch.setattr(pdf_text, "PdfReader", fail)
    with pytest.raises(PDFTextExtractionError):
        extract_pdf_text(b"%PDF-1.7")
    assert not caplog.records
    assert logging.getLogger(name).filters == []

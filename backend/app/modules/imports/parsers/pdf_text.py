"""Text-layer extraction in memory. No OCR, metadata, logging, or file persistence."""

import logging
import sys
from io import BytesIO

from pypdf import PdfReader

from app.modules.imports.exceptions import PDFTextExtractionError
from app.modules.imports.schemas import ExtractedDocument, ExtractedPage


class _DiscardPDFDiagnostics(logging.Filter):
    def filter(self, record):
        # Upstream parser diagnostics may contain malformed source tokens.
        return False


def extract_pdf_text(data: bytes, *, max_pages: int | None = None) -> ExtractedDocument:
    if not data.startswith(b"%PDF-"):
        raise PDFTextExtractionError("Input is not a PDF")
    # pypdf emits diagnostics through named child loggers. Filter only those;
    # never modify the application's root logging level or handlers.
    # pypdf creates many loggers lazily at the first warning. Include imported
    # module names, not only loggers already present in the logging registry.
    names = set(sys.modules) | set(logging.Logger.manager.loggerDict)
    loggers = [
        logging.getLogger(name) for name in names if name == "pypdf" or name.startswith("pypdf.")
    ]
    diagnostic_filter = _DiscardPDFDiagnostics()
    for logger in loggers:
        logger.addFilter(diagnostic_filter)
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PDFTextExtractionError("Encrypted PDFs are unsupported")
        if not reader.pages:
            raise PDFTextExtractionError("PDF has no pages")
        if max_pages is not None and len(reader.pages) > max_pages:
            raise PDFTextExtractionError("PDF page limit exceeded")
        pages = tuple(
            ExtractedPage(index, page.extract_text(extraction_mode="plain") or "")
            for index, page in enumerate(reader.pages, 1)
        )
        if not any(page.text.strip() for page in pages):
            raise PDFTextExtractionError("PDF has no usable text layer; OCR is unsupported")
        return ExtractedDocument(pages)
    except PDFTextExtractionError:
        raise
    except Exception:
        raise PDFTextExtractionError("PDF text extraction failed") from None
    finally:
        for logger in loggers:
            logger.removeFilter(diagnostic_filter)

"""
PDF Text Extractor
Downloads PDFs from BSE/NSE and extracts clean text for AI processing.
Handles both embedded-text PDFs and scanned (OCR) documents.
"""
from __future__ import annotations

import io
import logging
import tempfile
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_PLUMBER_AVAILABLE = True
except ImportError:
    PDF_PLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not installed — PDF extraction unavailable")

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("pytesseract/PIL not installed — OCR unavailable")


async def extract_text_from_url(
    client: httpx.AsyncClient,
    url: str,
    max_pages: int = 20,
) -> Optional[str]:
    """
    Download a PDF from url and extract text.
    Returns None if download or extraction fails.
    """
    try:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("PDF download failed (%s): %s", url, exc)
        return None

    content_type = resp.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
        # Might be an inline HTML page, not a PDF — return response text
        return resp.text[:8000]

    return extract_text_from_bytes(resp.content, max_pages=max_pages)


def extract_text_from_bytes(
    pdf_bytes: bytes,
    max_pages: int = 20,
) -> Optional[str]:
    """
    Extract text from raw PDF bytes.
    Tries pdfplumber first; falls back to OCR.
    """
    if not PDF_PLUMBER_AVAILABLE:
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages[:max_pages]
            parts: list[str] = []

            for page in pages:
                # Try embedded text first
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text and len(text.strip()) > 50:
                    parts.append(text)
                elif OCR_AVAILABLE:
                    # Page is likely scanned — render as image and OCR
                    img = page.to_image(resolution=200).original
                    ocr_text = pytesseract.image_to_string(img, lang="eng")
                    if ocr_text.strip():
                        parts.append(ocr_text)

        full_text = "\n\n".join(parts)
        return _clean_text(full_text)

    except Exception as exc:
        logger.error("PDF extraction error: %s", exc)
        return None


def extract_text_from_file(path: str, max_pages: int = 20) -> Optional[str]:
    with open(path, "rb") as f:
        return extract_text_from_bytes(f.read(), max_pages=max_pages)


def _clean_text(text: str) -> str:
    """
    Remove excess whitespace, page numbers, headers/footers boilerplate.
    """
    import re
    # Remove page headers/footers (lines with only numbers or common boilerplate)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip pure page number lines
        if re.fullmatch(r"\d+", stripped):
            continue
        # Skip very short lines that are likely headers
        if len(stripped) < 4:
            continue
        cleaned.append(stripped)

    # Collapse multiple blank lines
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 200) -> list[str]:
    """Split long text into overlapping chunks for LLM processing."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

"""
PDF downloader + text extractor for Company Research Worker.
Re-uses the core PDF parsing logic from the Order Tracking worker,
extended with full-document chunking for embedding.
"""
from __future__ import annotations

import io
import re
from typing import Any

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)",
    "Referer": "https://www.bseindia.com/",
}

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


async def download_pdf(client: httpx.AsyncClient, url: str) -> bytes | None:
    """Download a PDF from a URL. Returns raw bytes or None on failure."""
    try:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            return None
        return resp.content
    except Exception:
        return None


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.
    Primary: pdfplumber. Fallback: pytesseract OCR per page.
    """
    if not pdf_bytes:
        return ""

    text_parts: list[str] = []

    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if len(page_text.strip()) < 50 and HAS_OCR:
                        # Likely scanned — fall back to OCR
                        img = page.to_image(resolution=200).original
                        page_text = pytesseract.image_to_string(img, lang="eng")
                    text_parts.append(page_text)
        except Exception:
            pass

    if not text_parts and HAS_OCR:
        # Full OCR fallback
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text_parts.append(pytesseract.image_to_string(img))
        except Exception:
            pass

    raw = "\n\n".join(text_parts)
    return _clean_text(raw)


def _clean_text(text: str) -> str:
    """Remove page numbers, headers/footers, collapse whitespace."""
    # Remove lines that are just page numbers or very short
    lines = [l for l in text.splitlines() if len(l.strip()) > 20 or l.strip() == ""]
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    # Collapse internal whitespace
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def chunk_text(
    text: str,
    chunk_size: int = 3000,
    overlap: int = 200,
) -> list[dict]:
    """
    Split text into overlapping chunks for embedding.
    Returns list of {chunk_index, text, token_count} dicts.
    Splits on paragraph boundaries where possible.
    """
    if not text:
        return []

    # Prefer paragraph splits
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[dict] = []
    current = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": current,
                    "token_count": len(current.split()),
                })
                chunk_idx += 1
                # Carry overlap
                words = current.split()
                current = " ".join(words[-overlap // 5:]) + "\n\n" + para
            else:
                current = para

    if current.strip():
        chunks.append({
            "chunk_index": chunk_idx,
            "text": current.strip(),
            "token_count": len(current.split()),
        })

    return chunks


async def fetch_and_extract(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """
    Download PDF from URL, extract text, return (text, page_count).
    page_count is 0 if extraction failed.
    """
    pdf_bytes = await download_pdf(client, url)
    if not pdf_bytes:
        return "", 0

    page_count = 0
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            pass

    text = extract_text_from_bytes(pdf_bytes)
    return text, page_count

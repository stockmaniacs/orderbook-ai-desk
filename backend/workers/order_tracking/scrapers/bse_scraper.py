"""
BSE Corporate Announcement Scraper
Fetches order-win announcements from BSE Corp Filings API.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from .nse_scraper import last_trading_day

logger = logging.getLogger(__name__)

# BSE Corp Filing API endpoint (public, no auth required)
BSE_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_CORP_ANNOUNCE = f"{BSE_BASE}/AnnSubCategoryGetData/w"
BSE_DOC_DOWNLOAD = "https://www.bseindia.com/xml-data/corpfiling/AttachHis"

# Categories most likely to contain order announcements
ORDER_CATEGORIES = [
    "New Orders",
    "Order Win",
    "Contract Award",
    "Business Updates",
    "Outcome of Board Meeting",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Research Platform/1.0)",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}


class BSEOrderScraper:
    """Fetches and filters BSE corporate announcements for order wins."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self):
        if self._owns_client:
            self._client = httpx.AsyncClient(
                headers=HEADERS, timeout=30, follow_redirects=True
            )
        return self

    async def __aexit__(self, *args):
        if self._owns_client and self._client:
            await self._client.aclose()

    # ─────────────────────────────────────────────────────────────────────────
    async def fetch_recent_announcements(
        self,
        days_back: int = 1,
        scrip_cd: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch BSE announcements from the last N days.
        Returns raw announcement dicts ready for AI extraction.
        """
        trade_day = last_trading_day()
        from_date = trade_day.strftime("%Y%m%d")
        to_date = trade_day.strftime("%Y%m%d")

        params = {
            "pageno": "1",
            "strCat": "-1",
            "strPrevDate": from_date,
            "strScrip": scrip_cd or "",
            "strSearch": "P",
            "strToDate": to_date,
            "strType": "C",
        }

        try:
            resp = await self._client.get(BSE_CORP_ANNOUNCE, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("BSE API error: %s", exc)
            return []

        announcements = data.get("Table", [])
        return [self._parse_announcement(a) for a in announcements if self._is_order_related(a)]

    # ─────────────────────────────────────────────────────────────────────────
    def _is_order_related(self, ann: dict) -> bool:
        """Heuristic filter — keep only order/contract announcements."""
        category = ann.get("SUBCATNAME", "").lower()
        headline = ann.get("HEADLINE", "").lower()

        order_keywords = [
            "order", "contract", "work order", "letter of intent", "loi",
            "epc", "procurement", "supply order", "awarded", "securing",
            "bagged", "received order", "new project", "agreement",
        ]
        exclude_keywords = ["dividend", "agm", "egm", "result", "buyback", "rights"]

        for kw in exclude_keywords:
            if kw in category or kw in headline:
                return False

        return any(kw in category or kw in headline for kw in order_keywords)

    # ─────────────────────────────────────────────────────────────────────────
    def _parse_announcement(self, ann: dict) -> dict:
        """Normalise BSE announcement to internal format."""
        file_name = ann.get("ATTACHMENTNAME", "")
        pdf_url = f"{BSE_DOC_DOWNLOAD}/{file_name}" if file_name else None

        # Build content hash for dedup
        raw = f"BSE|{ann.get('NEWSID', '')}|{ann.get('SCRIP_CD', '')}"
        content_hash = hashlib.sha256(raw.encode()).hexdigest()

        announced_str = ann.get("NEWS_DT", "")
        try:
            announced_date = datetime.strptime(announced_str[:10], "%Y-%m-%d").date()
        except Exception:
            announced_date = date.today()

        return {
            "source": "BSE",
            "source_id": str(ann.get("NEWSID", "")),
            "source_url": pdf_url,
            "symbol_bse": str(ann.get("SCRIP_CD", "")),
            "company_name": ann.get("SLONGNAME", ""),
            "isin": ann.get("ISIN_CODE", ""),
            "headline": ann.get("HEADLINE", ""),
            "category": ann.get("SUBCATNAME", ""),
            "announced_date": announced_date.isoformat(),
            "pdf_url": pdf_url,
            "content_hash": content_hash,
            "raw_text": ann.get("HEADLINE", ""),  # full text from PDF parser
        }

    # ─────────────────────────────────────────────────────────────────────────
    async def download_pdf_text(self, pdf_url: str) -> Optional[str]:
        """Download BSE PDF and return raw text (delegated to pdf_parser)."""
        from .pdf_parser import extract_text_from_url
        return await extract_text_from_url(self._client, pdf_url)

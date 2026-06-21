"""
NSE Corporate Filings Scraper
Fetches order announcements from NSE Corporate Filings API.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# NSE public holidays 2026 (add more as needed)
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 2),    # Holi
    date(2026, 3, 30),   # Ram Navami
    date(2026, 4, 2),    # Good Friday
    date(2026, 4, 6),    # Mahavir Jayanti
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 21),  # Diwali Laxmi Pujan
    date(2026, 10, 22),  # Diwali Balipratipada
    date(2026, 11, 5),   # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


def last_trading_day(ref: date | None = None) -> date:
    """Return the most recent NSE trading day (skips weekends + holidays)."""
    d = ref or date.today()
    # Step back until we hit a weekday that isn't a holiday
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in NSE_HOLIDAYS_2026:
        d -= timedelta(days=1)
    return d

NSE_BASE = "https://www.nseindia.com"
NSE_CORP_FILINGS = f"{NSE_BASE}/api/corporate-announcements"
NSE_DOC = f"{NSE_BASE}/corporate-announcements"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    "X-Requested-With": "XMLHttpRequest",
}

ORDER_SUBJECTS = [
    "order", "contract", "work order", "loi", "letter of intent",
    "epc", "procurement", "supply", "awarded", "project", "secured",
    "bagged", "win", "agreement for", "receipt of order",
]

EXCLUDE_SUBJECTS = [
    "dividend", "agm", "egm", "result", "buyback", "rights issue",
    "board meeting", "closure of register", "record date",
]


class NSEOrderScraper:
    """Fetches and filters NSE corporate filings for order wins."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self):
        if self._owns_client:
            self._client = httpx.AsyncClient(
                headers=HEADERS, timeout=30, follow_redirects=True
            )
            # NSE requires a session cookie — hit the homepage first
            await self._client.get(NSE_BASE)
        return self

    async def __aexit__(self, *args):
        if self._owns_client and self._client:
            await self._client.aclose()

    # ─────────────────────────────────────────────────────────────────────────
    async def fetch_recent_filings(
        self,
        days_back: int = 1,
        symbol: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch NSE corporate announcements for the last N days.
        """
        trade_day = last_trading_day()
        from_dt = trade_day.strftime("%d-%m-%Y")
        to_dt = trade_day.strftime("%d-%m-%Y")

        params = {
            "index": "equities",
            "from_date": from_dt,
            "to_date": to_dt,
        }
        if symbol:
            params["symbol"] = symbol

        try:
            # NSE often needs the main page loaded first for cookies
            resp = await self._client.get(NSE_CORP_FILINGS, params=params)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            logger.error("NSE API error: %s", exc)
            return []

        filings = raw if isinstance(raw, list) else raw.get("data", [])
        return [
            self._parse_filing(f)
            for f in filings
            if self._is_order_related(f)
        ]

    # ─────────────────────────────────────────────────────────────────────────
    def _is_order_related(self, filing: dict) -> bool:
        subject = filing.get("subject", "").lower()
        body = filing.get("body", "").lower()
        text = f"{subject} {body}"

        for kw in EXCLUDE_SUBJECTS:
            if kw in text:
                return False
        return any(kw in text for kw in ORDER_SUBJECTS)

    # ─────────────────────────────────────────────────────────────────────────
    def _parse_filing(self, filing: dict) -> dict:
        raw_key = f"NSE|{filing.get('an_no', '')}|{filing.get('symbol', '')}"
        content_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        date_str = filing.get("an_dt", "")
        try:
            announced_date = datetime.strptime(date_str[:10], "%d-%m-%Y").date()
        except Exception:
            try:
                announced_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except Exception:
                announced_date = date.today()

        attach = filing.get("attchmntFile", "")
        pdf_url = f"{NSE_BASE}{attach}" if attach else None

        return {
            "source": "NSE",
            "source_id": str(filing.get("an_no", "")),
            "source_url": pdf_url,
            "symbol_nse": filing.get("symbol", ""),
            "company_name": filing.get("sm_name", ""),
            "isin": filing.get("isin", ""),
            "headline": filing.get("subject", ""),
            "category": filing.get("desc", ""),
            "announced_date": announced_date.isoformat(),
            "pdf_url": pdf_url,
            "content_hash": content_hash,
            "raw_text": filing.get("body", filing.get("subject", "")),
        }

    # ─────────────────────────────────────────────────────────────────────────
    async def download_pdf_text(self, pdf_url: str) -> Optional[str]:
        from .pdf_parser import extract_text_from_url
        return await extract_text_from_url(self._client, pdf_url)

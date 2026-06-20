"""
BSE document fetcher for Company Research Worker.
Fetches: annual reports, investor presentations, concall transcripts,
         quarterly results, and general announcements.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

import httpx

BSE_CORP_ACTION = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_COMPANY_INFO = "https://api.bseindia.com/BseIndiaAPI/api/CompanyHeader/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

# Subcategory codes → our doc_type mapping
SUBCATEGORY_MAP = {
    "annual report": "ANNUAL_REPORT",
    "annual rep": "ANNUAL_REPORT",
    "investor presentation": "INVESTOR_PRESENTATION",
    "analyst/investor meet": "INVESTOR_PRESENTATION",
    "con call": "CONCALL_TRANSCRIPT",
    "conference call": "CONCALL_TRANSCRIPT",
    "earnings call": "CONCALL_TRANSCRIPT",
    "press release": "NEWS",
    "financial results": "QUARTERLY_RESULTS",
    "quarterly results": "QUARTERLY_RESULTS",
    "half yearly results": "QUARTERLY_RESULTS",
    "management interview": "MANAGEMENT_INTERVIEW",
}


def _content_hash(source: str, source_id: str) -> str:
    return hashlib.sha256(f"{source}:{source_id}".encode()).hexdigest()


def _classify_doc(sub_cat: str) -> str:
    lower = sub_cat.lower().strip()
    for key, doc_type in SUBCATEGORY_MAP.items():
        if key in lower:
            return doc_type
    return "BSE_ANNOUNCEMENT"


def _parse_fiscal_year(ann_date: date) -> tuple[int, str]:
    """Return (fiscal_year, quarter) from an announcement date."""
    # Indian FY: Apr–Mar
    if ann_date.month >= 4:
        fy = ann_date.year + 1
    else:
        fy = ann_date.year
    month = ann_date.month
    if 4 <= month <= 6:
        quarter = f"Q1FY{str(fy)[2:]}"
    elif 7 <= month <= 9:
        quarter = f"Q2FY{str(fy)[2:]}"
    elif 10 <= month <= 12:
        quarter = f"Q3FY{str(fy)[2:]}"
    else:
        quarter = f"Q4FY{str(fy)[2:]}"
    return fy, quarter


class BSEDocumentFetcher:
    """Async context manager. Fetches research documents for a company from BSE."""

    def __init__(self, bse_code: str, isin: str):
        self.bse_code = bse_code
        self.isin = isin
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BSEDocumentFetcher":
        self._client = httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def fetch_announcements(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        days_back: int = 365,
    ) -> list[dict]:
        """
        Fetch all research-relevant announcements for a company.
        Returns list of normalized document dicts (not yet in DB).
        """
        if not from_date:
            from_date = date.today() - timedelta(days=days_back)
        if not to_date:
            to_date = date.today()

        params = {
            "pageno": 1,
            "strCat": "-1",        # all categories
            "strPrevDate": from_date.strftime("%Y%m%d"),
            "strScrip": self.bse_code,
            "strSearch": "P",
            "strToDate": to_date.strftime("%Y%m%d"),
            "strType": "C",
        }

        docs = []
        page = 1
        while True:
            params["pageno"] = page
            try:
                resp = await self._client.get(BSE_CORP_ACTION, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                break

            items = data.get("Table", [])
            if not items:
                break

            for item in items:
                source_id = str(item.get("NEWSID", ""))
                sub_cat = item.get("SUBCATNAME", "")
                cat_name = item.get("CATEGORYNAME", "")
                headline = item.get("HEADLINE", "")
                pdf_url = item.get("ATTACHMENTNAME", "")
                dt_str = item.get("NEWS_DT", "")

                try:
                    ann_date = date.fromisoformat(dt_str[:10])
                except Exception:
                    ann_date = date.today()

                fy, quarter = _parse_fiscal_year(ann_date)
                doc_type = _classify_doc(sub_cat or cat_name)

                # Only collect research-relevant doc types
                if doc_type not in {
                    "ANNUAL_REPORT", "INVESTOR_PRESENTATION", "CONCALL_TRANSCRIPT",
                    "QUARTERLY_RESULTS", "MANAGEMENT_INTERVIEW", "BSE_ANNOUNCEMENT",
                    "NEWS",
                }:
                    continue

                docs.append({
                    "isin": self.isin,
                    "doc_type": doc_type,
                    "title": headline,
                    "source": "BSE",
                    "source_url": f"https://www.bseindia.com/stockinfo/AnnPdfLinks.aspx?Pname={pdf_url}" if pdf_url else None,
                    "fiscal_year": fy,
                    "quarter": quarter,
                    "published_date": ann_date.isoformat(),
                    "content_hash": _content_hash("BSE", source_id),
                    "_raw_pdf_name": pdf_url,
                    "_source_id": source_id,
                })

            # BSE returns 25 items per page
            if len(items) < 25:
                break
            page += 1

        return docs

    async def fetch_annual_reports(self) -> list[dict]:
        """Fetch historical annual report links (last 5 years)."""
        return [
            d for d in await self.fetch_announcements(days_back=365 * 6)
            if d["doc_type"] == "ANNUAL_REPORT"
        ]

    async def fetch_concall_transcripts(self) -> list[dict]:
        return [
            d for d in await self.fetch_announcements(days_back=365 * 3)
            if d["doc_type"] == "CONCALL_TRANSCRIPT"
        ]

    async def fetch_investor_presentations(self) -> list[dict]:
        return [
            d for d in await self.fetch_announcements(days_back=365 * 3)
            if d["doc_type"] == "INVESTOR_PRESENTATION"
        ]

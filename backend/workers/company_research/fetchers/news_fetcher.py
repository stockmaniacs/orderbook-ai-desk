"""
News fetcher for Company Research Worker.
Sources: Google News RSS + Economic Times / Business Standard RSS feeds.
Extracts news relevant to a specific company (by name + NSE symbol).
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)",
    "Accept": "application/rss+xml,application/xml,text/xml",
}

# News sources (RSS)
RSS_SOURCES = {
    "google_news": "https://news.google.com/rss/search?q={query}+site:economictimes.com+OR+site:businessstandard.com+OR+site:moneycontrol.com&hl=en-IN&gl=IN&ceid=IN:en",
    "economic_times": "https://economictimes.indiatimes.com/rssfeeds/{ticker}.cms",
    "moneycontrol": "https://www.moneycontrol.com/rss/results.xml",
}


def _content_hash(source: str, url: str) -> str:
    return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()


def _parse_pub_date(pub_date_str: str) -> date:
    try:
        return parsedate_to_datetime(pub_date_str).date()
    except Exception:
        return date.today()


def _is_relevant(text: str, company_name: str, symbol: str) -> bool:
    """Quick relevance check — company name or symbol must appear."""
    lower = text.lower()
    name_parts = [p.lower() for p in company_name.split() if len(p) > 3]
    # At least 2 name parts (or the symbol) must match
    matches = sum(1 for p in name_parts if p in lower)
    return matches >= 2 or (symbol and symbol.lower() in lower)


class NewsArticleFetcher:
    """Fetch recent news articles for a company from RSS feeds."""

    def __init__(self, isin: str, company_name: str, symbol_nse: str):
        self.isin = isin
        self.company_name = company_name
        self.symbol_nse = symbol_nse or ""
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "NewsArticleFetcher":
        self._client = httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _fetch_rss(self, url: str) -> list[dict]:
        """Fetch and parse a single RSS feed."""
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except Exception:
            return []

        articles = []
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return []

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date_str = item.findtext("pubDate") or ""
            pub_date = _parse_pub_date(pub_date_str)

            # Skip old news
            if (date.today() - pub_date).days > 90:
                continue

            combined = f"{title} {description}"
            if not _is_relevant(combined, self.company_name, self.symbol_nse):
                continue

            articles.append({
                "isin": self.isin,
                "doc_type": "NEWS",
                "title": title,
                "source": "NEWS_FEED",
                "source_url": link,
                "fiscal_year": None,
                "quarter": None,
                "published_date": pub_date.isoformat(),
                "content_hash": _content_hash("NEWS", link),
                "_snippet": re.sub(r"<[^>]+>", "", description)[:500],
            })

        return articles

    async def fetch_recent_news(self, days_back: int = 90) -> list[dict]:
        """Fetch news from all sources, deduplicated by URL."""
        # Build Google News query
        short_name = self.company_name.split(" ")[0]
        query = f"{short_name}+{self.symbol_nse}+NSE+stock+results".replace(" ", "+")
        google_url = RSS_SOURCES["google_news"].format(query=query)

        all_articles: list[dict] = []
        seen_hashes: set[str] = set()

        for url in [google_url]:
            articles = await self._fetch_rss(url)
            for art in articles:
                h = art["content_hash"]
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    all_articles.append(art)

        # Sort by date descending
        all_articles.sort(key=lambda a: a["published_date"], reverse=True)
        return all_articles[:50]  # cap at 50 per company

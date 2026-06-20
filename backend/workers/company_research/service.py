"""
Service layer — Company Research Worker.
Orchestrates the full incremental update pipeline:
  1. Detect new / changed documents for a company
  2. Extract only changed fields
  3. Synthesize only affected thesis sections
  4. Build / patch the markdown report
  5. Version and persist everything
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Company, CompanyFinancials, DocumentChunk, InvestmentThesis,
    ResearchDocument, ResearchField, ResearchFieldHistory,
    ResearchReport, ResearchTask,
)
from .fetchers.bse_fetcher import BSEDocumentFetcher
from .fetchers.news_fetcher import NewsArticleFetcher
from .fetchers.pdf_fetcher import fetch_and_extract, chunk_text
from .ai.extractor import extract_research_fields, fields_needing_update
from .ai.researcher import generate_investment_thesis, sections_to_update_from_changed_fields
from .ai.report_builder import build_report_markdown, diff_summary

try:
    import google.generativeai as genai
    _EMBED_MODEL = "models/text-embedding-004"
    _HAS_EMBED = True
except ImportError:
    _HAS_EMBED = False


# ─── Embedding ────────────────────────────────────────────────────────────────

async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts with text-embedding-004 (768 dim)."""
    if not _HAS_EMBED or not texts:
        return [[] for _ in texts]
    result = genai.embed_content(
        model=_EMBED_MODEL,
        content=texts,
        task_type="retrieval_document",
    )
    return result["embedding"]


# ─── Document ingestion ───────────────────────────────────────────────────────

async def ingest_document(
    db: AsyncSession,
    doc_meta: dict,
    http_client: httpx.AsyncClient,
) -> tuple[ResearchDocument | None, bool]:
    """
    Register a document in the DB and extract its text.
    Returns (document, is_new).  Skips if already ingested (dedup by content_hash).
    """
    content_hash = doc_meta.get("content_hash")
    if not content_hash:
        return None, False

    # Dedup check
    existing = await db.scalar(
        select(ResearchDocument).where(ResearchDocument.content_hash == content_hash)
    )
    if existing:
        return existing, False

    # Create record
    doc = ResearchDocument(
        isin=doc_meta["isin"],
        doc_type=doc_meta["doc_type"],
        title=doc_meta.get("title"),
        source=doc_meta.get("source"),
        source_url=doc_meta.get("source_url"),
        fiscal_year=doc_meta.get("fiscal_year"),
        quarter=doc_meta.get("quarter"),
        published_date=doc_meta.get("published_date"),
        content_hash=content_hash,
    )
    db.add(doc)
    await db.flush()  # get doc.id

    # Download + extract text if URL available
    source_url = doc_meta.get("source_url")
    if source_url:
        text, page_count = await fetch_and_extract(http_client, source_url)
    else:
        text = doc_meta.get("_snippet", "")
        page_count = 0

    doc.page_count = page_count
    doc.file_size_bytes = len(text.encode()) if text else 0
    doc.text_extracted = bool(text)

    if text:
        # Chunk and embed
        chunks = chunk_text(text)
        embeddings = await _embed_texts([c["text"] for c in chunks])

        for chunk, emb in zip(chunks, embeddings):
            dc = DocumentChunk(
                document_id=doc.id,
                isin=doc.isin,
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                token_count=chunk["token_count"],
            )
            db.add(dc)
            if emb:
                # Set pgvector embedding via raw SQL after flush
                await db.flush()
                await db.execute(
                    "UPDATE research_doc_chunks SET embedding = :emb WHERE id = :id",
                    {"emb": str(emb), "id": str(dc.id)},
                )

    await db.commit()
    return doc, True


# ─── Field extraction + update ────────────────────────────────────────────────

async def update_research_fields(
    db: AsyncSession,
    isin: str,
    company_name: str,
    doc: ResearchDocument,
    doc_text: str,
) -> list[str]:
    """
    Extract research fields from a document and incrementally update the DB.
    Returns list of field names that actually changed.
    """
    # Load existing fields for this company
    result = await db.execute(
        select(ResearchField).where(ResearchField.isin == isin)
    )
    existing_rows = {r.field_name: r for r in result.scalars().all()}
    existing_meta = {
        name: {
            "primary_source": row.primary_source,
            "is_stale": row.is_stale,
            "version": row.version,
        }
        for name, row in existing_rows.items()
    }

    # Determine which fields to re-extract
    fields_to_extract = fields_needing_update(existing_meta, str(doc.id), doc.doc_type)
    if not fields_to_extract:
        return []

    fiscal_period = doc.quarter or (f"FY{doc.fiscal_year}" if doc.fiscal_year else "")

    # Call Gemini Flash
    extraction = await extract_research_fields(
        text=doc_text,
        company_name=company_name,
        isin=isin,
        doc_type=doc.doc_type,
        fiscal_period=fiscal_period,
        fields_to_extract=fields_to_extract,
    )

    extracted = extraction.get("extracted_fields", {})
    changed_fields: list[str] = []

    for field_name, field_data in extracted.items():
        value = field_data.get("value")
        confidence = float(field_data.get("confidence", 0.3))

        # Skip low-confidence null values
        if value is None and confidence < 0.5:
            continue

        value_text = value if isinstance(value, str) else None
        value_json = value if not isinstance(value, str) else None
        key_quote = field_data.get("key_quote")
        fp = field_data.get("fiscal_period") or fiscal_period

        existing = existing_rows.get(field_name)

        if existing:
            # Only update if value meaningfully changed
            old_text = existing.value_text or ""
            new_text = value_text or (json.dumps(value_json) if value_json else "")
            if old_text.strip() == new_text.strip() and not existing.is_stale:
                continue

            # Archive current version
            db.add(ResearchFieldHistory(
                field_id=existing.id,
                isin=isin,
                field_name=field_name,
                version=existing.version,
                value_text=existing.value_text,
                value_json=existing.value_json,
                confidence=existing.confidence,
                source_types=existing.source_types,
                update_reason=existing.update_reason,
            ))

            # Update in-place
            existing.value_text = value_text
            existing.value_json = value_json
            existing.confidence = confidence
            existing.source_doc_ids = json.loads(
                json.dumps(list({*(existing.source_doc_ids or []), str(doc.id)}))
            )
            existing.source_types = list({*(existing.source_types or []), doc.doc_type})
            existing.primary_source = doc.doc_type
            existing.fiscal_period = fp
            existing.as_of_date = doc.published_date
            existing.version += 1
            existing.last_updated = datetime.utcnow()
            existing.update_reason = key_quote or f"Updated from {doc.doc_type}"
            existing.is_stale = False

        else:
            # New field
            from .ai.extractor import RESEARCH_FIELDS
            field_def = next((f for f in RESEARCH_FIELDS if f["name"] == field_name), {})
            db.add(ResearchField(
                isin=isin,
                field_name=field_name,
                field_category=field_def.get("category"),
                value_text=value_text,
                value_json=value_json,
                confidence=confidence,
                source_doc_ids=[str(doc.id)],
                source_types=[doc.doc_type],
                primary_source=doc.doc_type,
                fiscal_period=fp,
                as_of_date=doc.published_date,
                update_reason=key_quote or f"First extraction from {doc.doc_type}",
            ))

        changed_fields.append(field_name)

    # Mark doc as AI-extracted
    doc.ai_extracted = True
    doc.processed_at = datetime.utcnow()

    await db.commit()
    return changed_fields


# ─── Thesis synthesis ─────────────────────────────────────────────────────────

async def update_thesis(
    db: AsyncSession,
    company: Company,
    changed_fields: list[str],
    financials: dict,
) -> InvestmentThesis:
    """
    Generate or update the investment thesis for a company.
    Only regenerates sections affected by changed_fields.
    """
    # Load all current fields
    result = await db.execute(
        select(ResearchField).where(ResearchField.isin == company.isin)
    )
    fields_dict = {
        r.field_name: {
            "value_text": r.value_text,
            "value_json": r.value_json,
            "confidence": float(r.confidence or 0),
            "fiscal_period": r.fiscal_period,
            "primary_source": r.primary_source,
        }
        for r in result.scalars().all()
    }

    # Load existing thesis
    existing = await db.scalar(
        select(InvestmentThesis).where(InvestmentThesis.isin == company.isin)
    )

    thesis_data = await generate_investment_thesis(
        company_name=company.company_name,
        isin=company.isin,
        sector=company.sector or "",
        market_cap_cr=float(company.market_cap_cr or 0),
        market_cap_cat=company.market_cap_cat or "",
        current_price=financials.get("current_price", 0),
        financials=financials,
        extracted_fields=fields_dict,
        changed_fields=changed_fields,
    )

    def _float(v: Any) -> float | None:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    if existing:
        # Patch only non-null keys returned by the LLM
        for key, val in thesis_data.items():
            if val is not None and hasattr(existing, key):
                setattr(existing, key, val)
        existing.version += 1
        existing.sections_updated = thesis_data.get("sections_updated", [])
        existing.last_updated = datetime.utcnow()
    else:
        existing = InvestmentThesis(
            isin=company.isin,
            company_name=company.company_name,
            one_liner=thesis_data.get("one_liner"),
            thesis_text=thesis_data.get("thesis_text"),
            strengths=thesis_data.get("strengths"),
            weaknesses=thesis_data.get("weaknesses"),
            opportunities=thesis_data.get("opportunities"),
            threats=thesis_data.get("threats"),
            bull_case=thesis_data.get("bull_case"),
            bull_cagr_pct=_float(thesis_data.get("bull_cagr_pct")),
            bull_target_cr=_float(thesis_data.get("bull_target_cr")),
            base_case=thesis_data.get("base_case"),
            base_cagr_pct=_float(thesis_data.get("base_cagr_pct")),
            base_target_cr=_float(thesis_data.get("base_target_cr")),
            bear_case=thesis_data.get("bear_case"),
            bear_cagr_pct=_float(thesis_data.get("bear_cagr_pct")),
            bear_target_cr=_float(thesis_data.get("bear_target_cr")),
            bull_probability=_float(thesis_data.get("bull_probability")),
            base_probability=_float(thesis_data.get("base_probability")),
            bear_probability=_float(thesis_data.get("bear_probability")),
            current_price=_float(financials.get("current_price")),
            fair_value_low=_float(thesis_data.get("fair_value_low")),
            fair_value_mid=_float(thesis_data.get("fair_value_mid")),
            fair_value_high=_float(thesis_data.get("fair_value_high")),
            target_price_12m=_float(thesis_data.get("target_price_12m")),
            expected_cagr_3y=_float(thesis_data.get("expected_cagr_3y")),
            rating=thesis_data.get("rating"),
            confidence_score=_float(thesis_data.get("confidence_score")),
            sections_updated=thesis_data.get("sections_updated", []),
        )
        db.add(existing)

    await db.commit()
    return existing


# ─── Report generation ────────────────────────────────────────────────────────

async def build_and_save_report(
    db: AsyncSession,
    company: Company,
    thesis: InvestmentThesis,
    changed_fields: list[str],
    trigger: str,
) -> ResearchReport:
    """
    Build an incremental markdown report and save it.
    Previous report's is_current is set to False.
    """
    # Load current fields
    result = await db.execute(
        select(ResearchField).where(ResearchField.isin == company.isin)
    )
    fields_dict = {
        r.field_name: {
            "value_text": r.value_text,
            "value_json": r.value_json,
            "confidence": float(r.confidence or 0),
            "fiscal_period": r.fiscal_period,
        }
        for r in result.scalars().all()
    }

    # Load previous report
    prev_report = await db.scalar(
        select(ResearchReport)
        .where(ResearchReport.isin == company.isin, ResearchReport.is_current == True)
        .order_by(ResearchReport.report_version.desc())
    )
    prev_version = prev_report.report_version if prev_report else 0
    prev_content = prev_report.markdown_content if prev_report else None

    # Determine changed sections from changed fields
    changed_sections = sections_to_update_from_changed_fields(changed_fields)

    company_dict = {
        "isin": company.isin,
        "company_name": company.company_name,
        "symbol_nse": company.symbol_nse,
        "sector": company.sector,
        "market_cap_cr": float(company.market_cap_cr or 0),
        "market_cap_cat": company.market_cap_cat,
    }

    thesis_dict = {
        k: getattr(thesis, k, None)
        for k in [
            "one_liner", "thesis_text", "strengths", "weaknesses",
            "opportunities", "threats", "bull_case", "bull_cagr_pct",
            "bull_target_cr", "base_case", "base_cagr_pct", "base_target_cr",
            "bear_case", "bear_cagr_pct", "bear_target_cr",
            "bull_probability", "base_probability", "bear_probability",
            "current_price", "fair_value_low", "fair_value_mid", "fair_value_high",
            "target_price_12m", "expected_cagr_3y", "rating", "confidence_score",
        ]
    }

    markdown, actually_changed = build_report_markdown(
        company=company_dict,
        thesis=thesis_dict,
        fields=fields_dict,
        financials={},
        version=prev_version + 1,
        trigger=trigger,
        changed_sections=changed_sections,
        previous_report=prev_content,
    )

    # Deactivate previous
    if prev_report:
        prev_report.is_current = False

    # Count source docs
    doc_count_result = await db.execute(
        select(ResearchDocument).where(ResearchDocument.isin == company.isin)
    )
    doc_count = len(doc_count_result.scalars().all())

    new_report = ResearchReport(
        isin=company.isin,
        company_name=company.company_name,
        report_version=prev_version + 1,
        is_current=True,
        markdown_content=markdown,
        trigger=trigger,
        sections_changed=actually_changed,
        diff_summary=diff_summary(actually_changed, trigger),
        word_count=len(markdown.split()),
        source_doc_count=doc_count,
        confidence_score=float(thesis.confidence_score or 0),
    )
    db.add(new_report)
    await db.commit()
    return new_report


# ─── Full pipeline orchestrator ───────────────────────────────────────────────

async def run_research_pipeline(
    db: AsyncSession,
    isin: str,
    force_full: bool = False,
) -> dict:
    """
    Full research pipeline for a single company:
      1. Fetch new documents from BSE + News
      2. Ingest + extract text
      3. Extract changed fields
      4. Update thesis
      5. Build report
    """
    company = await db.scalar(
        select(Company).where(Company.isin == isin)
    )
    if not company:
        return {"error": f"Company {isin} not found in registry"}

    # Update status
    company.research_status = "IN_PROGRESS"
    await db.commit()

    stats = {
        "isin": isin,
        "company_name": company.company_name,
        "new_docs": 0,
        "changed_fields": [],
        "report_version": None,
    }

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http_client:
        # ── 1. Fetch documents from BSE ───────────────────────────────────────
        all_doc_metas: list[dict] = []
        if company.bse_code:
            async with BSEDocumentFetcher(company.bse_code, isin) as bse:
                all_doc_metas.extend(await bse.fetch_announcements(days_back=90 if not force_full else 365 * 5))

        # Fetch news
        async with NewsArticleFetcher(isin, company.company_name, company.symbol_nse or "") as news:
            all_doc_metas.extend(await news.fetch_recent_news(days_back=60))

        # ── 2. Ingest each document ───────────────────────────────────────────
        all_changed_fields: list[str] = []
        last_trigger = ""

        for doc_meta in all_doc_metas:
            doc, is_new = await ingest_document(db, doc_meta, http_client)
            if not doc or not is_new:
                continue

            stats["new_docs"] += 1
            last_trigger = f"{doc.doc_type} ({doc.quarter or doc.fiscal_year or 'undated'})"

            # Get text from chunks
            chunks_result = await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.chunk_index)
            )
            doc_text = "\n\n".join(c.text for c in chunks_result.scalars().all())

            if not doc_text:
                continue

            # ── 3. Extract changed fields ─────────────────────────────────────
            changed = await update_research_fields(
                db, isin, company.company_name, doc, doc_text
            )
            all_changed_fields.extend(changed)

    # Deduplicate
    all_changed_fields = list(set(all_changed_fields))
    stats["changed_fields"] = all_changed_fields

    if not all_changed_fields and not force_full:
        company.research_status = "DONE"
        await db.commit()
        return stats

    # ── 4. Update thesis ──────────────────────────────────────────────────────
    latest_fin = await db.scalar(
        select(CompanyFinancials)
        .where(CompanyFinancials.isin == isin, CompanyFinancials.is_consolidated == True)
        .order_by(CompanyFinancials.fiscal_year.desc(), CompanyFinancials.period_type.desc())
    )
    fin_dict = {}
    if latest_fin:
        fin_dict = {
            "revenue": float(latest_fin.revenue or 0),
            "ebitda_margin": float(latest_fin.ebitda_margin or 0),
            "net_debt": float(latest_fin.net_debt or 0),
            "debt_equity": float(latest_fin.debt_equity or 0),
            "roe": float(latest_fin.roe or 0),
            "roce": float(latest_fin.roce or 0),
            "revenue_cagr_3y": 0.0,
            "pat_cagr_3y": 0.0,
        }

    thesis = await update_thesis(db, company, all_changed_fields, fin_dict)

    # ── 5. Build report ───────────────────────────────────────────────────────
    trigger = last_trigger or "Scheduled research update"
    report = await build_and_save_report(db, company, thesis, all_changed_fields, trigger)
    stats["report_version"] = report.report_version

    # Mark done
    company.research_status = "DONE"
    company.last_research_date = datetime.utcnow()
    await db.commit()

    return stats


# ─── Dashboard assembly ───────────────────────────────────────────────────────

async def get_research_dashboard(db: AsyncSession, isin: str) -> dict | None:
    company = await db.scalar(
        select(Company).where(Company.isin == isin)
    )
    if not company:
        return None

    thesis = await db.scalar(
        select(InvestmentThesis).where(InvestmentThesis.isin == isin)
    )
    fields_result = await db.execute(
        select(ResearchField).where(ResearchField.isin == isin)
    )
    fields = fields_result.scalars().all()

    report = await db.scalar(
        select(ResearchReport)
        .where(ResearchReport.isin == isin, ResearchReport.is_current == True)
    )
    docs_result = await db.execute(
        select(ResearchDocument).where(ResearchDocument.isin == isin)
        .order_by(ResearchDocument.published_date.desc()).limit(10)
    )
    fin = await db.scalar(
        select(CompanyFinancials)
        .where(CompanyFinancials.isin == isin, CompanyFinancials.is_consolidated == True)
        .order_by(CompanyFinancials.fiscal_year.desc()).limit(1)
    )

    return {
        "company": company,
        "thesis": thesis,
        "fields": list(fields),
        "latest_report": report,
        "recent_docs": list(docs_result.scalars().all()),
        "latest_financials": fin,
    }


async def get_universe(
    db: AsyncSession,
    sector: str | None = None,
    rating: str | None = None,
    min_confidence: float = 0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    q = (
        select(Company, InvestmentThesis)
        .join(InvestmentThesis, InvestmentThesis.isin == Company.isin, isouter=True)
        .where(Company.is_active == True)
    )
    if sector:
        q = q.where(Company.sector == sector)
    if rating:
        q = q.where(InvestmentThesis.rating == rating)
    if min_confidence:
        q = q.where(InvestmentThesis.confidence_score >= min_confidence)

    q = q.order_by(InvestmentThesis.confidence_score.desc().nullslast()).limit(limit).offset(offset)
    result = await db.execute(q)

    rows = []
    for company, thesis in result.all():
        current_price = float(thesis.current_price or 0) if thesis else 0
        target = float(thesis.target_price_12m or 0) if thesis else 0
        upside = ((target / current_price) - 1) * 100 if current_price and target else None
        rows.append({
            "isin": company.isin,
            "symbol_nse": company.symbol_nse,
            "company_name": company.company_name,
            "sector": company.sector,
            "market_cap_cr": float(company.market_cap_cr or 0),
            "market_cap_cat": company.market_cap_cat,
            "rating": thesis.rating if thesis else None,
            "confidence_score": float(thesis.confidence_score or 0) if thesis else None,
            "expected_cagr_3y": float(thesis.expected_cagr_3y or 0) if thesis else None,
            "target_price_12m": target or None,
            "current_price": current_price or None,
            "upside_pct": upside,
            "last_research_date": company.last_research_date,
        })
    return rows

# AI-First Indian Stock Market Research Platform — Complete Architecture

> **Version:** 1.0 | **Date:** 2026-06-19  
> **Role:** Chief Architect Blueprint (pre-code design)

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Topology](#3-system-topology)
4. [Cross-Cutting Concerns](#4-cross-cutting-concerns)
5. [Shared Database Conventions](#5-shared-database-conventions)
6. [Worker 01 — NSE/BSE News Worker](#worker-01--nsebse-news-worker)
7. [Worker 02 — Order Tracking Worker](#worker-02--order-tracking-worker)
8. [Worker 03 — Concall Worker](#worker-03--concall-worker)
9. [Worker 04 — Investor Presentation Worker](#worker-04--investor-presentation-worker)
10. [Worker 05 — Fundamental Worker](#worker-05--fundamental-worker)
11. [Worker 06 — Technical Worker](#worker-06--technical-worker)
12. [Worker 07 — Valuation Worker](#worker-07--valuation-worker)
13. [Worker 08 — Master Tracker Worker](#worker-08--master-tracker-worker)
14. [Worker 09 — Mutual Fund Worker](#worker-09--mutual-fund-worker)
15. [Worker 10 — Alert Worker](#worker-10--alert-worker)
16. [Worker 11 — Dashboard Worker](#worker-11--dashboard-worker)
17. [Inter-Worker Communication Map](#17-inter-worker-communication-map)
18. [Deployment Architecture](#18-deployment-architecture)
19. [Security Architecture](#19-security-architecture)
20. [Scalability Roadmap](#20-scalability-roadmap)

---

## 1. Platform Overview

### Vision

An AI-first research desk that replicates the workflow of an institutional equity research team: ingesting raw data from exchanges, filings, and market feeds; processing it through specialist AI agents; and surfacing structured, actionable intelligence via a Next.js dashboard.

### Core Design Principles

- **Worker Isolation**: each agent owns its schema and API surface; no worker queries another's tables directly.
- **Event-Driven Updates**: workers publish domain events to Redis Streams; downstream workers subscribe and react.
- **AI-Augmented, Not AI-Only**: every worker has a deterministic fast path (rules/SQL) and an AI slow path (LLM enrichment) so the system degrades gracefully when AI is unavailable.
- **Idempotent Jobs**: all Celery tasks are safe to retry; every record carries a content hash to prevent duplicate inserts.
- **Audit Trail**: every AI-generated insight is stored with its source documents, model version, and confidence score.

---

## 2. Technology Stack

### Frontend
| Layer | Choice | Reason |
|---|---|---|
| Framework | Next.js 15 (App Router) | SSR + RSC for fast first paint; streaming for live data |
| Language | TypeScript 5.x | Type safety across API contracts |
| Styling | Tailwind CSS 3.x | Utility-first; consistent design tokens |
| Components | Shadcn/UI (Radix primitives) | Accessible, unstyled, owned in repo |
| Charts | Recharts + Lightweight Charts (TradingView) | General charts + OHLCV candlesticks |
| State | Zustand (client) + React Query (server) | Minimal boilerplate; cache invalidation |
| WebSocket | native browser WebSocket → FastAPI WS | Live price ticks, alert notifications |

### Backend
| Layer | Choice | Reason |
|---|---|---|
| API Framework | Python FastAPI 0.111 | Async-native, auto OpenAPI docs, pydantic v2 |
| Worker Runtime | Celery 5.x + Redis broker | Battle-tested distributed task queue |
| Beat Scheduler | Celery Beat | Cron-style scheduling for periodic ingestion |
| ORM | SQLAlchemy 2.x (async) | Async sessions; Alembic migrations |
| AI / LLM | Google Gemini 1.5 Pro (primary) + Gemini Flash (cheap tasks) | Long context for PDFs/transcripts |
| Embeddings | `text-embedding-004` via Vertex AI | 768-dim vectors stored in pgvector |
| PDF Parsing | pdfplumber + pypdf2 fallback | Extracts text + tables from filings |
| OCR fallback | Tesseract via pytesseract | Scanned annual reports |

### Data Layer
| Layer | Choice | Notes |
|---|---|---|
| Primary DB | PostgreSQL 16 (+ pgvector extension) | OLTP + vector search in one engine |
| Cache / Broker | Redis 7 (Cluster mode in prod) | L2 cache, pub/sub, Celery broker + result backend |
| Object Store | Oracle Cloud Object Storage | Raw PDFs, audio, large JSON blobs |
| Search | PostgreSQL full-text + pgvector | Avoids extra Elasticsearch dependency |

### Infrastructure
| Concern | Choice |
|---|---|
| Hosting | Oracle Cloud (Ampere A1 ARM — 4 OCPU / 24 GB free tier + paid flex) |
| Edge / CDN | Cloudflare (Workers, R2 for static assets, DDoS protection) |
| CI/CD | GitHub Actions → Docker build → Oracle Container Registry |
| Containers | Docker Compose (dev), Kubernetes (prod via OKE) |
| Secrets | Cloudflare Workers KV + Oracle Vault |
| Monitoring | Prometheus + Grafana (self-hosted) |
| Logging | Loki + Promtail |
| Tracing | OpenTelemetry → Tempo |

---

## 3. System Topology

```
┌──────────────────────────────────────────────────────────────────┐
│                        Cloudflare Edge                           │
│  CDN (static assets)  |  WAF  |  Rate Limiting  |  SSL Termination│
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼──────────────────────────────────────┐
│                    Next.js 15 Frontend                           │
│  App Router | RSC | React Query | Zustand | WebSocket client    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼──────────────────────────────────────┐
│                  FastAPI Gateway (Port 8000)                     │
│  Auth Middleware | Rate Limiter | Request Router | WS Manager   │
└──┬────────┬────────┬────────┬────────┬────────┬─────────────────┘
   │        │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼        ▼
[News]  [Orders] [Concall] [Fundm] [Tech]  [Dashboard]   ← FastAPI Routers
   │        │        │        │        │        │           (each in own module)
   └────────┴────────┴───┬────┴────────┘        │
                         │                       │
              ┌──────────▼───────────┐           │
              │   PostgreSQL 16      │◄──────────┘
              │   (+ pgvector)       │
              └──────────────────────┘
                         │
              ┌──────────▼───────────┐
              │    Redis 7 Cluster   │
              │  Cache | Broker | PubSub │
              └──────────────────────┘
                         │
         ┌───────────────▼───────────────────────┐
         │            Celery Workers              │
         │  [news] [orders] [concall] [fundm]    │
         │  [tech] [valuation] [mf] [alerts]     │
         │  [master] [dashboard]                 │
         └───────────────┬───────────────────────┘
                         │
              ┌──────────▼───────────┐
              │  Oracle Object Store │
              │  (PDFs, audio, blobs)│
              └──────────────────────┘
```

### Service Boundaries

Every worker exposes:
- A **FastAPI router** (`/api/v1/{worker}/...`) mounted in the main gateway
- A **Celery task module** (`workers/{worker}/tasks.py`)
- Its own **SQLAlchemy models** (`workers/{worker}/models.py`)
- A **Redis key namespace** (`{worker}:*`)

---

## 4. Cross-Cutting Concerns

### 4.1 Authentication & Authorization

```
User → Next.js → POST /api/v1/auth/login
             ← JWT (access 15 min) + Refresh token (7 days, httpOnly cookie)
All API routes → JWTBearer dependency injection
Role enum: ADMIN | ANALYST | VIEWER
```

- Tokens signed with RS256 (private key in Oracle Vault)
- Refresh token rotation on each use
- Per-route RBAC decorators (`@require_role(Role.ANALYST)`)

### 4.2 Caching Strategy

```
L1: In-process LRU (TTL 30s) — price ticks, dashboard counters
L2: Redis (TTL varies per worker) — processed data, AI summaries
L3: PostgreSQL — source of truth
```

Cache key convention: `{worker}:{entity_type}:{id}:{version}`

### 4.3 Event Bus (Redis Streams)

Each worker publishes domain events consumed by downstream workers:

| Stream | Producer | Consumers |
|---|---|---|
| `stream:news` | News Worker | Alert Worker, Dashboard Worker |
| `stream:price_tick` | Technical Worker | Alert Worker, Dashboard Worker |
| `stream:fundamentals_updated` | Fundamental Worker | Valuation Worker, Master Tracker |
| `stream:concall_processed` | Concall Worker | Master Tracker, Alert Worker |
| `stream:order_executed` | Order Tracking | Alert Worker, Dashboard Worker |
| `stream:alert_triggered` | Alert Worker | Dashboard Worker |
| `stream:mf_updated` | MF Worker | Master Tracker, Dashboard Worker |

### 4.4 Error Handling Pattern

All Celery tasks follow:
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(TransientError,),
    acks_late=True,
)
def fetch_task(self, ...):
    try:
        ...
    except RateLimitError as e:
        raise self.retry(countdown=exponential_backoff(self.request.retries))
    except PermanentError as e:
        log_to_db(task_id=self.request.id, error=str(e), status="FAILED")
        raise  # do not retry
```

Dead-letter queue in Redis: `dlq:{worker}` — monitored by Alert Worker.

### 4.5 AI Prompt Management

All LLM prompts stored in `prompt_templates` table, versioned, with A/B testing support:

```sql
CREATE TABLE prompt_templates (
    id UUID PRIMARY KEY,
    worker VARCHAR(50),
    task_type VARCHAR(100),
    version INTEGER,
    template TEXT,
    model VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ
);
```

---

## 5. Shared Database Conventions

### Naming
- Tables: `snake_case`, plural
- Primary keys: `UUID` (gen_random_uuid())
- Timestamps: always `TIMESTAMPTZ` (UTC stored, IST displayed in UI)
- Soft deletes: `deleted_at TIMESTAMPTZ NULL`

### Universal Audit Columns (on every table)
```sql
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
created_by  UUID REFERENCES users(id),
version     INTEGER NOT NULL DEFAULT 1  -- optimistic locking
```

### Instruments Master (shared reference table)
```sql
CREATE TABLE instruments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isin        VARCHAR(12) UNIQUE NOT NULL,
    symbol_nse  VARCHAR(20),
    symbol_bse  VARCHAR(20),
    company_name VARCHAR(255) NOT NULL,
    sector      VARCHAR(100),
    industry    VARCHAR(100),
    market_cap_category VARCHAR(10),  -- LARGE / MID / SMALL / MICRO
    is_active   BOOLEAN DEFAULT TRUE,
    listing_date DATE,
    face_value  NUMERIC(10,2),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_instruments_isin ON instruments(isin);
CREATE INDEX idx_instruments_symbol_nse ON instruments(symbol_nse);
```

---

## Worker 01 — NSE/BSE News Worker

### Purpose
Continuously ingests corporate announcements, exchange filings, regulatory notices, and AI-summarises them. Provides the "news feed" consumed by all other workers and the UI.

### Data Sources
| Source | Method | Rate Limit |
|---|---|---|
| NSE Corporate Filings API | REST polling | 60 req/min |
| BSE Corporate Announcements | REST polling | 60 req/min |
| NSE Circulars | RSS + REST | 30 req/min |
| SEBI Notifications | RSS | no limit |
| Financial news aggregators (Moneycontrol, ET Markets) | RSS | no limit |

### Database Schema

```sql
-- Raw ingestion table
CREATE TABLE news_raw (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(50) NOT NULL,  -- NSE | BSE | SEBI | MONEYCONTROL
    source_id       VARCHAR(255) NOT NULL,  -- original ID from source
    instrument_id   UUID REFERENCES instruments(id),
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    published_at    TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    content_hash    VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 for dedup
    processing_status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING|PROCESSING|DONE|FAILED
    CONSTRAINT uq_source_source_id UNIQUE (source, source_id)
);

-- AI-processed news
CREATE TABLE news_processed (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id          UUID NOT NULL REFERENCES news_raw(id),
    instrument_id   UUID REFERENCES instruments(id),
    category        VARCHAR(50),   -- RESULT | ACQUISITION | DIVIDEND | BOARD_MEETING | REGULATORY | OTHER
    sentiment       VARCHAR(10),   -- POSITIVE | NEGATIVE | NEUTRAL
    sentiment_score NUMERIC(4,3),  -- -1.0 to 1.0
    summary         TEXT,          -- AI-generated 2-3 line summary
    key_points      JSONB,         -- array of bullet points
    impact_rating   SMALLINT,      -- 1 (minor) to 5 (major)
    tags            TEXT[],
    model_version   VARCHAR(50),
    processed_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_news_processed_instrument ON news_processed(instrument_id);
CREATE INDEX idx_news_processed_category ON news_processed(category);
CREATE INDEX idx_news_processed_sentiment ON news_processed(sentiment);
CREATE INDEX idx_news_raw_published ON news_raw(published_at DESC);

-- Embeddings for semantic search
CREATE TABLE news_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id         UUID NOT NULL REFERENCES news_processed(id),
    embedding       vector(768),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_news_embeddings_vector ON news_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### APIs

```
GET  /api/v1/news/feed
     ?instrument_id=&category=&sentiment=&from=&to=&page=&limit=
     → paginated list of processed news

GET  /api/v1/news/{id}
     → single news item with full AI analysis

GET  /api/v1/news/instrument/{isin}
     → all news for a stock (last 90 days default)

POST /api/v1/news/search
     body: { query: string, filters: {...} }
     → semantic search via pgvector

GET  /api/v1/news/summary/today
     → AI-generated morning briefing for watchlist stocks

WebSocket /ws/news/live
     → real-time push of new processed articles
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `fetch_nse_announcements` | `*/5 * * * *` | Every 5 min during market hours |
| `fetch_bse_announcements` | `*/5 * * * *` | Every 5 min during market hours |
| `fetch_sebi_circulars` | `0 */2 * * *` | Every 2 hours |
| `fetch_rss_feeds` | `*/15 * * * *` | Every 15 min |
| `process_pending_news` | `*/2 * * * *` | AI enrichment of raw queue |
| `generate_morning_brief` | `0 8 * * 1-5` | Weekdays at 8 AM IST |

### Workflow

```
1. Celery Beat triggers fetch_nse_announcements
2. HTTP GET NSE API → parse response → compute SHA-256 of content
3. INSERT INTO news_raw (ON CONFLICT content_hash DO NOTHING)
4. Publish {raw_id} to Redis Stream stream:news_raw
5. process_pending_news consumer reads stream:
   a. Classify category (rule-based first, LLM for ambiguous)
   b. Sentiment analysis (Gemini Flash — cheap, fast)
   c. Generate summary and key points (Gemini Flash)
   d. Generate embedding (text-embedding-004)
   e. INSERT INTO news_processed + news_embeddings
   f. Update news_raw.processing_status = 'DONE'
   g. Publish to stream:news (consumed by Alert + Dashboard workers)
6. Cache latest 50 news items in Redis (TTL 5 min)
```

### Edge Cases

- **Duplicate filings**: content_hash unique constraint; `ON CONFLICT DO NOTHING`
- **NSE API downtime**: exponential backoff (60s → 120s → 300s); fallback to BSE for cross-listed stocks
- **PDF-only announcements**: download PDF → pdfplumber → extract text → send to LLM
- **Non-English content**: detect language; translate via Gemini before analysis
- **Market holiday**: skip intraday polling; run daily end-of-day batch only
- **Rate limit hit**: back off for 61 seconds; use last-modified header to fetch only delta

### Scalability

- Horizontally scale Celery `news_processor` workers (stateless)
- Partition `news_raw` by month (PostgreSQL declarative partitioning)
- Archive records older than 2 years to Oracle Object Storage

---

## Worker 02 — Order Tracking Worker

### Purpose
Connects to the user's broker (Zerodha Kite, via the connected MCP) to track portfolio positions, executed orders, P&L, and capital utilisation. Maintains a clean internal ledger independent of broker's UI for analytics.

### Data Sources
- Zerodha Kite Connect API (MCP: `mcp__19ebe0ce-*`)
- Internal manual entry for non-Kite brokers

### Database Schema

```sql
CREATE TABLE portfolios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    broker          VARCHAR(50) NOT NULL DEFAULT 'ZERODHA',
    account_id      VARCHAR(100) NOT NULL,
    display_name    VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_broker_account UNIQUE (user_id, broker, account_id)
);

CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id),
    broker_order_id VARCHAR(100) NOT NULL,
    instrument_id   UUID REFERENCES instruments(id),
    symbol          VARCHAR(20) NOT NULL,
    exchange        VARCHAR(10) NOT NULL,
    order_type      VARCHAR(20) NOT NULL,  -- MARKET | LIMIT | SL | SL-M
    product_type    VARCHAR(10) NOT NULL,  -- CNC | MIS | NRML
    transaction_type VARCHAR(5) NOT NULL,  -- BUY | SELL
    quantity        INTEGER NOT NULL,
    price           NUMERIC(12,4),
    trigger_price   NUMERIC(12,4),
    filled_quantity INTEGER DEFAULT 0,
    average_price   NUMERIC(12,4),
    status          VARCHAR(20) NOT NULL,  -- OPEN | COMPLETE | CANCELLED | REJECTED
    status_message  TEXT,
    order_timestamp TIMESTAMPTZ NOT NULL,
    exchange_timestamp TIMESTAMPTZ,
    tags            TEXT[],
    strategy_label  VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_portfolio_broker_order UNIQUE (portfolio_id, broker_order_id)
);
CREATE INDEX idx_orders_portfolio ON orders(portfolio_id);
CREATE INDEX idx_orders_instrument ON orders(instrument_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_timestamp ON orders(order_timestamp DESC);

CREATE TABLE positions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id),
    instrument_id   UUID REFERENCES instruments(id),
    symbol          VARCHAR(20) NOT NULL,
    product_type    VARCHAR(10) NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 0,
    average_price   NUMERIC(12,4) NOT NULL DEFAULT 0,
    last_price      NUMERIC(12,4),
    pnl             NUMERIC(15,4),
    pnl_pct         NUMERIC(8,4),
    day_pnl         NUMERIC(15,4),
    buy_value       NUMERIC(15,4),
    sell_value      NUMERIC(15,4),
    as_of           TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_portfolio_symbol_product UNIQUE (portfolio_id, symbol, product_type)
);

CREATE TABLE holdings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id),
    instrument_id   UUID REFERENCES instruments(id),
    isin            VARCHAR(12) NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    quantity        INTEGER NOT NULL,
    average_price   NUMERIC(12,4) NOT NULL,
    last_price      NUMERIC(12,4),
    close_price     NUMERIC(12,4),
    pnl             NUMERIC(15,4),
    pnl_pct         NUMERIC(8,4),
    day_change      NUMERIC(8,4),
    t1_quantity     INTEGER DEFAULT 0,   -- T+1 pending settlement
    collateral_quantity INTEGER DEFAULT 0,
    as_of           TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_portfolio_isin UNIQUE (portfolio_id, isin)
);

CREATE TABLE order_analytics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id),
    date            DATE NOT NULL,
    total_orders    INTEGER DEFAULT 0,
    completed_orders INTEGER DEFAULT 0,
    cancelled_orders INTEGER DEFAULT 0,
    total_buy_value NUMERIC(15,4) DEFAULT 0,
    total_sell_value NUMERIC(15,4) DEFAULT 0,
    realised_pnl    NUMERIC(15,4) DEFAULT 0,
    unrealised_pnl  NUMERIC(15,4) DEFAULT 0,
    brokerage       NUMERIC(10,4) DEFAULT 0,
    taxes           NUMERIC(10,4) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_portfolio_date UNIQUE (portfolio_id, date)
);

-- GTT (Good Till Triggered) orders
CREATE TABLE gtt_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id),
    broker_gtt_id   VARCHAR(100) NOT NULL,
    instrument_id   UUID REFERENCES instruments(id),
    symbol          VARCHAR(20) NOT NULL,
    trigger_type    VARCHAR(20),   -- SINGLE | OCO
    trigger_values  JSONB,
    last_price      NUMERIC(12,4),
    status          VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### APIs

```
GET  /api/v1/orders/positions
     → current intraday positions with live P&L

GET  /api/v1/orders/holdings
     → long-term holdings with XIRR and day change

GET  /api/v1/orders/orders
     ?status=&date=&symbol=
     → order book with filters

GET  /api/v1/orders/analytics/summary
     ?from=&to=
     → P&L summary, win rate, best/worst trades

GET  /api/v1/orders/analytics/instrument/{isin}
     → all trades in a stock with FIFO cost basis P&L

GET  /api/v1/orders/margins
     → available margin breakdown

GET  /api/v1/orders/gtts
     → all active GTT orders

WebSocket /ws/orders/positions
     → live position updates (price feed from Technical Worker)
```

### Update Schedule

| Job | Cron / Trigger | Description |
|---|---|---|
| `sync_orders` | `*/1 * * * 1-5` | Every minute during market hours (9:00-15:35) |
| `sync_positions` | `*/1 * * * 1-5` | Every minute (intraday) |
| `sync_holdings` | `30 15 * * 1-5` | After market close (3:30 PM) |
| `sync_gtts` | `*/5 * * * 1-5` | Every 5 min |
| `compute_daily_analytics` | `0 16 * * 1-5` | After settlement |

### Workflow

```
1. sync_orders:
   a. Call Kite get_orders() via MCP
   b. Upsert into orders table (ON CONFLICT broker_order_id UPDATE)
   c. Detect new COMPLETE orders → publish to stream:order_executed
   d. Update Redis cache (TTL 60s)

2. sync_positions:
   a. Call Kite get_positions()
   b. Merge with last_price from Technical Worker cache
   c. Upsert positions table
   d. Broadcast updated P&L via WebSocket to subscribed clients

3. compute_daily_analytics:
   a. Aggregate orders for the day
   b. Calculate brokerage (Zerodha fee structure: ₹20 or 0.03% per order)
   c. Calculate STT, exchange charges, GST
   d. Upsert order_analytics
```

### Edge Cases

- **Broker API timeout**: use cached last-known state; show staleness indicator in UI
- **Order rejection**: parse rejection reason; surface as alert with suggestion
- **Corporate action adjustments**: detect bonus/split/dividend; recalculate average price
- **Multiple accounts**: support portfolio_id scoping across all APIs
- **T+1 / T+2 settlement**: track t1_quantity separately; don't show in available cash

---

## Worker 03 — Concall Worker

### Purpose
Ingests earnings call audio/transcripts from company IR pages, NSE, and third-party sources. Uses AI to extract management commentary, guidance, key risks, and tracks sentiment trends across quarters.

### Data Sources
- NSE corporate filings (audio links)
- BSE announcements
- Company IR websites (scraped)
- Manual upload (PDF transcripts)

### Database Schema

```sql
CREATE TABLE concalls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    quarter         VARCHAR(10) NOT NULL,  -- Q1FY26, Q2FY26...
    fiscal_year     INTEGER NOT NULL,
    call_date       DATE NOT NULL,
    call_type       VARCHAR(20) DEFAULT 'EARNINGS',  -- EARNINGS | ANALYST_DAY | AGM
    audio_url       TEXT,
    transcript_url  TEXT,
    object_store_key TEXT,  -- Oracle Object Storage key
    transcript_text TEXT,   -- extracted full text
    duration_minutes SMALLINT,
    participants    JSONB,   -- [{name, designation, company}]
    processing_status VARCHAR(20) DEFAULT 'PENDING',
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_quarter UNIQUE (instrument_id, quarter)
);

CREATE TABLE concall_analysis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concall_id      UUID NOT NULL REFERENCES concalls(id),
    management_tone VARCHAR(20),    -- BULLISH | NEUTRAL | CAUTIOUS | BEARISH
    tone_score      NUMERIC(4,3),
    revenue_guidance JSONB,   -- {type: POSITIVE|NEGATIVE|FLAT|WITHHELD, commentary: "..."}
    margin_guidance JSONB,
    capex_guidance  JSONB,
    demand_outlook  TEXT,
    key_risks       JSONB,   -- [{risk: "...", severity: HIGH|MED|LOW}]
    key_opportunities JSONB,
    analyst_concerns JSONB,  -- questions raised by analysts
    management_responses JSONB,
    executive_summary TEXT,
    one_liners      TEXT[],  -- 5 most important takeaways
    red_flags       TEXT[],
    model_version   VARCHAR(50),
    processed_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE concall_segments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concall_id      UUID NOT NULL REFERENCES concalls(id),
    segment_index   SMALLINT NOT NULL,
    speaker_name    VARCHAR(255),
    speaker_role    VARCHAR(50),  -- MANAGEMENT | ANALYST | MODERATOR
    start_time_sec  INTEGER,
    end_time_sec    INTEGER,
    text            TEXT NOT NULL,
    topics          TEXT[],
    sentiment       VARCHAR(10),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_concall_segments_concall ON concall_segments(concall_id);

CREATE TABLE concall_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concall_id      UUID NOT NULL REFERENCES concalls(id),
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(768),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_concall_embeddings_vector ON concall_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Quarter-on-quarter comparison
CREATE TABLE concall_trends (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    tone_history    JSONB,   -- [{quarter, tone_score}]
    guidance_trend  JSONB,
    recurring_risks JSONB,
    yoy_delta       TEXT,    -- AI-generated YoY narrative
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### APIs

```
GET  /api/v1/concalls/instrument/{isin}
     → list of all concalls with analysis summary

GET  /api/v1/concalls/{id}
     → full concall with segments and analysis

GET  /api/v1/concalls/{id}/qa
     → analyst Q&A section extracted separately

POST /api/v1/concalls/{id}/ask
     body: { question: string }
     → RAG-based Q&A over the transcript

GET  /api/v1/concalls/compare
     ?isin=&q1=Q1FY26&q2=Q2FY26
     → side-by-side comparison of two quarters

POST /api/v1/concalls/upload
     body: multipart/form-data (PDF or audio)
     → manual transcript upload + processing queue

GET  /api/v1/concalls/trends/{isin}
     → management tone trend chart data (last 8 quarters)
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `scan_new_concalls` | `0 */4 * * 1-5` | Scan NSE/BSE for new concall PDFs |
| `download_transcripts` | Triggered | Downloads PDF/audio to Object Store |
| `transcribe_audio` | Triggered | Whisper/Gemini audio → text |
| `process_transcript` | Triggered | AI analysis pipeline |
| `build_trend_report` | `0 6 * * 1` | Weekly trend rebuild |

### Workflow

```
1. scan_new_concalls → finds new filing on NSE
2. Download PDF to Oracle Object Store
3. Extract text (pdfplumber; OCR fallback)
4. Chunk transcript into 2000-token segments
5. For each segment: classify speaker, extract topics, sentiment
6. Whole-doc analysis (Gemini 1.5 Pro — 1M context):
   a. Executive summary
   b. Revenue / margin / capex guidance
   c. Key risks and opportunities
   d. Management tone score
   e. Red flags
7. Generate embeddings for each chunk
8. Update concall_trends for the stock
9. Publish to stream:concall_processed
```

### Edge Cases

- **Audio-only, no transcript**: use Gemini 1.5 Pro audio understanding (direct audio input)
- **Concurrent speakers / cross-talk**: best-effort speaker diarization; fallback to unnamed segments
- **Very long calls (>2 hours)**: chunk + map-reduce summarization
- **Management guidance contradiction across quarters**: flag in red_flags
- **Non-English sections (Hindi/regional)**: detect, translate, process

---

## Worker 04 — Investor Presentation Worker

### Purpose
Processes investor presentations, annual reports, sustainability reports, and credit ratings. Extracts structured data (financials, strategy, KPIs) and makes them searchable and comparable.

### Database Schema

```sql
CREATE TABLE investor_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    doc_type        VARCHAR(50) NOT NULL,
    -- ANNUAL_REPORT | INVESTOR_PRESENTATION | CREDIT_RATING | SUSTAINABILITY | AGM_NOTICE
    fiscal_year     INTEGER,
    quarter         VARCHAR(10),
    title           TEXT NOT NULL,
    source_url      TEXT,
    object_store_key TEXT,
    page_count      INTEGER,
    file_size_bytes BIGINT,
    processing_status VARCHAR(20) DEFAULT 'PENDING',
    published_date  DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE investor_doc_analysis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES investor_documents(id),
    strategic_priorities JSONB,   -- [{priority, description}]
    key_metrics     JSONB,        -- {revenue_cagr_3y, roe, roce, debt_equity, ...}
    management_vision TEXT,
    competitive_advantages TEXT[],
    growth_drivers  TEXT[],
    risk_factors    TEXT[],
    capital_allocation TEXT,      -- dividend policy, buybacks, capex plans
    esg_highlights  JSONB,
    executive_summary TEXT,
    notable_charts  JSONB,        -- extracted chart data where possible
    model_version   VARCHAR(50),
    processed_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE investor_doc_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES investor_documents(id),
    page_number     INTEGER NOT NULL,
    text_content    TEXT,
    tables          JSONB,   -- extracted tables as JSON
    has_charts      BOOLEAN DEFAULT FALSE,
    embedding       vector(768)
);
CREATE INDEX idx_investor_doc_pages_doc ON investor_doc_pages(document_id);
CREATE INDEX idx_investor_doc_pages_embedding ON investor_doc_pages
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### APIs

```
GET  /api/v1/presentations/instrument/{isin}
     → list of all documents for a company

GET  /api/v1/presentations/{id}
     → document metadata + analysis

POST /api/v1/presentations/{id}/ask
     body: { question: string }
     → RAG over the document

GET  /api/v1/presentations/compare
     ?isin=&year1=&year2=
     → year-on-year strategy comparison

POST /api/v1/presentations/upload
     → manual upload for any company
```

### Update Schedule

- `scan_annual_reports`: `0 9 * * 1-5` (daily check post filing season)
- `process_document`: triggered on new document detected

### Workflow

```
1. Detect new annual report on NSE/BSE or company IR page
2. Download to Oracle Object Store
3. Page-by-page extraction:
   a. Text via pdfplumber
   b. Tables via camelot-py
   c. Charts: detect with image analysis; extract metadata
4. Batch embedding (50 pages per API call)
5. Whole-document AI analysis (Gemini 1.5 Pro)
6. Store in investor_doc_analysis
7. Publish to stream:fundamentals_updated
```

---

## Worker 05 — Fundamental Worker

### Purpose
Maintains a structured financial model for every tracked stock: P&L, balance sheet, cash flow, key ratios, and management quality scores. The single source of truth for financial data.

### Data Sources
- BSE/NSE quarterly results (XBRL + PDF)
- Screener.in API (if licensed)
- Manual financial data entry
- Investor Presentation Worker (parsed tables)

### Database Schema

```sql
CREATE TABLE financial_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    period_type     VARCHAR(10) NOT NULL,  -- QUARTERLY | ANNUAL | TTM
    fiscal_year     INTEGER NOT NULL,
    quarter         VARCHAR(10),  -- Q1, Q2, Q3, Q4 (null for annual)
    period_end_date DATE NOT NULL,
    is_consolidated BOOLEAN DEFAULT TRUE,
    is_audited      BOOLEAN DEFAULT FALSE,
    source          VARCHAR(50),

    -- P&L (in ₹ Lakhs)
    revenue         NUMERIC(20,4),
    revenue_growth_yoy NUMERIC(8,4),
    gross_profit    NUMERIC(20,4),
    gross_margin    NUMERIC(8,4),
    ebitda          NUMERIC(20,4),
    ebitda_margin   NUMERIC(8,4),
    depreciation    NUMERIC(20,4),
    ebit            NUMERIC(20,4),
    interest        NUMERIC(20,4),
    pbt             NUMERIC(20,4),
    tax             NUMERIC(20,4),
    pat             NUMERIC(20,4),
    pat_margin      NUMERIC(8,4),
    eps             NUMERIC(12,4),
    eps_diluted     NUMERIC(12,4),

    -- Balance Sheet
    total_assets    NUMERIC(20,4),
    total_equity    NUMERIC(20,4),
    total_debt      NUMERIC(20,4),
    net_debt        NUMERIC(20,4),
    cash_equivalents NUMERIC(20,4),
    inventory       NUMERIC(20,4),
    receivables     NUMERIC(20,4),
    payables        NUMERIC(20,4),
    fixed_assets    NUMERIC(20,4),

    -- Cash Flow
    cfo             NUMERIC(20,4),
    cfi             NUMERIC(20,4),
    cff             NUMERIC(20,4),
    free_cash_flow  NUMERIC(20,4),
    capex           NUMERIC(20,4),

    -- Ratios
    roe             NUMERIC(8,4),
    roce            NUMERIC(8,4),
    roa             NUMERIC(8,4),
    debt_equity     NUMERIC(8,4),
    current_ratio   NUMERIC(8,4),
    inventory_days  NUMERIC(8,2),
    debtor_days     NUMERIC(8,2),
    creditor_days   NUMERIC(8,2),
    cash_conversion_cycle NUMERIC(8,2),
    interest_coverage NUMERIC(8,4),
    asset_turnover  NUMERIC(8,4),

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_period UNIQUE (instrument_id, period_type, fiscal_year, quarter, is_consolidated)
);
CREATE INDEX idx_financial_results_instrument ON financial_results(instrument_id, period_end_date DESC);

CREATE TABLE fundamental_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id) UNIQUE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    -- Piotroski F-Score
    piotroski_score SMALLINT,
    piotroski_detail JSONB,
    -- Altman Z-Score
    altman_z_score  NUMERIC(8,4),
    altman_category VARCHAR(20),   -- SAFE | GREY | DISTRESS
    -- Growth Scores
    revenue_cagr_3y NUMERIC(8,4),
    revenue_cagr_5y NUMERIC(8,4),
    pat_cagr_3y     NUMERIC(8,4),
    pat_cagr_5y     NUMERIC(8,4),
    eps_cagr_5y     NUMERIC(8,4),
    -- Quality Score (composite)
    quality_score   NUMERIC(5,2),  -- 0-100
    quality_rank    INTEGER,       -- rank within sector
    -- AI Narrative
    fundamental_thesis TEXT,
    concerns        TEXT[],
    model_version   VARCHAR(50)
);

CREATE TABLE shareholding_pattern (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    quarter         VARCHAR(10) NOT NULL,
    promoter_pct    NUMERIC(6,3),
    promoter_pledge_pct NUMERIC(6,3),
    dii_pct         NUMERIC(6,3),
    fii_pct         NUMERIC(6,3),
    public_pct      NUMERIC(6,3),
    top10_pct       NUMERIC(6,3),
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_quarter_sh UNIQUE (instrument_id, quarter)
);
```

### APIs

```
GET  /api/v1/fundamentals/{isin}/summary
     → latest quarter snapshot + trend arrows

GET  /api/v1/fundamentals/{isin}/financials
     ?period_type=QUARTERLY&from_year=&to_year=&consolidated=true
     → time-series financial data (for charts)

GET  /api/v1/fundamentals/{isin}/scores
     → Piotroski, Altman-Z, quality score

GET  /api/v1/fundamentals/{isin}/shareholding
     → shareholding pattern last 8 quarters

GET  /api/v1/fundamentals/screen
     body: { filters: { roe_min: 15, debt_equity_max: 1, ... } }
     → stock screener returning matching ISINs

GET  /api/v1/fundamentals/sector/{sector}/compare
     → peer comparison table
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `fetch_quarterly_results` | `0 18 * * 1-5` | Post-market, pick up day's results |
| `fetch_annual_results` | `0 9 1 5,8 *` | May & Aug (FY end results season) |
| `recompute_ratios` | After results | Triggered by new financial_results insert |
| `recompute_scores` | `0 2 * * *` | Nightly rebuild of all scores |
| `fetch_shareholding` | `0 10 20 1,4,7,10 *` | Quarterly (post filing deadline) |

---

## Worker 06 — Technical Worker

### Purpose
Maintains real-time and historical OHLCV data for all tracked instruments. Computes technical indicators, generates chart signals, and provides the price feed consumed by all other workers.

### Data Sources
- Zerodha Kite Historical Data API (via MCP)
- NSE EOD data (direct download)
- Real-time LTP via Kite get_ltp / get_ohlc

### Database Schema

```sql
-- Partitioned by month for performance
CREATE TABLE ohlcv_daily (
    id              UUID DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    date            DATE NOT NULL,
    open            NUMERIC(12,4) NOT NULL,
    high            NUMERIC(12,4) NOT NULL,
    low             NUMERIC(12,4) NOT NULL,
    close           NUMERIC(12,4) NOT NULL,
    volume          BIGINT NOT NULL,
    oi              BIGINT DEFAULT 0,  -- open interest (F&O)
    adjusted_close  NUMERIC(12,4),
    PRIMARY KEY (instrument_id, date)
) PARTITION BY RANGE (date);

CREATE TABLE ohlcv_intraday (
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    ts              TIMESTAMPTZ NOT NULL,
    interval        VARCHAR(5) NOT NULL,   -- 1m, 5m, 15m, 1h
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    close           NUMERIC(12,4),
    volume          BIGINT,
    PRIMARY KEY (instrument_id, ts, interval)
) PARTITION BY RANGE (ts);

CREATE TABLE technical_indicators (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    date            DATE NOT NULL,
    -- Moving Averages
    sma_20          NUMERIC(12,4),
    sma_50          NUMERIC(12,4),
    sma_200         NUMERIC(12,4),
    ema_9           NUMERIC(12,4),
    ema_21          NUMERIC(12,4),
    ema_50          NUMERIC(12,4),
    -- Momentum
    rsi_14          NUMERIC(6,3),
    macd_line       NUMERIC(10,4),
    macd_signal     NUMERIC(10,4),
    macd_histogram  NUMERIC(10,4),
    -- Volatility
    bb_upper        NUMERIC(12,4),
    bb_middle       NUMERIC(12,4),
    bb_lower        NUMERIC(12,4),
    atr_14          NUMERIC(10,4),
    -- Volume
    obv             BIGINT,
    vwap            NUMERIC(12,4),
    -- Trend
    adx_14          NUMERIC(6,3),
    stochastic_k    NUMERIC(6,3),
    stochastic_d    NUMERIC(6,3),
    supertrend      NUMERIC(12,4),
    supertrend_direction SMALLINT,   -- 1 up, -1 down
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_date_ti UNIQUE (instrument_id, date)
);
CREATE INDEX idx_ti_instrument_date ON technical_indicators(instrument_id, date DESC);

CREATE TABLE technical_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    signal_date     DATE NOT NULL,
    signal_type     VARCHAR(50) NOT NULL,
    -- GOLDEN_CROSS | DEATH_CROSS | RSI_OVERSOLD | RSI_OVERBOUGHT
    -- MACD_BULLISH_CROSS | BREAKOUT | BREAKDOWN | 52W_HIGH | 52W_LOW
    direction       VARCHAR(5),   -- BUY | SELL | NEUTRAL
    strength        VARCHAR(10),  -- STRONG | MODERATE | WEAK
    description     TEXT,
    price_at_signal NUMERIC(12,4),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_signals_instrument ON technical_signals(instrument_id, signal_date DESC);

-- Live price cache (Redis-first, PG as backup)
CREATE TABLE price_snapshots (
    instrument_id   UUID NOT NULL REFERENCES instruments(id) PRIMARY KEY,
    ltp             NUMERIC(12,4),
    change          NUMERIC(10,4),
    change_pct      NUMERIC(8,4),
    volume          BIGINT,
    high_52w        NUMERIC(12,4),
    low_52w         NUMERIC(12,4),
    updated_at      TIMESTAMPTZ
);
```

### APIs

```
GET  /api/v1/technical/{isin}/price
     → live price snapshot

GET  /api/v1/technical/{isin}/ohlcv
     ?interval=1d&from=&to=
     → OHLCV time series for charting

GET  /api/v1/technical/{isin}/indicators
     ?date=
     → all indicators for latest/given date

GET  /api/v1/technical/{isin}/signals
     ?from=&limit=20
     → recent buy/sell signals

GET  /api/v1/technical/{isin}/chart-data
     → combined OHLCV + indicators for chart widget

POST /api/v1/technical/screener
     body: { filters: { rsi_max: 30, above_200dma: true, ... } }
     → technical screener

WebSocket /ws/technical/prices
     body: { isins: ["INE...", ...] }
     → live price updates for subscribed instruments
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `fetch_live_prices` | `*/1 * * * 1-5` (09:00-15:35) | LTP for all watchlist stocks |
| `fetch_intraday_ohlcv` | `*/5 * * * 1-5` | 5-min candles |
| `fetch_eod_ohlcv` | `30 15 * * 1-5` | EOD candle after market close |
| `compute_indicators` | `0 16 * * 1-5` | All indicators from EOD data |
| `detect_signals` | `15 16 * * 1-5` | Signal scan after indicators |
| `backfill_history` | `0 3 * * 6` | Saturday — fill any gaps |

### Edge Cases

- **Exchange holidays**: skip fetch; mark in calendar table
- **Circuit breaker / trading halt**: detect 0-volume candle; flag in signals
- **Adjusted prices for splits/bonuses**: maintain both raw and adjusted close
- **Instrument delisting**: mark instrument as inactive; preserve history
- **Futures & Options**: separate OI tracking; distinguish from equity

---

## Worker 07 — Valuation Worker

### Purpose
Computes intrinsic value estimates using multiple methodologies and generates a unified fair value range. Maintained per-stock and updated whenever fundamentals or market data changes.

### Database Schema

```sql
CREATE TABLE valuations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    valuation_date  DATE NOT NULL,
    current_price   NUMERIC(12,4) NOT NULL,

    -- DCF Valuation
    dcf_fair_value  NUMERIC(12,4),
    dcf_assumptions JSONB,  -- {wacc, terminal_growth, fcf_base, projection_years}
    dcf_bull        NUMERIC(12,4),
    dcf_bear        NUMERIC(12,4),

    -- Peer Multiple Valuation
    peer_pe_avg     NUMERIC(8,4),
    peer_pb_avg     NUMERIC(8,4),
    peer_ev_ebitda_avg NUMERIC(8,4),
    pe_based_value  NUMERIC(12,4),
    pb_based_value  NUMERIC(12,4),
    ev_ebitda_value NUMERIC(12,4),

    -- Graham Number
    graham_number   NUMERIC(12,4),

    -- PEG Ratio
    peg_ratio       NUMERIC(8,4),
    peg_based_value NUMERIC(12,4),

    -- Price targets from analyst estimates (if available)
    analyst_consensus_target NUMERIC(12,4),
    analyst_count   SMALLINT,

    -- Blended Fair Value
    fair_value_low  NUMERIC(12,4),
    fair_value_mid  NUMERIC(12,4),
    fair_value_high NUMERIC(12,4),
    upside_pct      NUMERIC(8,4),
    rating          VARCHAR(20),   -- STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL

    -- AI narrative
    valuation_thesis TEXT,
    key_assumptions TEXT[],
    sensitivity_table JSONB,
    model_version   VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_valdate UNIQUE (instrument_id, valuation_date)
);

CREATE TABLE peer_groups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    peer_id         UUID NOT NULL REFERENCES instruments(id),
    group_basis     VARCHAR(50),   -- SECTOR | MANUAL | AI_SUGGESTED
    weight          NUMERIC(5,4) DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_peer UNIQUE (instrument_id, peer_id)
);

CREATE TABLE valuation_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    date            DATE NOT NULL,
    pe_ttm          NUMERIC(8,4),
    pb              NUMERIC(8,4),
    ps              NUMERIC(8,4),
    ev_ebitda       NUMERIC(8,4),
    market_cap      NUMERIC(20,4),
    enterprise_value NUMERIC(20,4),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_date_vh UNIQUE (instrument_id, date)
);
```

### APIs

```
GET  /api/v1/valuation/{isin}
     → latest valuation with all models + rating

GET  /api/v1/valuation/{isin}/history
     ?from=&to=
     → historical PE/PB band chart data

GET  /api/v1/valuation/{isin}/peers
     → peer comparison table with multiples

GET  /api/v1/valuation/{isin}/dcf
     → DCF model detail with sensitivity table

POST /api/v1/valuation/{isin}/dcf/scenario
     body: { wacc, growth_rate, terminal_growth }
     → on-the-fly DCF with custom assumptions

GET  /api/v1/valuation/sector/{sector}/multiples
     → current average multiples by sector
```

### Update Schedule

| Job | Trigger / Cron | Description |
|---|---|---|
| `recompute_valuation` | On fundamentals_updated event | Immediate recompute after new results |
| `update_market_multiples` | `0 16 * * 1-5` | Daily after market close |
| `rebuild_peer_groups` | `0 3 * * 0` | Weekly AI-assisted peer grouping |
| `generate_valuation_thesis` | After recompute | LLM narrative generation |

---

## Worker 08 — Master Tracker Worker

### Purpose
Aggregates signals from all workers into a single investable "Master View" per stock: a one-stop scorecard showing technical posture, fundamental quality, valuation gap, recent news sentiment, and concall tone.

### Database Schema

```sql
CREATE TABLE master_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id) UNIQUE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Composite Scores (0-100)
    overall_score   NUMERIC(5,2),
    technical_score NUMERIC(5,2),
    fundamental_score NUMERIC(5,2),
    valuation_score NUMERIC(5,2),   -- 100 = deeply undervalued
    sentiment_score NUMERIC(5,2),   -- news + concall tone
    momentum_score  NUMERIC(5,2),

    -- Ratings
    technical_rating VARCHAR(20),    -- STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
    fundamental_rating VARCHAR(20),
    valuation_rating VARCHAR(20),
    overall_rating  VARCHAR(20),

    -- Flags
    is_watchlist    BOOLEAN DEFAULT FALSE,
    is_in_portfolio BOOLEAN DEFAULT FALSE,
    has_active_alert BOOLEAN DEFAULT FALSE,

    -- Snapshot values
    current_price   NUMERIC(12,4),
    fair_value_mid  NUMERIC(12,4),
    upside_pct      NUMERIC(8,4),
    pe_ttm          NUMERIC(8,4),
    eps_cagr_3y     NUMERIC(8,4),
    rsi_14          NUMERIC(6,3),
    latest_news_sentiment VARCHAR(10),
    concall_tone    VARCHAR(20),

    -- AI one-liner
    ai_thesis       TEXT,
    last_concall_quarter VARCHAR(10),
    last_result_quarter VARCHAR(10)
);
CREATE INDEX idx_master_scores_overall ON master_scores(overall_score DESC);
CREATE INDEX idx_master_scores_watchlist ON master_scores(is_watchlist) WHERE is_watchlist = TRUE;

CREATE TABLE watchlists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    is_default      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE watchlist_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id    UUID NOT NULL REFERENCES watchlists(id),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    notes           TEXT,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_watchlist_instrument UNIQUE (watchlist_id, instrument_id)
);

CREATE TABLE research_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    instrument_id   UUID REFERENCES instruments(id),
    title           VARCHAR(255),
    content         TEXT,
    tags            TEXT[],
    linked_concall_id UUID REFERENCES concalls(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### APIs

```
GET  /api/v1/tracker/scorecard/{isin}
     → full master scorecard for a stock

GET  /api/v1/tracker/watchlist
     ?watchlist_id=
     → all stocks in watchlist with scores

GET  /api/v1/tracker/universe/top
     ?sort_by=overall_score&limit=50
     → top stocks by composite score

POST /api/v1/tracker/watchlist/add
     body: { isin, watchlist_id, notes }

POST /api/v1/tracker/notes
     → save research note

GET  /api/v1/tracker/compare
     ?isins=INE1,INE2,INE3
     → side-by-side scorecard comparison
```

### Update Schedule

| Job | Trigger | Description |
|---|---|---|
| `rebuild_master_score` | Any worker emits domain event | Near-real-time score refresh |
| `full_universe_rebuild` | `0 17 * * 1-5` | Nightly full rebuild |
| `generate_ai_thesis` | After score rebuild | LLM one-liner per stock |

### Workflow

```
1. Subscribe to all domain event streams
2. On event for instrument X:
   a. Fetch latest scores from each worker's Redis cache
   b. Apply weighted average:
      overall = 0.25*fundamental + 0.20*technical + 0.20*valuation
              + 0.20*sentiment   + 0.15*momentum
   c. Generate rating thresholds:
      ≥80: STRONG_BUY, ≥65: BUY, ≥50: HOLD, ≥35: SELL, <35: STRONG_SELL
   d. Upsert master_scores
   e. If score changed significantly (>5 pts), trigger Alert Worker check
```

---

## Worker 09 — Mutual Fund Worker

### Purpose
Tracks institutional MF ownership of stocks: which funds hold a position, historical changes in MF ownership, inflows/outflows, and identifies stocks with rising MF interest (smart money signal).

### Data Sources
- AMFI monthly portfolio disclosures
- SEBI MF data (mfindiaapi.com / AMFI official)
- NSDL/CDSL for consolidated ownership data

### Database Schema

```sql
CREATE TABLE mutual_funds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    amfi_code       VARCHAR(20) UNIQUE NOT NULL,
    scheme_name     TEXT NOT NULL,
    fund_house      VARCHAR(100) NOT NULL,
    category        VARCHAR(50),
    -- LARGE_CAP | MID_CAP | SMALL_CAP | FLEXI_CAP | SECTORAL | THEMATIC
    sub_category    VARCHAR(100),
    aum_crores      NUMERIC(15,2),
    nav             NUMERIC(12,4),
    nav_date        DATE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE mf_holdings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fund_id         UUID NOT NULL REFERENCES mutual_funds(id),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    month_year      VARCHAR(10) NOT NULL,   -- 2025-06
    shares_held     BIGINT,
    market_value_crores NUMERIC(15,4),
    pct_of_nav      NUMERIC(8,4),
    pct_of_equity_aum NUMERIC(8,4),
    change_in_shares BIGINT,   -- vs previous month
    is_new_entry    BOOLEAN DEFAULT FALSE,
    is_exit         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_fund_instrument_month UNIQUE (fund_id, instrument_id, month_year)
);
CREATE INDEX idx_mf_holdings_instrument ON mf_holdings(instrument_id, month_year DESC);
CREATE INDEX idx_mf_holdings_fund ON mf_holdings(fund_id, month_year DESC);

CREATE TABLE mf_stock_summary (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    month_year      VARCHAR(10) NOT NULL,
    total_funds_holding INTEGER DEFAULT 0,
    total_shares_held BIGINT DEFAULT 0,
    total_value_crores NUMERIC(15,4) DEFAULT 0,
    pct_of_free_float NUMERIC(8,4),
    new_entries     INTEGER DEFAULT 0,
    exits           INTEGER DEFAULT 0,
    net_change_shares BIGINT DEFAULT 0,
    category_breakdown JSONB,   -- {LARGE_CAP: 5, MID_CAP: 3, ...}
    top_holders     JSONB,      -- [{fund_name, pct_nav}] top 5
    smart_money_score NUMERIC(5,2),  -- rising MF interest score
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument_month_mf UNIQUE (instrument_id, month_year)
);

CREATE TABLE mf_flows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month_year      VARCHAR(10) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    gross_purchase_crores NUMERIC(15,4),
    gross_redemption_crores NUMERIC(15,4),
    net_flow_crores NUMERIC(15,4),
    total_aum_crores NUMERIC(20,4),
    folio_count     BIGINT,
    sip_amount_crores NUMERIC(15,4),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_month_category_flows UNIQUE (month_year, category)
);
```

### APIs

```
GET  /api/v1/mf/stock/{isin}
     → MF ownership summary + trend for a stock

GET  /api/v1/mf/stock/{isin}/holders
     ?month=2025-06&category=
     → which funds hold this stock

GET  /api/v1/mf/stock/{isin}/changes
     → month-on-month change in MF positions

GET  /api/v1/mf/fund/{amfi_code}/holdings
     ?month=
     → all holdings of a specific fund

GET  /api/v1/mf/screens/rising-interest
     → stocks with increasing MF buying (smart money)

GET  /api/v1/mf/screens/new-entries
     ?month=
     → stocks newly added by major funds

GET  /api/v1/mf/flows
     → monthly category-wise AUM and flow data
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `download_amfi_portfolios` | `0 8 10 * *` | 10th of each month (AMFI release) |
| `parse_mf_portfolios` | Triggered | Parse downloaded XLSX/JSON |
| `build_stock_summaries` | After parse | Aggregate per-stock MF data |
| `compute_smart_money_score` | After summaries | Trend scoring |
| `fetch_mf_flows` | `0 9 15 * *` | 15th monthly flows report |

---

## Worker 10 — Alert Worker

### Purpose
The real-time watchdog. Evaluates user-defined and system-generated alert conditions across all data streams and delivers multi-channel notifications instantly.

### Database Schema

```sql
CREATE TABLE alert_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(255) NOT NULL,
    instrument_id   UUID REFERENCES instruments(id),   -- null = market-wide
    alert_type      VARCHAR(50) NOT NULL,
    -- PRICE_TARGET | PRICE_DROP | RSI_LEVEL | VOLUME_SPIKE | NEWS_SENTIMENT
    -- RESULT_OUT | CONCALL_DONE | MF_ENTRY | SCORE_CHANGE | PORTFOLIO_PNL
    condition_params JSONB NOT NULL,   -- {"operator": ">=", "value": 1000}
    notification_channels TEXT[],     -- EMAIL | PUSH | WEBSOCKET
    is_active       BOOLEAN DEFAULT TRUE,
    repeat_interval_min INTEGER,      -- null = fire once; int = minimum minutes between fires
    last_triggered_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_alert_rules_user ON alert_rules(user_id);
CREATE INDEX idx_alert_rules_instrument ON alert_rules(instrument_id) WHERE instrument_id IS NOT NULL;

CREATE TABLE alert_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id         UUID NOT NULL REFERENCES alert_rules(id),
    instrument_id   UUID REFERENCES instruments(id),
    triggered_at    TIMESTAMPTZ DEFAULT NOW(),
    trigger_value   JSONB,    -- actual value that triggered the alert
    message         TEXT NOT NULL,
    is_read         BOOLEAN DEFAULT FALSE,
    notification_status JSONB,  -- {email: SENT|FAILED, push: SENT|FAILED}
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_alert_events_user ON alert_events(rule_id);
CREATE INDEX idx_alert_events_triggered ON alert_events(triggered_at DESC);

CREATE TABLE notification_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) UNIQUE,
    email_enabled   BOOLEAN DEFAULT TRUE,
    push_enabled    BOOLEAN DEFAULT TRUE,
    quiet_hours_start TIME,
    quiet_hours_end  TIME,
    daily_digest_time TIME DEFAULT '08:00',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### Alert Types and Evaluation Logic

| Alert Type | Trigger Condition | Data Source |
|---|---|---|
| PRICE_TARGET | LTP crosses target price | Technical Worker stream |
| RSI_LEVEL | RSI crosses threshold | Technical Worker stream |
| VOLUME_SPIKE | Volume > N× 30-day avg | Technical Worker stream |
| NEWS_SENTIMENT | Major negative/positive news | News Worker stream |
| RESULT_OUT | Quarterly result filing detected | News Worker stream |
| SCORE_CHANGE | Master score moves >5 pts | Master Tracker stream |
| PORTFOLIO_PNL | Portfolio P&L crosses threshold | Order Worker stream |
| MF_ENTRY | Fund newly enters a position | MF Worker stream |
| CONCALL_DONE | Concall processed; tone bearish | Concall Worker stream |

### APIs

```
GET  /api/v1/alerts/rules
     → list user's alert rules

POST /api/v1/alerts/rules
     body: { alert_type, instrument_id, condition_params, channels }

PUT  /api/v1/alerts/rules/{id}

DELETE /api/v1/alerts/rules/{id}

GET  /api/v1/alerts/events
     ?is_read=false&from=&limit=
     → alert history

POST /api/v1/alerts/events/{id}/read
     → mark as read

WebSocket /ws/alerts/live
     → real-time alert push to UI
```

### Update Schedule / Execution Model

Alert Worker is **event-driven** (not cron):
```
Redis Stream consumers for each domain:
  - stream:news → evaluate NEWS_SENTIMENT rules
  - stream:price_tick → evaluate PRICE_TARGET, RSI_LEVEL, VOLUME_SPIKE
  - stream:order_executed → evaluate PORTFOLIO_PNL rules
  - stream:concall_processed → evaluate CONCALL_DONE rules
  - stream:fundamentals_updated → trigger RESULT_OUT
  - stream:mf_updated → evaluate MF_ENTRY rules
  - stream:alert_triggered → consumed by Dashboard Worker
```

Delivery: `0 8 * * 1-5` daily digest email summarising all alerts.

### Edge Cases

- **Alert storm prevention**: de-duplicate within `repeat_interval_min` window
- **Quiet hours**: check notification_preferences before sending push/email
- **Market closed**: suppress price alerts; queue for next open
- **Alert rule backtest**: `/api/v1/alerts/rules/{id}/backtest` — show when it would have fired historically

---

## Worker 11 — Dashboard Worker

### Purpose
A data aggregation and pre-computation layer that powers the Next.js frontend. Pre-builds expensive views into Redis so the UI is always sub-100ms. Also generates AI-written morning briefings and portfolio digests.

### Database Schema

```sql
CREATE TABLE dashboard_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    snapshot_type   VARCHAR(50) NOT NULL,
    -- PORTFOLIO_SUMMARY | WATCHLIST_OVERVIEW | MARKET_HEATMAP | MORNING_BRIEF
    payload         JSONB NOT NULL,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    valid_until     TIMESTAMPTZ,
    CONSTRAINT uq_user_snapshot_type UNIQUE (user_id, snapshot_type)
);

CREATE TABLE market_overview (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL UNIQUE,
    nifty50_close   NUMERIC(10,4),
    nifty50_change_pct NUMERIC(8,4),
    sensex_close    NUMERIC(10,4),
    sensex_change_pct NUMERIC(8,4),
    advance_decline_ratio NUMERIC(8,4),
    market_breadth  JSONB,
    sector_performance JSONB,   -- [{sector, change_pct}]
    top_gainers     JSONB,
    top_losers      JSONB,
    most_active     JSONB,
    fii_net_flow    NUMERIC(15,4),
    dii_net_flow    NUMERIC(15,4),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE morning_briefs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    brief_date      DATE NOT NULL,
    content         TEXT NOT NULL,   -- AI-generated markdown
    key_events      JSONB,
    stocks_to_watch JSONB,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_brief_date UNIQUE (user_id, brief_date)
);
```

### APIs

```
GET  /api/v1/dashboard/summary
     → portfolio P&L + watchlist movers + unread alerts (cached)

GET  /api/v1/dashboard/market
     → market-wide overview (indices, breadth, sector heatmap)

GET  /api/v1/dashboard/morning-brief
     → today's AI-written morning brief for the user

GET  /api/v1/dashboard/heatmap
     ?universe=NIFTY500&metric=change_pct
     → treemap data (market cap weighted)

WebSocket /ws/dashboard/live
     → multiplex feed: prices + alerts + news for UI
```

### Update Schedule

| Job | Cron | Description |
|---|---|---|
| `build_market_overview` | `30 15 * * 1-5` | Post close |
| `generate_morning_brief` | `0 7 * * 1-5` | 7 AM IST for each user |
| `refresh_portfolio_cache` | On order_executed event | Instant cache invalidation |
| `refresh_watchlist_cache` | On price_tick + news events | Every 60s |

### Morning Brief Generation Workflow

```
1. Gather context for the user:
   a. Portfolio P&L status (yesterday close vs today pre-open if available)
   b. Last 24h news for watchlist stocks
   c. Any alert events fired overnight
   d. Key market events (results schedule, AGMs, F&O expiry)
   e. Technical signals fired yesterday
   f. Global market context (crude, USD/INR, Nifty futures)
2. Send structured context to Gemini 1.5 Pro
3. Generate 300-word briefing in markdown
4. Store in morning_briefs table
5. Deliver via WebSocket on user login + email at 8 AM
```

---

## 17. Inter-Worker Communication Map

```
┌──────────────┐     stream:news          ┌─────────────┐
│  News Worker │──────────────────────────▶ Alert Worker │
└──────┬───────┘                           └──────┬──────┘
       │                                          │ stream:alert_triggered
       │ stream:news                              ▼
       ▼                              ┌────────────────────┐
┌──────────────┐                      │  Dashboard Worker  │
│Master Tracker│◀──────────────────── └────────────────────┘
└──────┬───────┘   stream:concall_processed  ▲
       │           stream:fundamentals_updated │
       │                                       │
┌──────▼────────┐                    ┌─────────┴──────┐
│Valuation Wrkr │──────────────────▶ │Fundamental Wrkr│
└───────────────┘   triggers          └────────────────┘
                    recompute                 ▲
                                    ┌─────────┴──────┐
                                    │Investor Pres.  │
                                    └────────────────┘

┌──────────────┐  stream:price_tick  ┌─────────────┐
│Technical Wrkr│────────────────────▶│ Alert Worker│
└──────────────┘                      └─────────────┘

┌──────────────┐  stream:order_executed ┌────────────┐
│ Order Worker │──────────────────────▶│ Alert Wrkr │
└──────────────┘                        └────────────┘

┌──────────────┐  stream:mf_updated  ┌──────────────┐
│  MF Worker   │────────────────────▶│Master Tracker│
└──────────────┘                      └──────────────┘
```

---

## 18. Deployment Architecture

### Directory Structure

```
/
├── frontend/                    # Next.js 15 app
│   ├── app/                     # App Router
│   │   ├── (auth)/
│   │   ├── dashboard/
│   │   ├── stocks/[isin]/
│   │   ├── portfolio/
│   │   └── alerts/
│   ├── components/
│   │   ├── ui/                  # shadcn components
│   │   ├── charts/
│   │   └── workers/             # per-worker UI components
│   └── lib/
│       ├── api.ts               # typed API client
│       └── ws.ts                # WebSocket manager
│
├── backend/
│   ├── main.py                  # FastAPI app factory
│   ├── core/                    # auth, config, db, redis
│   ├── workers/
│   │   ├── news/
│   │   │   ├── models.py
│   │   │   ├── router.py
│   │   │   ├── tasks.py
│   │   │   └── service.py
│   │   ├── orders/
│   │   ├── concall/
│   │   ├── investor_pres/
│   │   ├── fundamental/
│   │   ├── technical/
│   │   ├── valuation/
│   │   ├── master_tracker/
│   │   ├── mutual_fund/
│   │   ├── alerts/
│   │   └── dashboard/
│   ├── shared/
│   │   ├── instruments.py
│   │   ├── llm.py               # Gemini client wrapper
│   │   └── events.py            # Redis Stream helpers
│   └── alembic/                 # DB migrations
│
├── infra/
│   ├── docker-compose.yml       # local dev
│   ├── k8s/                     # OKE manifests
│   └── cloudflare/              # Workers, R2, DNS config
│
└── .github/workflows/
    ├── ci.yml
    └── deploy.yml
```

### CI/CD Pipeline

```
Push to main →
  GitHub Actions:
    1. Lint (ruff, eslint)
    2. Type check (mypy, tsc)
    3. Unit tests (pytest, jest)
    4. Build Docker images
    5. Push to Oracle Container Registry
    6. kubectl rollout restart (OKE)
    7. Run DB migrations (alembic upgrade head)
    8. Smoke test (k6 / httpx)
```

### Oracle Cloud Resources

| Resource | Spec | Purpose |
|---|---|---|
| VM.Standard.A1.Flex (API) | 4 OCPU, 24 GB | FastAPI + Celery workers |
| VM.Standard.A1.Flex (DB) | 2 OCPU, 12 GB | PostgreSQL 16 |
| VM.Standard.A1.Flex (Cache) | 1 OCPU, 6 GB | Redis 7 |
| Object Storage | Pay per GB | PDFs, audio, backups |
| Load Balancer | 10 Mbps | Distribute API traffic |

---

## 19. Security Architecture

- **Transport**: TLS 1.3 everywhere; HSTS enforced via Cloudflare
- **Auth**: JWT (RS256); tokens never stored in localStorage (httpOnly cookies)
- **API keys** (Kite, Gemini): stored in Oracle Vault; injected as environment variables at runtime; never in git
- **Database**: no direct internet exposure; accessible only via private OCI VCN subnet
- **Rate limiting**: Cloudflare WAF (per-IP) + FastAPI middleware (per-user)
- **Input validation**: Pydantic v2 models on all request bodies
- **SQL injection**: SQLAlchemy parameterised queries only; no raw string interpolation
- **LLM prompt injection**: all user-supplied text sandwiched between system instructions with clear delimiters; output validated before DB write
- **Audit log**: all write operations logged to `audit_log` table (user_id, action, before/after JSON, IP, timestamp)

---

## 20. Scalability Roadmap

### Phase 1 (MVP — single Oracle VM)
- All services on one machine via Docker Compose
- Nifty 200 universe
- Polling-based price updates (1-min interval)

### Phase 2 (Growth — multi-node)
- Separate VMs for DB, Redis, API, Celery
- Add read replica for PostgreSQL (reporting queries)
- Celery workers scaled independently per worker type
- Nifty 500 universe

### Phase 3 (Scale — OKE Kubernetes)
- Stateless FastAPI pods: HPA on CPU
- Celery workers: KEDA-based autoscaling on Redis queue depth
- PostgreSQL: TimescaleDB for `ohlcv_*` tables (hypertables)
- Redis Cluster (3 primary + 3 replica)
- Full NSE/BSE universe (~5,000 instruments)
- WebSocket: replace with Cloudflare Durable Objects for global pub/sub

### Performance Targets
| Metric | Target |
|---|---|
| API P95 latency | < 100ms (cached) / < 500ms (DB hit) |
| Dashboard load | < 1.5s (LCP) |
| Price update lag | < 2s during market hours |
| Alert delivery | < 5s from trigger event |
| News processing | < 3 min from exchange filing |
| Concall processing | < 15 min from PDF available |

---

*End of Architecture Document — v1.0*
*Next step: scaffold the monorepo, implement shared core (auth, DB, Redis), then build Worker 01 and Worker 06 as the data foundation before all other workers.*

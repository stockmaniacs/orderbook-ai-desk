"""
Orderbook AI Desk — FastAPI entry point.
Start with: uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# ── Routers ───────────────────────────────────────────────────────────────────
from workers.order_tracking.router import router as order_router
from workers.company_research.router import router as research_router
from workers.subcontract_opportunity.router import router as subcontract_router
from workers.master_tracker.router import router as tracker_router
from workers.technical_analysis.router import router as technical_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing needed — Alembic handles migrations separately
    yield
    # Shutdown


app = FastAPI(
    title="Orderbook AI Desk",
    description="AI-powered investment research platform for NSE/BSE universe",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(order_router,      prefix="/api/v1/orders",     tags=["Orders"])
app.include_router(research_router,   prefix="/api/v1/research",   tags=["Research"])
app.include_router(subcontract_router,prefix="/api/v1/subcontract",tags=["Subcontract"])
app.include_router(tracker_router,    prefix="/api/v1/tracker",    tags=["Master Tracker"])
app.include_router(technical_router,  prefix="/api/v1/technical",  tags=["Technical"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "orderbook-ai-desk"}

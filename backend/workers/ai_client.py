"""
Shared OpenRouter AI client for all workers.
OpenRouter exposes an OpenAI-compatible API — no vendor-specific SDK needed.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

_HEADERS = {
    "Content-Type": "application/json",
    "HTTP-Referer": "https://orderbook-ai-desk.pages.dev",
    "X-Title": "Orderbook AI Desk",
}

# ─── Model tiers ──────────────────────────────────────────────────────────────
# Fast: extraction, classification, quick summaries
MODEL_FAST = "meta-llama/llama-3.3-70b-instruct:free"
# Deep: investment thesis, complex relationship extraction, scenario analysis
MODEL_DEEP = "nousresearch/hermes-3-llama-3.1-405b:free"
# Fallback when primary is rate-limited or unavailable
MODEL_FALLBACK = "google/gemma-4-31b-it:free"


def _build_payload(prompt: str, model: str, temperature: float) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }


async def call_ai(
    prompt: str,
    model: str = MODEL_FAST,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """
    Async OpenRouter call. Returns raw text from the model.
    Tries MODEL_FALLBACK automatically on 429/503.
    """
    headers = {**_HEADERS, "Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = _build_payload(prompt, model, temperature)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
            if r.status_code in (429, 503) and model != MODEL_FALLBACK:
                payload["model"] = MODEL_FALLBACK
                r = await client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, KeyError) as exc:
            raise RuntimeError(f"OpenRouter call failed: {exc}") from exc


def call_ai_sync(
    prompt: str,
    model: str = MODEL_FAST,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """
    Synchronous OpenRouter call (for non-async contexts).
    Tries MODEL_FALLBACK automatically on 429/503.
    """
    headers = {**_HEADERS, "Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = _build_payload(prompt, model, temperature)

    with httpx.Client(timeout=timeout) as client:
        try:
            r = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
            if r.status_code in (429, 503) and model != MODEL_FALLBACK:
                payload["model"] = MODEL_FALLBACK
                r = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, KeyError) as exc:
            raise RuntimeError(f"OpenRouter call failed: {exc}") from exc


def parse_json_response(raw: str) -> Any:
    """Strip markdown code fences and parse JSON."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE)
    return json.loads(raw)

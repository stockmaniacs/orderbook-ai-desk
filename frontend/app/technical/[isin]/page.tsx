"use client";

export const runtime = "edge";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

// ── Types (minimal) ───────────────────────────────────────────────────────────
interface TechnicalProfile {
  isin: string;
  symbol_nse: string | null;
  company_name: string;
  sector: string | null;
  industry: string | null;
  market_cap_cat: string | null;
  technical_score: number | null;
  conviction_score: number | null;
  rs_score: number | null;
  trend_score: number | null;
  momentum_score: number | null;
  volume_score: number | null;
  pattern_score: number | null;
  rs_rating: number | null;
  sector_rank: number | null;
  industry_rank: number | null;
  market_leader_rank: number | null;
  classification: string;
  signal: string;
  stage: number | null;
  minervini_count: number;
  cmp: number | null;
  pivot_price: number | null;
  entry_price: number | null;
  ideal_buy_zone_lo: number | null;
  ideal_buy_zone_hi: number | null;
  breakout_level: number | null;
  stop_loss: number | null;
  atr_stop: number | null;
  trailing_stop: number | null;
  target_price: number | null;
  expected_upside_pct: number | null;
  risk_reward_ratio: number | null;
  atr_14: number | null;
  atr_pct: number | null;
  volatility_20d: number | null;
  risk_score: number | null;
  position_size_pct: number | null;
  max_portfolio_alloc: number | null;
  active_pattern: string | null;
  pattern_maturity: number | null;
  scores_updated_at: string | null;
  price_date: string | null;
}

interface DailySnapshot {
  isin: string;
  snap_date: string;
  close: number | null;
  volume: number | null;
  sma_50: number | null;
  sma_150: number | null;
  sma_200: number | null;
  above_sma_50: boolean | null;
  above_sma_150: boolean | null;
  above_sma_200: boolean | null;
  high_52w: number | null;
  low_52w: number | null;
  pct_from_52w_high: number | null;
  rsi_14: number | null;
  rsi_weekly: number | null;
  adx_14: number | null;
  macd: number | null;
  macd_hist: number | null;
  macd_hist_expanding: boolean | null;
  vol_ratio: number | null;
  is_pocket_pivot: boolean;
  is_accumulation_day: boolean;
  is_distribution_day: boolean;
  distribution_days_20: number;
  tight_action_5d: boolean;
  atr_14: number | null;
  technical_score: number | null;
}

interface RelativeStrength {
  rs_rating: number | null;
  rs_vs_nifty500_1m: number | null;
  rs_vs_nifty500_3m: number | null;
  rs_vs_nifty500_6m: number | null;
  rs_vs_nifty500_12m: number | null;
  rs_trend: string | null;
  rs_breakout: boolean;
  rs_new_high: boolean;
  sector_rs_rank: number | null;
}

interface Pattern {
  id: string;
  pattern_type: string;
  status: string;
  detected_date: string;
  breakout_date: string | null;
  depth_pct: number | null;
  duration_days: number | null;
  contractions: number | null;
  pivot_price: number | null;
  buy_zone_lo: number | null;
  buy_zone_hi: number | null;
  pattern_stop: number | null;
  pattern_target: number | null;
  quality_score: number | null;
}

interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  title: string | null;
  description: string | null;
  alert_date: string;
  price_at_alert: number | null;
  tech_score_at: number | null;
  rs_rating_at: number | null;
  is_read: boolean;
  is_actioned: boolean;
}

interface SignalHistory {
  id: string;
  signal_date: string;
  signal: string;
  classification: string;
  pattern_type: string | null;
  technical_score: number | null;
  rs_rating: number | null;
  price_at_signal: number | null;
  target_price: number | null;
  stop_loss: number | null;
  risk_reward_ratio: number | null;
  return_7d: number | null;
  return_30d: number | null;
  return_60d: number | null;
  return_90d: number | null;
  outcome: string | null;
}

interface StockDetailOut {
  profile: TechnicalProfile;
  latest_snapshot: DailySnapshot | null;
  latest_rs: RelativeStrength | null;
  active_patterns: Pattern[];
  current_levels: {
    cmp: number | null;
    entry_price: number | null;
    ideal_buy_zone_lo: number | null;
    ideal_buy_zone_hi: number | null;
    breakout_level: number | null;
    pivot_price: number | null;
    stop_loss: number | null;
    atr_stop: number | null;
    trailing_stop: number | null;
    target_price: number | null;
    expected_upside_pct: number | null;
    risk_pct: number | null;
    risk_reward_ratio: number | null;
    position_size_pct: number | null;
    max_portfolio_alloc: number | null;
  } | null;
  recent_alerts: Alert[];
  signal_history: SignalHistory[];
  snapshot_history: DailySnapshot[];
  minervini_criteria: boolean[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const CLASS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  ELITE_LEADER:     { label: "Elite Leader",     color: "text-purple-300", bg: "bg-purple-900/40 border-purple-500/40" },
  STRONG_STRUCTURE: { label: "Strong Structure", color: "text-blue-300",   bg: "bg-blue-900/40 border-blue-500/40" },
  EMERGING_LEADER:  { label: "Emerging Leader",  color: "text-cyan-300",   bg: "bg-cyan-900/40 border-cyan-500/40" },
  CONSTRUCTIVE:     { label: "Constructive",     color: "text-green-300",  bg: "bg-green-900/40 border-green-500/40" },
  WATCHLIST:        { label: "Watchlist",        color: "text-yellow-300", bg: "bg-yellow-900/40 border-yellow-500/40" },
  WEAK_STRUCTURE:   { label: "Weak Structure",   color: "text-orange-300", bg: "bg-orange-900/40 border-orange-500/40" },
  AVOID:            { label: "Avoid",            color: "text-red-300",    bg: "bg-red-900/40 border-red-500/40" },
};

const SIGNAL_COLORS: Record<string, string> = {
  STRONG_BUY:   "text-emerald-300 bg-emerald-900/50 border-emerald-500/40",
  BUY:          "text-green-300 bg-green-900/50 border-green-500/40",
  ACCUMULATION: "text-teal-300 bg-teal-900/50 border-teal-500/40",
  HOLD:         "text-yellow-300 bg-yellow-900/50 border-yellow-500/40",
  REDUCE:       "text-orange-300 bg-orange-900/50 border-orange-500/40",
  SELL:         "text-red-300 bg-red-900/50 border-red-500/40",
  AVOID:        "text-red-400 bg-red-950/50 border-red-600/40",
};

const OUTCOME_CONFIG: Record<string, { label: string; color: string }> = {
  WIN:     { label: "WIN",     color: "text-emerald-300 bg-emerald-900/40 border-emerald-500/40" },
  LOSS:    { label: "LOSS",    color: "text-red-300 bg-red-900/40 border-red-500/40" },
  NEUTRAL: { label: "NEUTRAL", color: "text-gray-300 bg-gray-800 border-gray-600" },
  OPEN:    { label: "OPEN",    color: "text-blue-300 bg-blue-900/40 border-blue-500/40" },
};

const SEVERITY_COLORS: Record<string, string> = {
  HIGH:   "text-red-400 bg-red-900/40 border-red-500/40",
  MEDIUM: "text-yellow-400 bg-yellow-900/40 border-yellow-500/40",
  LOW:    "text-gray-300 bg-gray-800 border-gray-600",
};

const MINERVINI_LABELS = [
  "Price > 200 SMA",
  "200 SMA trending up ≥1 month",
  "150 SMA > 200 SMA",
  "50 SMA > 150 SMA & 200 SMA",
  "Price > 50 SMA",
  "Price ≥25% above 52w low",
  "Price within 25% of 52w high",
  "RS Rating ≥70",
];

const STAGE_DESC: Record<number, string> = {
  1: "Stage 1 — Accumulation Base (sideways, below 200 SMA)",
  2: "Stage 2 — Mark-Up Phase (advancing, actionable)",
  3: "Stage 3 — Distribution Top (late-stage, avoid new positions)",
  4: "Stage 4 — Mark-Down Decline (avoid / short)",
};

const PATTERN_LABELS: Record<string, string> = {
  VCP: "Volatility Contraction Pattern",
  CUP_HANDLE: "Cup & Handle",
  FLAT_BASE: "Flat Base",
  DOUBLE_BOTTOM: "Double Bottom",
  ASCENDING_BASE: "Ascending Base",
  HIGH_TIGHT_FLAG: "High Tight Flag",
  DARVAS_BOX: "Darvas Box",
  RANGE_CONTRACTION: "Range Contraction (NR7)",
};

const STATUS_COLORS: Record<string, string> = {
  FORMING:    "text-blue-300 bg-blue-900/40 border-blue-500/40",
  COMPLETE:   "text-purple-300 bg-purple-900/40 border-purple-500/40",
  BREAKOUT:   "text-emerald-300 bg-emerald-900/40 border-emerald-500/40",
  FAILED:     "text-red-300 bg-red-900/40 border-red-500/40",
  INVALIDATED:"text-gray-400 bg-gray-800 border-gray-600",
};

function fmt(n: number | null | undefined, dec = 1) {
  if (n == null) return "—";
  return n.toFixed(dec);
}

function pct(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function inr(n: number | null | undefined) {
  if (n == null) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function ScoreBar({ label, value, max = 100 }: { label: string; value: number | null; max?: number }) {
  const pct2 = value != null ? Math.min(100, (value / max) * 100) : 0;
  const color =
    pct2 >= 80 ? "bg-purple-500" : pct2 >= 65 ? "bg-blue-500" : pct2 >= 50 ? "bg-teal-500" : pct2 >= 35 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-28 flex-shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct2}%` }} />
      </div>
      <span className="text-sm font-semibold text-gray-200 w-8 text-right">{value != null ? Math.round(value) : "—"}</span>
    </div>
  );
}

function LevelRow({ label, value, color = "text-gray-200", note }: { label: string; value: string; color?: string; note?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-800/60 last:border-0">
      <span className="text-xs text-gray-400">{label}{note && <span className="ml-1 text-[10px] text-gray-600">({note})</span>}</span>
      <span className={`text-sm font-semibold font-mono ${color}`}>{value}</span>
    </div>
  );
}

const TABS = ["Overview", "Trade Levels", "Patterns", "RS & Breadth", "Signal History", "Alerts"] as const;
type Tab = typeof TABS[number];

// ── Component ─────────────────────────────────────────────────────────────────
export default function TechnicalDetailPage() {
  const { isin } = useParams<{ isin: string }>();
  const [data, setData] = useState<StockDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");

  useEffect(() => {
    if (!isin) return;
    setLoading(true);
    fetch(`/api/v1/technical/${isin}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [isin]);

  const markAlert = async (alertId: string, updates: { is_read?: boolean; is_actioned?: boolean }) => {
    await fetch(`/api/v1/technical/alerts/${alertId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        recent_alerts: prev.recent_alerts.map((a) =>
          a.id === alertId ? { ...a, ...updates } : a
        ),
      };
    });
  };

  if (loading) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">
      Loading…
    </div>
  );
  if (error || !data) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center text-red-400">
      {error ?? "Not found"}
    </div>
  );

  const { profile: p, latest_snapshot: snap, latest_rs: rs, active_patterns, current_levels: lvl,
          recent_alerts, signal_history, minervini_criteria } = data;

  const cls = CLASS_CONFIG[p.classification] ?? CLASS_CONFIG["WATCHLIST"];
  const unreadAlerts = recent_alerts.filter((a) => !a.is_read).length;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      {/* Back */}
      <a href="/technical" className="text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4 inline-flex items-center gap-1">
        ← Back to Scanner
      </a>

      {/* Header card */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 mt-3 mb-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-white">{p.symbol_nse ?? p.isin}</h1>
              <span className={`text-xs font-semibold px-2 py-1 rounded border ${cls.bg} ${cls.color}`}>
                {cls.label}
              </span>
              <span className={`text-xs font-medium px-2 py-1 rounded border ${SIGNAL_COLORS[p.signal] ?? SIGNAL_COLORS["HOLD"]}`}>
                {p.signal.replace("_", " ")}
              </span>
              {p.stage != null && (
                <span className={`text-xs font-bold px-2 py-1 rounded ${
                  p.stage === 2 ? "text-emerald-400 bg-emerald-900/50" :
                  p.stage === 1 ? "text-gray-400 bg-gray-800" :
                  p.stage === 3 ? "text-yellow-400 bg-yellow-900/50" : "text-red-400 bg-red-900/50"
                }`}>Stage {p.stage}</span>
              )}
            </div>
            <p className="text-gray-400 mt-1">{p.company_name}</p>
            {p.sector && <p className="text-sm text-gray-500 mt-0.5">{p.sector}{p.industry ? ` · ${p.industry}` : ""}</p>}
            {p.stage != null && (
              <p className="text-xs text-gray-500 mt-1">{STAGE_DESC[p.stage]}</p>
            )}
          </div>
          <div className="text-right flex-shrink-0">
            <div className="text-3xl font-bold text-white">{inr(p.cmp)}</div>
            {snap?.pct_from_52w_high != null && (
              <div className="text-sm text-gray-400 mt-0.5">
                {Math.abs(snap.pct_from_52w_high).toFixed(1)}% from 52w high
              </div>
            )}
            <div className="text-xs text-gray-500 mt-0.5">{p.price_date ?? ""}</div>
          </div>
        </div>

        {/* Quick stats strip */}
        <div className="grid grid-cols-5 gap-3 mt-4 pt-4 border-t border-gray-800">
          {[
            { label: "Tech Score", value: `${Math.round(p.technical_score ?? 0)}/100`, color: "text-blue-400" },
            { label: "Conviction", value: `${Math.round(p.conviction_score ?? 0)}/100`, color: "text-purple-400" },
            { label: "RS Rating", value: `${p.rs_rating ?? "—"}/99`, color: "text-emerald-400" },
            { label: "Minervini", value: `${p.minervini_count}/8`, color: p.minervini_count >= 7 ? "text-emerald-400" : p.minervini_count >= 5 ? "text-yellow-400" : "text-red-400" },
            { label: "Leader Rank", value: p.market_leader_rank != null ? `#${p.market_leader_rank}` : "—", color: "text-cyan-400" },
          ].map((s) => (
            <div key={s.label} className="text-center">
              <div className={`text-lg font-bold ${s.color}`}>{s.value}</div>
              <div className="text-[10px] text-gray-500">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800 mb-5">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors relative ${
              activeTab === t
                ? "border-blue-500 text-blue-400 bg-blue-900/20"
                : "border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40"
            }`}
          >
            {t}
            {t === "Alerts" && unreadAlerts > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-[9px] flex items-center justify-center text-white">
                {unreadAlerts}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab: Overview ── */}
      {activeTab === "Overview" && (
        <div className="grid grid-cols-2 gap-5">
          {/* Score breakdown */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Score Breakdown</h2>
            <ScoreBar label="Technical Score"  value={p.technical_score} />
            <ScoreBar label="Conviction Score" value={p.conviction_score} />
            <ScoreBar label="Trend (30%)"      value={p.trend_score} />
            <ScoreBar label="RS (25%)"         value={p.rs_score} />
            <ScoreBar label="Momentum (20%)"   value={p.momentum_score} />
            <ScoreBar label="Volume (15%)"     value={p.volume_score} />
            <ScoreBar label="Pattern (10%)"    value={p.pattern_score} />
          </div>

          {/* Minervini Checklist */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-200">Minervini Trend Template</h2>
              <span className={`text-sm font-bold ${
                p.minervini_count >= 7 ? "text-emerald-400" :
                p.minervini_count >= 5 ? "text-yellow-400" : "text-red-400"
              }`}>{p.minervini_count}/8</span>
            </div>
            <div className="space-y-2">
              {MINERVINI_LABELS.map((label, i) => {
                const pass = minervini_criteria[i] ?? false;
                return (
                  <div key={i} className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                    pass ? "border-emerald-500/30 bg-emerald-900/20" : "border-red-500/20 bg-red-900/10"
                  }`}>
                    <span className={`text-lg flex-shrink-0 ${pass ? "text-emerald-400" : "text-red-500"}`}>
                      {pass ? "✓" : "✗"}
                    </span>
                    <span className={`text-xs ${pass ? "text-emerald-300" : "text-gray-400"}`}>{label}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* MA Alignment */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Moving Average Alignment</h2>
            {snap ? (
              <div className="space-y-0">
                {[
                  { label: "Price vs 50 SMA",  above: snap.above_sma_50,  price: snap.close, sma: snap.sma_50 },
                  { label: "Price vs 150 SMA", above: snap.above_sma_150, price: snap.close, sma: snap.sma_150 },
                  { label: "Price vs 200 SMA", above: snap.above_sma_200, price: snap.close, sma: snap.sma_200 },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between py-2.5 border-b border-gray-800/50 last:border-0">
                    <span className="text-xs text-gray-400">{row.label}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-gray-300">{inr(row.sma)}</span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                        row.above ? "text-emerald-400 bg-emerald-900/40" : "text-red-400 bg-red-900/40"
                      }`}>
                        {row.above ? "ABOVE" : "BELOW"}
                      </span>
                    </div>
                  </div>
                ))}
                <div className="flex items-center justify-between py-2.5 border-b border-gray-800/50">
                  <span className="text-xs text-gray-400">RSI (14)</span>
                  <span className={`text-sm font-semibold font-mono ${
                    (snap.rsi_14 ?? 0) >= 70 ? "text-orange-400" :
                    (snap.rsi_14 ?? 0) >= 50 ? "text-emerald-400" : "text-red-400"
                  }`}>{fmt(snap.rsi_14)}</span>
                </div>
                <div className="flex items-center justify-between py-2.5 border-b border-gray-800/50">
                  <span className="text-xs text-gray-400">ADX (14)</span>
                  <span className={`text-sm font-semibold font-mono ${(snap.adx_14 ?? 0) >= 25 ? "text-emerald-400" : "text-gray-400"}`}>
                    {fmt(snap.adx_14)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2.5 border-b border-gray-800/50">
                  <span className="text-xs text-gray-400">MACD Histogram</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-semibold font-mono ${(snap.macd_hist ?? 0) > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {fmt(snap.macd_hist, 3)}
                    </span>
                    {snap.macd_hist_expanding && (
                      <span className="text-[10px] text-emerald-400 bg-emerald-900/40 px-1 py-0.5 rounded">Expanding</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between py-2.5 border-b border-gray-800/50">
                  <span className="text-xs text-gray-400">Volume Ratio</span>
                  <span className={`text-sm font-semibold font-mono ${(snap.vol_ratio ?? 0) >= 1.5 ? "text-emerald-400" : "text-gray-300"}`}>
                    {fmt(snap.vol_ratio, 2)}x
                  </span>
                </div>
                {snap.is_pocket_pivot && (
                  <div className="mt-2 py-1.5 px-3 rounded-lg bg-emerald-900/30 border border-emerald-500/30 text-xs text-emerald-300">
                    ✦ Pocket Pivot detected — institutional accumulation signal
                  </div>
                )}
                {snap.is_distribution_day && (
                  <div className="mt-2 py-1.5 px-3 rounded-lg bg-red-900/30 border border-red-500/30 text-xs text-red-300">
                    ✦ Distribution day — heavy selling pressure
                    {snap.distribution_days_20 > 3 && ` (${snap.distribution_days_20} in 20d)`}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-500 text-sm">No snapshot available</p>
            )}
          </div>

          {/* 52w context */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Price Context</h2>
            {snap ? (
              <div className="space-y-0">
                <LevelRow label="52-Week High"         value={inr(snap.high_52w)} color="text-emerald-400" />
                <LevelRow label="52-Week Low"          value={inr(snap.low_52w)} color="text-red-400" />
                <LevelRow label="% from 52w High"      value={`${fmt(snap.pct_from_52w_high)}%`}
                  color={(snap.pct_from_52w_high ?? 0) >= -15 ? "text-emerald-400" : "text-orange-400"} />
                <LevelRow label="ATR (14)"             value={`${inr(snap.atr_14)} (${fmt(p.atr_pct)}%)`} />
                <LevelRow label="Volatility (20d)"     value={`${fmt(p.volatility_20d)}%`} />
                <LevelRow label="Risk Score"           value={`${fmt(p.risk_score)}/100`} />
                <LevelRow label="Tight 5-Day Action"   value={snap.tight_action_5d ? "✓ Yes" : "—"}
                  color={snap.tight_action_5d ? "text-emerald-400" : "text-gray-400"} />
                <LevelRow label="Distribution Days"    value={String(snap.distribution_days_20)}
                  color={snap.distribution_days_20 >= 4 ? "text-red-400" : snap.distribution_days_20 >= 2 ? "text-orange-400" : "text-gray-200"} />
              </div>
            ) : (
              <p className="text-gray-500 text-sm">No snapshot available</p>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Trade Levels ── */}
      {activeTab === "Trade Levels" && (
        <div className="grid grid-cols-2 gap-5">
          {/* Entry zone */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Entry & Pivot Levels</h2>
            {lvl ? (
              <div>
                <LevelRow label="Current Price"   value={inr(lvl.cmp)} color="text-white" />
                <LevelRow label="Pivot Price"     value={inr(lvl.pivot_price)} color="text-purple-400" note="pattern pivot" />
                <LevelRow label="Entry Price"     value={inr(lvl.entry_price)} color="text-blue-400" />
                <LevelRow label="Buy Zone Low"    value={inr(lvl.ideal_buy_zone_lo)} color="text-teal-400" />
                <LevelRow label="Buy Zone High"   value={inr(lvl.ideal_buy_zone_hi)} color="text-teal-400" />
                <LevelRow label="Breakout Level"  value={inr(lvl.breakout_level)} color="text-emerald-400" />
              </div>
            ) : (
              <div>
                <LevelRow label="Current Price"   value={inr(p.cmp)} color="text-white" />
                <LevelRow label="Pivot Price"     value={inr(p.pivot_price)} color="text-purple-400" />
                <LevelRow label="Entry Price"     value={inr(p.entry_price)} color="text-blue-400" />
                <LevelRow label="Buy Zone Low"    value={inr(p.ideal_buy_zone_lo)} color="text-teal-400" />
                <LevelRow label="Buy Zone High"   value={inr(p.ideal_buy_zone_hi)} color="text-teal-400" />
                <LevelRow label="Breakout Level"  value={inr(p.breakout_level)} color="text-emerald-400" />
              </div>
            )}
          </div>

          {/* Exit / risk levels */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Exit & Risk Levels</h2>
            {lvl ? (
              <div>
                <LevelRow label="Target Price"   value={inr(lvl.target_price)} color="text-emerald-400" />
                <LevelRow label="Expected Upside" value={pct(lvl.expected_upside_pct)} color="text-emerald-400" />
                <LevelRow label="Stop Loss"      value={inr(lvl.stop_loss)} color="text-red-400" />
                <LevelRow label="ATR Stop"       value={inr(lvl.atr_stop)} color="text-orange-400" />
                <LevelRow label="Trailing Stop"  value={inr(lvl.trailing_stop)} color="text-orange-300" />
                <LevelRow label="Risk %"         value={`${fmt(lvl.risk_pct)}%`} />
                <LevelRow label="Risk/Reward"    value={lvl.risk_reward_ratio != null ? `${lvl.risk_reward_ratio.toFixed(1)}x` : "—"}
                  color={(lvl.risk_reward_ratio ?? 0) >= 3 ? "text-emerald-400" : (lvl.risk_reward_ratio ?? 0) >= 2 ? "text-yellow-400" : "text-red-400"} />
              </div>
            ) : (
              <div>
                <LevelRow label="Target Price"   value={inr(p.target_price)} color="text-emerald-400" />
                <LevelRow label="Expected Upside" value={pct(p.expected_upside_pct)} color="text-emerald-400" />
                <LevelRow label="Stop Loss"      value={inr(p.stop_loss)} color="text-red-400" />
                <LevelRow label="ATR Stop"       value={inr(p.atr_stop)} color="text-orange-400" />
                <LevelRow label="Trailing Stop"  value={inr(p.trailing_stop)} color="text-orange-300" />
                <LevelRow label="Risk/Reward"    value={p.risk_reward_ratio != null ? `${p.risk_reward_ratio.toFixed(1)}x` : "—"}
                  color={(p.risk_reward_ratio ?? 0) >= 3 ? "text-emerald-400" : (p.risk_reward_ratio ?? 0) >= 2 ? "text-yellow-400" : "text-red-400"} />
              </div>
            )}
          </div>

          {/* Position sizing */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 col-span-2">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Position Sizing</h2>
            <div className="grid grid-cols-4 gap-4 text-center">
              {[
                { label: "Suggested Position %", value: `${fmt(p.position_size_pct)}%`, color: "text-blue-400" },
                { label: "Max Portfolio Alloc", value: `${fmt(p.max_portfolio_alloc)}%`, color: "text-purple-400" },
                { label: "Classification", value: cls.label, color: cls.color },
                { label: "ATR %", value: `${fmt(p.atr_pct)}%`, color: "text-gray-300" },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-gray-800 bg-gray-800/40 p-3">
                  <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">{s.label}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 p-3 rounded-lg bg-gray-800/40 border border-gray-700 text-xs text-gray-400">
              <span className="font-semibold text-gray-300">Sizing method: </span>
              Kelly-inspired risk-per-trade model. Assumes 1% portfolio risk per trade ÷ stop loss% = position size, capped at classification maximum.
              For a ₹10L portfolio with {fmt(p.atr_pct)}% ATR-based stop, suggested size ≈ {fmt(p.position_size_pct)}% of portfolio.
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Patterns ── */}
      {activeTab === "Patterns" && (
        <div className="space-y-4">
          {active_patterns.length === 0 ? (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-10 text-center text-gray-500">
              No active patterns detected
            </div>
          ) : (
            active_patterns.map((pat) => (
              <div key={pat.id} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-base font-semibold text-white">
                        {PATTERN_LABELS[pat.pattern_type] ?? pat.pattern_type}
                      </h3>
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium ${STATUS_COLORS[pat.status] ?? ""}`}>
                        {pat.status}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">Detected: {pat.detected_date}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-2xl font-bold text-purple-400">{fmt(pat.quality_score)}</div>
                    <div className="text-[10px] text-gray-500">Quality Score</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div>
                    <LevelRow label="Pivot Price"    value={inr(pat.pivot_price)} color="text-purple-400" />
                    <LevelRow label="Buy Zone"       value={`${inr(pat.buy_zone_lo)} – ${inr(pat.buy_zone_hi)}`} color="text-teal-400" />
                    <LevelRow label="Pattern Stop"   value={inr(pat.pattern_stop)} color="text-red-400" />
                    <LevelRow label="Pattern Target" value={inr(pat.pattern_target)} color="text-emerald-400" />
                  </div>
                  <div>
                    <LevelRow label="Depth %" value={`${fmt(pat.depth_pct)}%`} />
                    <LevelRow label="Duration" value={pat.duration_days != null ? `${pat.duration_days}d` : "—"} />
                    {pat.contractions != null && (
                      <LevelRow label="Contractions" value={String(pat.contractions)} color="text-blue-400" />
                    )}
                    {pat.breakout_date && (
                      <LevelRow label="Breakout Date" value={pat.breakout_date} color="text-emerald-400" />
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Tab: RS & Breadth ── */}
      {activeTab === "RS & Breadth" && (
        <div className="grid grid-cols-2 gap-5">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Relative Strength</h2>
            {rs ? (
              <div>
                <div className="mb-4 p-3 rounded-lg bg-gray-800/50 border border-gray-700">
                  <div className="text-3xl font-bold text-emerald-400 text-center">{rs.rs_rating ?? "—"}</div>
                  <div className="text-[10px] text-gray-500 text-center mt-0.5">IBD-Style RS Rating (1–99)</div>
                </div>
                <LevelRow label="RS vs Nifty500 1M"  value={pct(rs.rs_vs_nifty500_1m)} color={(rs.rs_vs_nifty500_1m ?? 0) > 0 ? "text-emerald-400" : "text-red-400"} />
                <LevelRow label="RS vs Nifty500 3M"  value={pct(rs.rs_vs_nifty500_3m)} color={(rs.rs_vs_nifty500_3m ?? 0) > 0 ? "text-emerald-400" : "text-red-400"} />
                <LevelRow label="RS vs Nifty500 6M"  value={pct(rs.rs_vs_nifty500_6m)} color={(rs.rs_vs_nifty500_6m ?? 0) > 0 ? "text-emerald-400" : "text-red-400"} />
                <LevelRow label="RS vs Nifty500 12M" value={pct(rs.rs_vs_nifty500_12m)} color={(rs.rs_vs_nifty500_12m ?? 0) > 0 ? "text-emerald-400" : "text-red-400"} />
                <div className="mt-3 border-t border-gray-800 pt-3 space-y-0">
                  <LevelRow label="RS Trend"       value={rs.rs_trend ?? "—"} color={rs.rs_trend === "UP" ? "text-emerald-400" : rs.rs_trend === "DOWN" ? "text-red-400" : "text-gray-400"} />
                  <LevelRow label="RS Breakout"    value={rs.rs_breakout ? "✓ Yes" : "—"} color={rs.rs_breakout ? "text-emerald-400" : "text-gray-400"} />
                  <LevelRow label="RS New High"    value={rs.rs_new_high ? "✓ Yes" : "—"} color={rs.rs_new_high ? "text-emerald-400" : "text-gray-400"} />
                  <LevelRow label="Sector RS Rank" value={rs.sector_rs_rank != null ? `#${rs.sector_rs_rank}` : "—"} color="text-cyan-400" />
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">No RS data available</p>
            )}
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">Rankings</h2>
            <div className="grid grid-cols-1 gap-3">
              {[
                { label: "Market Leader Rank",  value: p.market_leader_rank != null ? `#${p.market_leader_rank}` : "—", color: "text-purple-400" },
                { label: "Sector Rank",         value: p.sector_rank != null ? `#${p.sector_rank}` : "—", color: "text-blue-400" },
                { label: "Industry Rank",       value: p.industry_rank != null ? `#${p.industry_rank}` : "—", color: "text-cyan-400" },
              ].map((r) => (
                <div key={r.label} className="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-800/30">
                  <span className="text-sm text-gray-300">{r.label}</span>
                  <span className={`text-xl font-bold ${r.color}`}>{r.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Signal History ── */}
      {activeTab === "Signal History" && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/80">
                {["Date", "Signal", "Classification", "Pattern", "Tech Score", "RS", "Price", "Target", "Stop", "R/R", "7d", "30d", "60d", "90d", "Outcome"].map((h) => (
                  <th key={h} className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {signal_history.length === 0 && (
                <tr><td colSpan={15} className="text-center py-10 text-gray-500">No signal history yet</td></tr>
              )}
              {signal_history.map((s) => {
                const oc = OUTCOME_CONFIG[s.outcome ?? "OPEN"] ?? OUTCOME_CONFIG["OPEN"];
                return (
                  <tr key={s.id} className="border-b border-gray-800/60 hover:bg-gray-800/20">
                    <td className="px-3 py-2 text-xs text-gray-400 whitespace-nowrap">{s.signal_date}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${SIGNAL_COLORS[s.signal] ?? ""}`}>
                        {s.signal.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1 py-0.5 rounded ${CLASS_CONFIG[s.classification]?.color ?? "text-gray-400"}`}>
                        {s.classification?.split("_")[0] ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-400">{s.pattern_type ? PATTERN_LABELS[s.pattern_type]?.split(" ")[0] ?? s.pattern_type : "—"}</td>
                    <td className="px-3 py-2 text-xs font-mono text-gray-300">{fmt(s.technical_score)}</td>
                    <td className="px-3 py-2 text-xs font-mono text-gray-300">{s.rs_rating ?? "—"}</td>
                    <td className="px-3 py-2 text-xs font-mono text-gray-200">{inr(s.price_at_signal)}</td>
                    <td className="px-3 py-2 text-xs font-mono text-emerald-400">{inr(s.target_price)}</td>
                    <td className="px-3 py-2 text-xs font-mono text-red-400">{inr(s.stop_loss)}</td>
                    <td className="px-3 py-2 text-xs font-mono text-gray-300">{s.risk_reward_ratio != null ? `${s.risk_reward_ratio.toFixed(1)}x` : "—"}</td>
                    {[s.return_7d, s.return_30d, s.return_60d, s.return_90d].map((ret, i) => (
                      <td key={i} className={`px-3 py-2 text-xs font-mono ${ret == null ? "text-gray-600" : ret > 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {ret != null ? pct(ret) : "—"}
                      </td>
                    ))}
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${oc.color}`}>
                        {oc.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Tab: Alerts ── */}
      {activeTab === "Alerts" && (
        <div className="space-y-3">
          {recent_alerts.length === 0 ? (
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-10 text-center text-gray-500">
              No alerts for this stock
            </div>
          ) : (
            recent_alerts.map((alert) => (
              <div
                key={alert.id}
                className={`rounded-xl border bg-gray-900 p-4 transition-colors ${
                  !alert.is_read ? "border-blue-500/30" : "border-gray-800"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      {!alert.is_read && <span className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0" />}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${SEVERITY_COLORS[alert.severity] ?? ""}`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">{alert.alert_type.replace(/_/g, " ")}</span>
                      <span className="text-xs text-gray-600">{alert.alert_date}</span>
                    </div>
                    {alert.title && (
                      <p className="text-sm font-semibold text-gray-200 mt-1.5">{alert.title}</p>
                    )}
                    {alert.description && (
                      <p className="text-xs text-gray-400 mt-1">{alert.description}</p>
                    )}
                    {alert.price_at_alert != null && (
                      <p className="text-xs text-gray-500 mt-1">
                        Price: <span className="font-mono text-gray-300">{inr(alert.price_at_alert)}</span>
                        {alert.tech_score_at != null && <> · Tech Score: <span className="text-gray-300">{fmt(alert.tech_score_at)}</span></>}
                        {alert.rs_rating_at != null && <> · RS: <span className="text-gray-300">{alert.rs_rating_at}</span></>}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    {!alert.is_read && (
                      <button
                        onClick={() => markAlert(alert.id, { is_read: true })}
                        className="text-xs px-2.5 py-1 rounded border border-gray-700 hover:border-blue-500 text-gray-400 hover:text-blue-400 transition-colors"
                      >
                        Mark Read
                      </button>
                    )}
                    {!alert.is_actioned && (
                      <button
                        onClick={() => markAlert(alert.id, { is_actioned: true })}
                        className="text-xs px-2.5 py-1 rounded border border-gray-700 hover:border-emerald-500 text-gray-400 hover:text-emerald-400 transition-colors"
                      >
                        Action
                      </button>
                    )}
                    {alert.is_actioned && (
                      <span className="text-xs text-gray-600 px-2">Actioned</span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

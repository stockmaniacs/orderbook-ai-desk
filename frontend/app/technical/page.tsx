"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface DashboardStockRow {
  isin: string;
  symbol_nse: string | null;
  company_name: string;
  sector: string | null;
  market_cap_cat: string | null;
  technical_score: number | null;
  conviction_score: number | null;
  rs_rating: number | null;
  trend_score: number | null;
  momentum_score: number | null;
  volume_score: number | null;
  classification: string;
  signal: string;
  stage: number | null;
  minervini_count: number;
  active_pattern: string | null;
  cmp: number | null;
  target_price: number | null;
  expected_upside_pct: number | null;
  risk_reward_ratio: number | null;
  position_size_pct: number | null;
  sector_rank: number | null;
  industry_rank: number | null;
  market_leader_rank: number | null;
  unread_alert_count: number;
  price_date: string | null;
}

interface MarketBreadthOut {
  breadth_date: string;
  total_stocks: number | null;
  pct_above_sma_50: number | null;
  pct_above_sma_150: number | null;
  pct_above_sma_200: number | null;
  new_highs: number | null;
  new_lows: number | null;
  nh_nl_ratio: number | null;
  advances: number | null;
  declines: number | null;
  ad_ratio: number | null;
  elite_leaders_count: number;
  strong_structure_count: number;
  top_sectors: Record<string, number> | null;
  market_regime: string | null;
}

interface TechnicalDashboardOut {
  total: number;
  elite_leaders: number;
  strong_structure: number;
  emerging_leaders: number;
  items: DashboardStockRow[];
  market_breadth: MarketBreadthOut | null;
  unread_alerts: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const CLASS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  ELITE_LEADER:     { label: "Elite Leader",     color: "text-purple-400", bg: "bg-purple-900/40 border-purple-500/40" },
  STRONG_STRUCTURE: { label: "Strong Structure", color: "text-blue-400",   bg: "bg-blue-900/40 border-blue-500/40" },
  EMERGING_LEADER:  { label: "Emerging Leader",  color: "text-cyan-400",   bg: "bg-cyan-900/40 border-cyan-500/40" },
  CONSTRUCTIVE:     { label: "Constructive",     color: "text-green-400",  bg: "bg-green-900/40 border-green-500/40" },
  WATCHLIST:        { label: "Watchlist",        color: "text-yellow-400", bg: "bg-yellow-900/40 border-yellow-500/40" },
  WEAK_STRUCTURE:   { label: "Weak Structure",   color: "text-orange-400", bg: "bg-orange-900/40 border-orange-500/40" },
  AVOID:            { label: "Avoid",            color: "text-red-400",    bg: "bg-red-900/40 border-red-500/40" },
};

const SIGNAL_CONFIG: Record<string, { label: string; color: string }> = {
  STRONG_BUY:   { label: "Strong Buy",   color: "text-emerald-300 bg-emerald-900/60 border-emerald-500/50" },
  BUY:          { label: "Buy",          color: "text-green-300 bg-green-900/60 border-green-500/50" },
  ACCUMULATION: { label: "Accumulate",   color: "text-teal-300 bg-teal-900/60 border-teal-500/50" },
  HOLD:         { label: "Hold",         color: "text-yellow-300 bg-yellow-900/60 border-yellow-500/50" },
  REDUCE:       { label: "Reduce",       color: "text-orange-300 bg-orange-900/60 border-orange-500/50" },
  SELL:         { label: "Sell",         color: "text-red-300 bg-red-900/60 border-red-500/50" },
  AVOID:        { label: "Avoid",        color: "text-red-400 bg-red-950/60 border-red-600/50" },
};

const REGIME_CONFIG: Record<string, { label: string; color: string }> = {
  BULL_CONFIRMED:  { label: "Bull Confirmed",  color: "text-emerald-400" },
  BULL_UNDER_PRESSURE: { label: "Bull Under Pressure", color: "text-yellow-400" },
  UPTREND_RESUMING: { label: "Uptrend Resuming", color: "text-teal-400" },
  SIDEWAYS:        { label: "Sideways",        color: "text-gray-400" },
  DOWNTREND:       { label: "Downtrend",       color: "text-orange-400" },
  BEAR_CONFIRMED:  { label: "Bear Confirmed",  color: "text-red-400" },
};

const PATTERN_LABELS: Record<string, string> = {
  VCP: "VCP", CUP_HANDLE: "C&H", FLAT_BASE: "Flat", DOUBLE_BOTTOM: "2B",
  ASCENDING_BASE: "Asc", HIGH_TIGHT_FLAG: "HTF", DARVAS_BOX: "Darvas",
  RANGE_CONTRACTION: "NR7",
};

function fmt(n: number | null, dec = 1) {
  if (n == null) return "—";
  return n.toFixed(dec);
}

function ScoreBar({ value, max = 100, color = "bg-blue-500" }: { value: number | null; max?: number; color?: string }) {
  const pct = value != null ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 rounded-full bg-gray-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-300 w-6 text-right">{value != null ? Math.round(value) : "—"}</span>
    </div>
  );
}

function StageBadge({ stage }: { stage: number | null }) {
  if (stage == null) return null;
  const colors = ["", "text-gray-400 bg-gray-800", "text-emerald-400 bg-emerald-900/50", "text-yellow-400 bg-yellow-900/50", "text-red-400 bg-red-900/50"];
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${colors[stage] ?? "text-gray-400 bg-gray-800"}`}>
      S{stage}
    </span>
  );
}

function MinerviniBars({ count }: { count: number }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className={`w-1.5 h-3 rounded-sm ${i < count ? "bg-emerald-500" : "bg-gray-700"}`}
        />
      ))}
    </div>
  );
}

// ── Classification tabs ───────────────────────────────────────────────────────
const CLASS_TABS = [
  { key: "",                value: "All" },
  { key: "ELITE_LEADER",   value: "Elite Leaders" },
  { key: "STRONG_STRUCTURE", value: "Strong Structure" },
  { key: "EMERGING_LEADER", value: "Emerging Leaders" },
  { key: "CONSTRUCTIVE",   value: "Constructive" },
  { key: "WATCHLIST",      value: "Watchlist" },
];

const SORT_OPTIONS = [
  { key: "conviction_score",   label: "Conviction" },
  { key: "technical_score",   label: "Tech Score" },
  { key: "rs_rating",         label: "RS Rating" },
  { key: "market_leader_rank", label: "Leader Rank" },
  { key: "expected_upside_pct", label: "Upside %" },
];

// ── Breadth Panel ─────────────────────────────────────────────────────────────
function BreadthPanel({ b }: { b: MarketBreadthOut }) {
  const regime = REGIME_CONFIG[b.market_regime ?? ""] ?? { label: b.market_regime ?? "—", color: "text-gray-400" };
  const topSectors = b.top_sectors ? Object.entries(b.top_sectors).slice(0, 5) : [];
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">Market Breadth</h3>
        <span className={`text-xs font-bold ${regime.color}`}>{regime.label}</span>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="text-lg font-bold text-blue-400">{fmt(b.pct_above_sma_200)}%</div>
          <div className="text-[10px] text-gray-500">Above 200 SMA</div>
        </div>
        <div>
          <div className="text-lg font-bold text-cyan-400">{fmt(b.pct_above_sma_150)}%</div>
          <div className="text-[10px] text-gray-500">Above 150 SMA</div>
        </div>
        <div>
          <div className="text-lg font-bold text-teal-400">{fmt(b.pct_above_sma_50)}%</div>
          <div className="text-[10px] text-gray-500">Above 50 SMA</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-center">
        <div>
          <div className="text-sm font-bold text-emerald-400">↑ {b.new_highs ?? "—"}</div>
          <div className="text-[10px] text-gray-500">New Highs</div>
        </div>
        <div>
          <div className="text-sm font-bold text-red-400">↓ {b.new_lows ?? "—"}</div>
          <div className="text-[10px] text-gray-500">New Lows</div>
        </div>
      </div>
      {topSectors.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-500 mb-1.5 uppercase tracking-wider">Top Sectors</div>
          <div className="space-y-1">
            {topSectors.map(([sector, score]) => (
              <div key={sector} className="flex items-center gap-2">
                <div className="flex-1 text-[11px] text-gray-300 truncate">{sector}</div>
                <div className="h-1 w-16 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-purple-500 rounded-full" style={{ width: `${Math.min(100, Number(score))}%` }} />
                </div>
                <span className="text-[10px] text-gray-400 w-5 text-right">{Math.round(Number(score))}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="pt-2 border-t border-gray-800 flex justify-between text-[11px] text-gray-400">
        <span>Elite: <span className="text-purple-400 font-semibold">{b.elite_leaders_count}</span></span>
        <span>Strong: <span className="text-blue-400 font-semibold">{b.strong_structure_count}</span></span>
        <span>NH/NL: <span className="text-gray-300 font-semibold">{fmt(b.nh_nl_ratio, 2)}</span></span>
        <span>A/D: <span className="text-gray-300 font-semibold">{fmt(b.ad_ratio, 2)}</span></span>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function TechnicalPage() {
  const [data, setData] = useState<TechnicalDashboardOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [classTab, setClassTab] = useState("");
  const [sortBy, setSortBy] = useState("conviction_score");
  const [search, setSearch] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [patternFilter, setPatternFilter] = useState(false);
  const [minRS, setMinRS] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ sort_by: sortBy, limit: "100" });
      if (classTab) params.set("classification", classTab);
      if (signalFilter) params.set("signal", signalFilter);
      if (stageFilter) params.set("stage", stageFilter);
      if (patternFilter) params.set("has_pattern", "true");
      if (minRS) params.set("min_rs_rating", minRS);
      const res = await fetch(`/api/v1/technical/dashboard?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [classTab, sortBy, signalFilter, stageFilter, patternFilter, minRS]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const filtered = (data?.items ?? []).filter((r) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      r.company_name.toLowerCase().includes(q) ||
      (r.symbol_nse ?? "").toLowerCase().includes(q) ||
      (r.sector ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Technical AI Scanner</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Minervini · Stage Analysis · RS Ratings · Breakout Detection
            </p>
          </div>
          <div className="flex items-center gap-3">
            {data?.unread_alerts != null && data.unread_alerts > 0 && (
              <span className="flex items-center gap-1.5 text-sm text-red-300 bg-red-900/40 border border-red-500/40 px-3 py-1.5 rounded-lg">
                <span className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
                {data.unread_alerts} alert{data.unread_alerts > 1 ? "s" : ""}
              </span>
            )}
            <button
              onClick={fetchData}
              className="text-sm px-3 py-1.5 rounded-lg border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Summary stat chips */}
        {data && (
          <div className="flex gap-3 mt-4">
            {[
              { label: "Total Universe", value: data.total, color: "text-gray-300" },
              { label: "Elite Leaders", value: data.elite_leaders, color: "text-purple-400" },
              { label: "Strong Structure", value: data.strong_structure, color: "text-blue-400" },
              { label: "Emerging Leaders", value: data.emerging_leaders, color: "text-cyan-400" },
            ].map((s) => (
              <div key={s.label} className="rounded-lg border border-gray-800 bg-gray-900 px-4 py-2.5 text-center min-w-[100px]">
                <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-[10px] text-gray-500 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-6">
        {/* Left: main content */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Classification tabs */}
          <div className="flex gap-1 border-b border-gray-800 pb-0">
            {CLASS_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setClassTab(t.key)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                  classTab === t.key
                    ? "border-blue-500 text-blue-400 bg-blue-900/20"
                    : "border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40"
                }`}
              >
                {t.value}
              </button>
            ))}
          </div>

          {/* Filters row */}
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              placeholder="Search company / symbol…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 rounded-lg border border-gray-700 bg-gray-800 px-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 w-52"
            />
            <select
              value={signalFilter}
              onChange={(e) => setSignalFilter(e.target.value)}
              className="h-8 rounded-lg border border-gray-700 bg-gray-800 px-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Signals</option>
              {["STRONG_BUY", "BUY", "ACCUMULATION", "HOLD", "REDUCE", "SELL", "AVOID"].map((s) => (
                <option key={s} value={s}>{SIGNAL_CONFIG[s]?.label ?? s}</option>
              ))}
            </select>
            <select
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
              className="h-8 rounded-lg border border-gray-700 bg-gray-800 px-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Stages</option>
              {[1, 2, 3, 4].map((s) => (
                <option key={s} value={String(s)}>Stage {s}</option>
              ))}
            </select>
            <input
              type="number"
              placeholder="Min RS (e.g. 80)"
              value={minRS}
              onChange={(e) => setMinRS(e.target.value)}
              className="h-8 w-36 rounded-lg border border-gray-700 bg-gray-800 px-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <label className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-gray-700 bg-gray-800 text-sm text-gray-300 cursor-pointer hover:border-gray-500">
              <input
                type="checkbox"
                checked={patternFilter}
                onChange={(e) => setPatternFilter(e.target.checked)}
                className="accent-blue-500"
              />
              Has Pattern
            </label>
            {/* Sort */}
            <div className="flex gap-1 ml-auto">
              {SORT_OPTIONS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setSortBy(s.key)}
                  className={`h-8 px-3 text-xs rounded-lg border transition-colors ${
                    sortBy === s.key
                      ? "border-blue-500 bg-blue-900/30 text-blue-400"
                      : "border-gray-700 bg-gray-800 text-gray-400 hover:text-gray-200"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div className="flex items-center justify-center h-40 text-gray-500">Loading…</div>
          ) : error ? (
            <div className="flex items-center justify-center h-40 text-red-400">{error}</div>
          ) : (
            <div className="rounded-xl border border-gray-800 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 bg-gray-900/80">
                    <th className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">#</th>
                    <th className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Company</th>
                    <th className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Class · Stage</th>
                    <th className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Signal</th>
                    <th className="text-right px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">CMP</th>
                    <th className="text-right px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Upside</th>
                    <th className="text-right px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">R/R</th>
                    <th className="px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Tech Score</th>
                    <th className="px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">RS Rating</th>
                    <th className="px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Minervini</th>
                    <th className="text-left px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Pattern</th>
                    <th className="text-right px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Pos%</th>
                    <th className="text-right px-3 py-2.5 text-xs text-gray-400 font-medium whitespace-nowrap">Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={13} className="text-center py-10 text-gray-500">No stocks match the current filters</td>
                    </tr>
                  )}
                  {filtered.map((row, idx) => {
                    const cls = CLASS_CONFIG[row.classification] ?? CLASS_CONFIG["WATCHLIST"];
                    const sig = SIGNAL_CONFIG[row.signal] ?? SIGNAL_CONFIG["HOLD"];
                    const scoreColor =
                      (row.technical_score ?? 0) >= 80 ? "bg-purple-500" :
                      (row.technical_score ?? 0) >= 65 ? "bg-blue-500" :
                      (row.technical_score ?? 0) >= 50 ? "bg-teal-500" : "bg-gray-600";
                    const rsColor =
                      (row.rs_rating ?? 0) >= 80 ? "bg-emerald-500" :
                      (row.rs_rating ?? 0) >= 60 ? "bg-teal-500" : "bg-gray-600";
                    return (
                      <tr
                        key={row.isin}
                        onClick={() => (window.location.href = `/technical/${row.isin}`)}
                        className="border-b border-gray-800/60 hover:bg-gray-800/40 cursor-pointer transition-colors"
                      >
                        <td className="px-3 py-2.5 text-gray-500 text-xs">{idx + 1}</td>
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-2">
                            {row.unread_alert_count > 0 && (
                              <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                            )}
                            <div>
                              <div className="font-semibold text-white text-sm">{row.symbol_nse ?? row.isin}</div>
                              <div className="text-[11px] text-gray-400 truncate max-w-[140px]">{row.company_name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${cls.bg} ${cls.color}`}>
                              {cls.label.split(" ")[0]}
                            </span>
                            <StageBadge stage={row.stage} />
                          </div>
                          {row.sector && (
                            <div className="text-[10px] text-gray-500 mt-0.5 truncate max-w-[120px]">{row.sector}</div>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${sig.color}`}>
                            {sig.label}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-sm text-gray-200">
                          {row.cmp != null ? `₹${row.cmp.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <span className={`text-sm font-semibold ${(row.expected_upside_pct ?? 0) > 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {row.expected_upside_pct != null ? `${row.expected_upside_pct > 0 ? "+" : ""}${row.expected_upside_pct.toFixed(1)}%` : "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right text-gray-300 font-mono text-sm">
                          {row.risk_reward_ratio != null ? `${row.risk_reward_ratio.toFixed(1)}x` : "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <ScoreBar value={row.technical_score} color={scoreColor} />
                        </td>
                        <td className="px-3 py-2.5">
                          <ScoreBar value={row.rs_rating} color={rsColor} />
                        </td>
                        <td className="px-3 py-2.5">
                          <MinerviniBars count={row.minervini_count} />
                        </td>
                        <td className="px-3 py-2.5">
                          {row.active_pattern ? (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-900/50 border border-indigo-500/40 text-indigo-300">
                              {PATTERN_LABELS[row.active_pattern] ?? row.active_pattern}
                            </span>
                          ) : (
                            <span className="text-gray-600 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right text-gray-300 text-sm">
                          {row.position_size_pct != null ? `${row.position_size_pct.toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-right text-gray-400 text-xs">
                          {row.market_leader_rank != null ? `#${row.market_leader_rank}` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right sidebar: breadth + sector rankings */}
        <div className="w-72 flex-shrink-0 space-y-4">
          {data?.market_breadth && <BreadthPanel b={data.market_breadth} />}

          {/* Sector Rankings (top_sectors from breadth) */}
          {data?.market_breadth?.top_sectors && (
            <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
              <h3 className="text-sm font-semibold text-gray-200 mb-3">Sector RS Rankings</h3>
              <div className="space-y-2">
                {Object.entries(data.market_breadth.top_sectors)
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .map(([sector, score], i) => (
                  <div key={sector} className="flex items-center gap-2">
                    <span className="text-[10px] text-gray-500 w-4 text-right">{i + 1}</span>
                    <span className="text-[11px] text-gray-300 flex-1 truncate">{sector}</span>
                    <span className="text-[11px] font-semibold text-purple-400">{Math.round(Number(score))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick legend */}
          <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Classification</h3>
            <div className="space-y-1.5">
              {Object.entries(CLASS_CONFIG).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${v.bg} ${v.color}`}>
                    {k.split("_")[0]}
                  </span>
                  <span className="text-[11px] text-gray-400">{v.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

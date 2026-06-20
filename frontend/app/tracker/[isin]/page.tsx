"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

/* ── Types ──────────────────────────────────────────────────────────────────── */
interface QuarterlyRow {
  fiscal_year: number;
  quarter: string;
  target?: {
    expected_revenue_cr?: number;
    expected_ebitda_cr?: number;
    expected_ebitda_margin?: number;
    expected_pat_cr?: number;
    expected_order_book_cr?: number;
    mgmt_revenue_guidance?: number;
    mgmt_margin_guidance?: number;
  };
  actual?: {
    revenue_cr?: number;
    ebitda_cr?: number;
    ebitda_margin?: number;
    pat_cr?: number;
    order_book_cr?: number;
    capex_cr?: number;
    promoter_holding_pct?: number;
    promoter_pledged_pct?: number;
    revenue_yoy_pct?: number;
    pat_yoy_pct?: number;
    mgmt_commentary?: string;
  };
  comparison?: {
    revenue_signal: string;
    ebitda_signal: string;
    margin_signal: string;
    pat_signal: string;
    order_book_signal: string;
    guidance_signal: string;
    promoter_signal: string;
    overall_signal: string;
    verdict: string;
    beat_count: number;
    miss_count: number;
    in_line_count: number;
    revenue_beat_pct?: number;
    ebitda_beat_pct?: number;
    margin_delta_bps?: number;
    pat_beat_pct?: number;
    ai_summary?: string;
  };
}

interface CompanyDetail {
  stock: {
    isin: string; symbol_nse?: string; company_name: string; sector?: string;
    market_cap_cr?: number; market_cap_cat?: string; cmp?: number;
    target_price_12m?: number; upside_pct?: number; expected_cagr_3y?: number;
    rating: string; overall_signal: string; risk_reward_score?: number;
    conviction_score?: number; technical_trend?: string; technical_score?: number;
    consecutive_red: number; tags?: string[];
  };
  thesis?: {
    thesis_text?: string;
    growth_drivers?: string[];
    key_risks?: string[];
    moat?: string;
    management_quality?: string;
    expected_revenue_cagr_3y?: number;
    expected_ebitda_margin?: number;
    expected_pat_cagr_3y?: number;
    expected_pe_entry?: number;
    expected_pe_exit?: number;
    bull_case?: Record<string, string>;
    base_case?: Record<string, string>;
    bear_case?: Record<string, string>;
  };
  scenarios?: Array<{
    scenario_type: string; target_price?: number; expected_cagr?: number;
    probability?: number; description?: string; key_triggers?: string[];
    key_risks?: string[];
  }>;
  quarterly_history?: QuarterlyRow[];
  recent_alerts?: Array<{
    id: string; alert_type: string; severity: string; title?: string;
    description?: string; triggered_at: string; is_read: boolean; is_actioned: boolean;
    fiscal_year?: number; quarter?: string;
  }>;
  latest_technical?: {
    snapshot_date: string; close_price?: number; sma_50?: number; sma_200?: number;
    rsi_14?: number; above_sma_50?: boolean; above_sma_200?: boolean;
    golden_cross?: boolean; death_cross?: boolean;
    pct_from_52w_high?: number; pct_from_52w_low?: number;
    trend?: string; technical_score?: number;
  };
  promoter_history?: Array<{
    fiscal_year: number; quarter: string;
    promoter_holding_pct?: number; promoter_pledged_pct?: number;
    fii_pct?: number; promoter_change_pct?: number;
    pledged_change_pct?: number; signal: string;
  }>;
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */
const SIG_CLASSES: Record<string, { bg: string; text: string; border: string }> = {
  GREEN:  { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300" },
  YELLOW: { bg: "bg-amber-50",   text: "text-amber-700",   border: "border-amber-300"   },
  RED:    { bg: "bg-red-50",     text: "text-red-700",     border: "border-red-300"     },
  NA:     { bg: "bg-gray-50",    text: "text-gray-400",    border: "border-gray-200"    },
};

function SigBadge({ sig, compact }: { sig: string; compact?: boolean }) {
  const c = SIG_CLASSES[sig] || SIG_CLASSES.NA;
  const icons: Record<string, string> = { GREEN: "●", YELLOW: "●", RED: "●", NA: "–" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
      {icons[sig]} {compact ? "" : sig}
    </span>
  );
}

function fmt(v?: number | null, prefix = "", suffix = "", decimals = 0) {
  if (v == null) return "—";
  return `${prefix}${v.toLocaleString("en-IN", { maximumFractionDigits: decimals })}${suffix}`;
}

function BeatPct({ val }: { val?: number }) {
  if (val == null) return <span className="text-gray-300">—</span>;
  const color = val >= 2 ? "text-emerald-600" : val <= -3 ? "text-red-500" : "text-amber-600";
  return <span className={`text-xs font-medium ${color}`}>{val > 0 ? "+" : ""}{val.toFixed(1)}%</span>;
}

const SCENARIO_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  BULL: { bg: "bg-emerald-50", border: "border-emerald-200", label: "🐂 Bull Case" },
  BASE: { bg: "bg-blue-50",    border: "border-blue-200",    label: "📊 Base Case" },
  BEAR: { bg: "bg-red-50",     border: "border-red-200",     label: "🐻 Bear Case" },
};

function ScenarioCard({ s }: { s: NonNullable<CompanyDetail["scenarios"]>[0] }) {
  const cfg = SCENARIO_COLORS[s.scenario_type] || { bg: "bg-gray-50", border: "border-gray-200", label: s.scenario_type };
  return (
    <div className={`rounded-xl border p-4 ${cfg.bg} ${cfg.border}`}>
      <div className="font-semibold text-gray-800 mb-2 text-sm">{cfg.label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600 mb-3">
        <div>Target: <span className="font-semibold text-gray-900">{fmt(s.target_price, "₹")}</span></div>
        <div>CAGR: <span className="font-semibold text-gray-900">{fmt(s.expected_cagr, "", "%")}</span></div>
        <div>Probability: <span className="font-semibold text-gray-900">{s.probability != null ? `${(s.probability * 100).toFixed(0)}%` : "—"}</span></div>
      </div>
      {s.description && <p className="text-xs text-gray-600 mb-2">{s.description}</p>}
      {s.key_triggers && s.key_triggers.length > 0 && (
        <div className="text-xs">
          <div className="font-medium text-gray-700 mb-1">Triggers:</div>
          <ul className="space-y-0.5">
            {s.key_triggers.map((t, i) => <li key={i} className="flex gap-1"><span className="text-emerald-500">✓</span>{t}</li>)}
          </ul>
        </div>
      )}
      {s.key_risks && s.key_risks.length > 0 && (
        <div className="text-xs mt-2">
          <div className="font-medium text-gray-700 mb-1">Risks:</div>
          <ul className="space-y-0.5">
            {s.key_risks.map((r, i) => <li key={i} className="flex gap-1"><span className="text-red-400">✕</span>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────────────────── */
const METRICS = [
  { key: "revenue_signal",    label: "Revenue",          beatKey: "revenue_beat_pct",  isBps: false },
  { key: "ebitda_signal",     label: "EBITDA",           beatKey: "ebitda_beat_pct",   isBps: false },
  { key: "margin_signal",     label: "Margin",           beatKey: "margin_delta_bps",  isBps: true  },
  { key: "pat_signal",        label: "PAT",              beatKey: "pat_beat_pct",      isBps: false },
  { key: "order_book_signal", label: "Order Book",       beatKey: null,                isBps: false },
  { key: "guidance_signal",   label: "Guidance",         beatKey: null,                isBps: false },
  { key: "promoter_signal",   label: "Promoter Holding", beatKey: null,                isBps: false },
  { key: "overall_signal",    label: "Overall",          beatKey: null,                isBps: false },
];

const SEVERITY_COLORS: Record<string, string> = {
  HIGH:   "bg-red-100 text-red-700 border-red-200",
  MEDIUM: "bg-orange-100 text-orange-700 border-orange-200",
  LOW:    "bg-blue-100 text-blue-700 border-blue-200",
};

type TabKey = "overview" | "quarterly" | "thesis" | "scenarios" | "technicals" | "alerts";

export default function TrackerDetailPage() {
  const { isin } = useParams<{ isin: string }>();
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>("overview");
  const [markingAlerts, setMarkingAlerts] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch(`/api/v1/tracker/${isin}`)
      .then(r => r.json())
      .then(d => { setDetail(d); setLoading(false); });
  }, [isin]);

  const markAlert = async (id: string) => {
    setMarkingAlerts(p => new Set(p).add(id));
    await fetch(`/api/v1/tracker/alerts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_read: true }),
    });
    setDetail(d => d ? {
      ...d,
      recent_alerts: d.recent_alerts?.map(a => a.id === id ? { ...a, is_read: true } : a)
    } : d);
    setMarkingAlerts(p => { const n = new Set(p); n.delete(id); return n; });
  };

  if (loading) return <div className="text-center py-32 text-gray-400">Loading…</div>;
  if (!detail) return <div className="text-center py-32 text-red-400">Company not found.</div>;

  const { stock, thesis, scenarios = [], quarterly_history = [], recent_alerts = [], latest_technical, promoter_history = [] } = detail;
  const sigCfg = SIG_CLASSES[stock.overall_signal] || SIG_CLASSES.NA;
  const TABS: { key: TabKey; label: string }[] = [
    { key: "overview",   label: "Overview"   },
    { key: "quarterly",  label: "Quarterly"  },
    { key: "thesis",     label: "Thesis"     },
    { key: "scenarios",  label: "Scenarios"  },
    { key: "technicals", label: "Technicals" },
    { key: "alerts",     label: `Alerts ${recent_alerts.filter(a => !a.is_read).length > 0 ? `(${recent_alerts.filter(a => !a.is_read).length})` : ""}` },
  ];

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Back */}
      <a href="/tracker" className="text-sm text-indigo-600 hover:underline mb-4 inline-block">← Back to Tracker</a>

      {/* Company header */}
      <div className={`rounded-2xl border p-5 mb-6 ${sigCfg.bg} ${sigCfg.border.replace("border-", "border-l-4 border-l-").replace("300", "500")} border border-gray-200`}>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-xl font-bold text-gray-900">{stock.company_name}</h1>
              {stock.symbol_nse && <span className="text-sm bg-gray-800 text-white px-2 py-0.5 rounded font-mono">{stock.symbol_nse}</span>}
              <SigBadge sig={stock.overall_signal} />
              {stock.consecutive_red >= 2 && (
                <span className="text-xs bg-red-100 text-red-700 border border-red-300 px-2 py-0.5 rounded-full font-medium">
                  ⚠ {stock.consecutive_red}× Red
                </span>
              )}
            </div>
            <div className="text-sm text-gray-500">{stock.sector} · {stock.market_cap_cat} Cap · {fmt(stock.market_cap_cr, "₹", " Cr")}</div>
          </div>
          <div className="grid grid-cols-3 gap-4 text-right">
            <div>
              <div className="text-xs text-gray-400 uppercase">CMP</div>
              <div className="text-lg font-bold text-gray-900">{fmt(stock.cmp, "₹")}</div>
              <div className="text-xs text-gray-500">Target: {fmt(stock.target_price_12m, "₹")}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 uppercase">Upside</div>
              <div className={`text-lg font-bold ${(stock.upside_pct || 0) > 0 ? "text-emerald-600" : "text-red-500"}`}>
                {stock.upside_pct != null ? `${stock.upside_pct > 0 ? "+" : ""}${stock.upside_pct.toFixed(1)}%` : "—"}
              </div>
              <div className="text-xs text-gray-500">CAGR: {fmt(stock.expected_cagr_3y, "", "%")}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 uppercase">Risk / Reward</div>
              <div className={`text-lg font-bold ${(stock.risk_reward_score || 0) >= 7 ? "text-emerald-600" : (stock.risk_reward_score || 0) >= 5 ? "text-amber-600" : "text-red-500"}`}>
                {stock.risk_reward_score?.toFixed(1) || "—"}/10
              </div>
              <div className="text-xs text-gray-500">Rating: {stock.rating.replace("_", " ")}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${tab === t.key ? "bg-white border border-b-white border-gray-200 text-indigo-600 -mb-px" : "text-gray-500 hover:text-gray-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────────── */}
      {tab === "overview" && (
        <div className="grid grid-cols-3 gap-5">
          {/* Thesis summary */}
          <div className="col-span-2 rounded-xl border border-gray-200 bg-white p-5">
            <h3 className="font-semibold text-gray-800 mb-3">Investment Thesis</h3>
            {thesis?.thesis_text ? (
              <p className="text-sm text-gray-700 leading-relaxed">{thesis.thesis_text}</p>
            ) : (
              <p className="text-sm text-gray-400 italic">No thesis on file.</p>
            )}
            {thesis?.growth_drivers && thesis.growth_drivers.length > 0 && (
              <div className="mt-4">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Growth Drivers</div>
                <ul className="space-y-1">
                  {thesis.growth_drivers.map((d, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700"><span className="text-emerald-500 mt-0.5">✓</span>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {thesis?.key_risks && thesis.key_risks.length > 0 && (
              <div className="mt-4">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Key Risks</div>
                <ul className="space-y-1">
                  {thesis.key_risks.map((r, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700"><span className="text-red-400 mt-0.5">⚠</span>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Quick metrics */}
          <div className="space-y-3">
            {thesis && (
              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h4 className="text-xs font-semibold text-gray-400 uppercase mb-3">Expected Metrics</h4>
                <div className="space-y-2 text-sm">
                  {[
                    ["Rev CAGR 3Y", fmt(thesis.expected_revenue_cagr_3y, "", "%")],
                    ["EBITDA Margin", fmt(thesis.expected_ebitda_margin, "", "%")],
                    ["PAT CAGR 3Y",  fmt(thesis.expected_pat_cagr_3y, "", "%")],
                    ["Entry PE",     fmt(thesis.expected_pe_entry, "", "x")],
                    ["Exit PE",      fmt(thesis.expected_pe_exit, "", "x")],
                    ["Moat",         thesis.moat || "—"],
                    ["Mgmt Quality", thesis.management_quality || "—"],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-500">{k}</span>
                      <span className="font-medium text-gray-800">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {latest_technical && (
              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h4 className="text-xs font-semibold text-gray-400 uppercase mb-3">Technical</h4>
                <div className="space-y-1.5 text-sm">
                  {[
                    ["Trend",           latest_technical.trend || "—"],
                    ["Score",           fmt(latest_technical.technical_score, "", "/100")],
                    ["RSI(14)",         fmt(latest_technical.rsi_14, "", "", 1)],
                    ["SMA50",           fmt(latest_technical.sma_50, "₹", "", 0)],
                    ["SMA200",          fmt(latest_technical.sma_200, "₹", "", 0)],
                    ["From 52W High",   fmt(latest_technical.pct_from_52w_high, "", "%", 1)],
                    ["Golden Cross",    latest_technical.golden_cross ? "✓ Yes" : latest_technical.death_cross ? "✕ Death Cross" : "No"],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-500">{k}</span>
                      <span className="font-medium text-gray-800">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Quarterly ─────────────────────────────────────────────────────────── */}
      {tab === "quarterly" && (
        <div>
          {quarterly_history.length === 0 ? (
            <div className="text-center py-16 text-gray-400">No quarterly data yet.</div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-400 uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left sticky left-0 bg-gray-50">Quarter</th>
                    {METRICS.map(m => (
                      <th key={m.key} className="px-3 py-3 text-center whitespace-nowrap">{m.label}</th>
                    ))}
                    <th className="px-4 py-3 text-center">Beat/Miss</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {quarterly_history.map((row) => {
                    const c = row.comparison;
                    const quarterLabel = `${row.quarter} FY${row.fiscal_year}`;
                    return (
                      <tr key={quarterLabel} className="hover:bg-gray-50/50">
                        <td className="px-4 py-3 font-medium text-gray-700 sticky left-0 bg-white whitespace-nowrap">{quarterLabel}</td>
                        {METRICS.map(m => {
                          const sig = (c as Record<string, string> | undefined)?.[m.key] || "NA";
                          const beatVal = m.beatKey ? (c as Record<string, number> | undefined)?.[m.beatKey] : null;
                          const sigCls = SIG_CLASSES[sig] || SIG_CLASSES.NA;
                          return (
                            <td key={m.key} className="px-3 py-3 text-center">
                              <div className="flex flex-col items-center gap-0.5">
                                <span className={`inline-block w-2.5 h-2.5 rounded-full ${sig === "GREEN" ? "bg-emerald-500" : sig === "RED" ? "bg-red-500" : sig === "YELLOW" ? "bg-amber-400" : "bg-gray-200"}`} />
                                {m.beatKey && beatVal != null && (
                                  <span className={`text-xs ${(beatVal) > 0 ? "text-emerald-600" : "text-red-500"}`}>
                                    {m.isBps ? `${beatVal > 0 ? "+" : ""}${beatVal.toFixed(0)}bps` : `${beatVal > 0 ? "+" : ""}${beatVal.toFixed(1)}%`}
                                  </span>
                                )}
                                {/* Show expected vs actual in tooltip-like sub-text */}
                                {m.key === "revenue_signal" && row.actual?.revenue_cr != null && (
                                  <span className="text-xs text-gray-400">₹{row.actual.revenue_cr.toFixed(0)}Cr</span>
                                )}
                              </div>
                            </td>
                          );
                        })}
                        <td className="px-4 py-3 text-center">
                          {c ? (
                            <span className="text-xs">
                              <span className="text-emerald-600 font-bold">{c.beat_count}B</span>
                              {" / "}
                              <span className="text-gray-400">{c.in_line_count}I</span>
                              {" / "}
                              <span className="text-red-500 font-bold">{c.miss_count}M</span>
                            </span>
                          ) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Expanded detail for latest quarter */}
          {quarterly_history[0]?.comparison?.ai_summary && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5">
              <div className="text-sm font-semibold text-gray-700 mb-2">AI Summary — {quarterly_history[0].quarter} FY{quarterly_history[0].fiscal_year}</div>
              <p className="text-sm text-gray-600 leading-relaxed">{quarterly_history[0].comparison.ai_summary}</p>
            </div>
          )}

          {/* Expected vs actual table for latest quarter */}
          {quarterly_history[0] && (quarterly_history[0].target || quarterly_history[0].actual) && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="bg-gray-50 px-5 py-3 text-sm font-semibold text-gray-700 border-b border-gray-200">
                Latest Quarter Detail — {quarterly_history[0].quarter} FY{quarterly_history[0].fiscal_year}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-gray-400 uppercase">
                    <tr>
                      <th className="px-5 py-2 text-left">Metric</th>
                      <th className="px-5 py-2 text-right">Expected</th>
                      <th className="px-5 py-2 text-right">Actual</th>
                      <th className="px-5 py-2 text-center">Signal</th>
                      <th className="px-5 py-2 text-right">Delta</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {[
                      { label: "Revenue (Cr)", exp: quarterly_history[0].target?.expected_revenue_cr, act: quarterly_history[0].actual?.revenue_cr, sig: quarterly_history[0].comparison?.revenue_signal, beat: quarterly_history[0].comparison?.revenue_beat_pct, isBps: false },
                      { label: "EBITDA (Cr)",  exp: quarterly_history[0].target?.expected_ebitda_cr,  act: quarterly_history[0].actual?.ebitda_cr,  sig: quarterly_history[0].comparison?.ebitda_signal,  beat: quarterly_history[0].comparison?.ebitda_beat_pct,  isBps: false },
                      { label: "EBITDA Margin", exp: quarterly_history[0].target?.expected_ebitda_margin, act: quarterly_history[0].actual?.ebitda_margin, sig: quarterly_history[0].comparison?.margin_signal, beat: quarterly_history[0].comparison?.margin_delta_bps, isBps: true },
                      { label: "PAT (Cr)",     exp: quarterly_history[0].target?.expected_pat_cr,     act: quarterly_history[0].actual?.pat_cr,     sig: quarterly_history[0].comparison?.pat_signal,     beat: quarterly_history[0].comparison?.pat_beat_pct,     isBps: false },
                      { label: "Order Book (Cr)", exp: quarterly_history[0].target?.expected_order_book_cr, act: quarterly_history[0].actual?.order_book_cr, sig: quarterly_history[0].comparison?.order_book_signal, beat: null, isBps: false },
                      { label: "Mgmt Rev. Guidance", exp: quarterly_history[0].target?.mgmt_revenue_guidance, act: null, sig: quarterly_history[0].comparison?.guidance_signal, beat: null, isBps: false },
                      { label: "Promoter Holding", exp: null, act: quarterly_history[0].actual?.promoter_holding_pct, sig: quarterly_history[0].comparison?.promoter_signal, beat: null, isBps: false },
                    ].map(row => (
                      <tr key={row.label} className="hover:bg-gray-50/30">
                        <td className="px-5 py-2.5 text-gray-700">{row.label}</td>
                        <td className="px-5 py-2.5 text-right text-gray-600">{row.exp != null ? row.exp.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}</td>
                        <td className="px-5 py-2.5 text-right font-medium text-gray-900">{row.act != null ? row.act.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}</td>
                        <td className="px-5 py-2.5 text-center"><SigBadge sig={row.sig || "NA"} compact /></td>
                        <td className="px-5 py-2.5 text-right">
                          {row.beat != null ? (
                            <span className={`text-xs font-medium ${row.beat > 0 ? "text-emerald-600" : "text-red-500"}`}>
                              {row.beat > 0 ? "+" : ""}{row.beat.toFixed(row.isBps ? 0 : 1)}{row.isBps ? "bps" : "%"}
                            </span>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {quarterly_history[0].actual?.mgmt_commentary && (
                <div className="px-5 py-3 border-t border-gray-100 text-xs text-gray-600 leading-relaxed bg-gray-50">
                  <span className="font-medium text-gray-700">Mgmt Commentary:</span> {quarterly_history[0].actual.mgmt_commentary}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Thesis ────────────────────────────────────────────────────────────── */}
      {tab === "thesis" && (
        <div className="space-y-5">
          {!thesis ? (
            <div className="text-center py-16 text-gray-400">No thesis on file.</div>
          ) : (
            <>
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h3 className="font-semibold text-gray-800 mb-3">Full Thesis</h3>
                <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{thesis.thesis_text || "—"}</p>
              </div>
              <div className="grid grid-cols-2 gap-5">
                <div className="rounded-xl border border-gray-200 bg-white p-5">
                  <h4 className="font-semibold text-gray-700 mb-3 text-sm">Growth Drivers</h4>
                  <ul className="space-y-2">
                    {(thesis.growth_drivers || []).map((d, i) => (
                      <li key={i} className="flex gap-2 text-sm text-gray-700"><span className="text-emerald-500">✓</span>{d}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl border border-gray-200 bg-white p-5">
                  <h4 className="font-semibold text-gray-700 mb-3 text-sm">Key Risks</h4>
                  <ul className="space-y-2">
                    {(thesis.key_risks || []).map((r, i) => (
                      <li key={i} className="flex gap-2 text-sm text-gray-700"><span className="text-red-400">⚠</span>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h4 className="font-semibold text-gray-700 mb-3 text-sm">Expected Financials</h4>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  {[
                    ["Revenue CAGR (3Y)", fmt(thesis.expected_revenue_cagr_3y, "", "%", 1)],
                    ["EBITDA Margin Target", fmt(thesis.expected_ebitda_margin, "", "%", 1)],
                    ["PAT CAGR (3Y)", fmt(thesis.expected_pat_cagr_3y, "", "%", 1)],
                    ["Entry PE", fmt(thesis.expected_pe_entry, "", "x", 1)],
                    ["Exit PE", fmt(thesis.expected_pe_exit, "", "x", 1)],
                    ["Moat", thesis.moat || "—"],
                    ["Mgmt Quality", thesis.management_quality || "—"],
                  ].map(([k, v]) => (
                    <div key={k} className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">{k}</div>
                      <div className="font-semibold text-gray-800">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Scenarios ─────────────────────────────────────────────────────────── */}
      {tab === "scenarios" && (
        <div>
          {scenarios.length === 0 ? (
            <div className="text-center py-16 text-gray-400">No scenarios on file.</div>
          ) : (
            <div className="grid grid-cols-3 gap-5">
              {["BULL", "BASE", "BEAR"].map(type => {
                const s = scenarios.find(x => x.scenario_type === type);
                return s ? <ScenarioCard key={type} s={s} /> : (
                  <div key={type} className="rounded-xl border border-dashed border-gray-200 p-8 text-center text-gray-300 text-sm">
                    No {type.toLowerCase()} case
                  </div>
                );
              })}
            </div>
          )}

          {/* Bull/Base/Bear table from thesis */}
          {thesis && (thesis.bull_case || thesis.base_case || thesis.bear_case) && (
            <div className="mt-6 rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="bg-gray-50 px-5 py-3 text-sm font-semibold text-gray-700 border-b">Scenario Parameters</div>
              <div className="grid grid-cols-3 divide-x divide-gray-100">
                {(["Bull", "Base", "Bear"] as const).map((label) => {
                  const cas = label === "Bull" ? thesis.bull_case : label === "Base" ? thesis.base_case : thesis.bear_case;
                  return (
                  <div key={label} className="p-5">
                    <div className={`text-sm font-semibold mb-3 ${label === "Bull" ? "text-emerald-600" : label === "Base" ? "text-blue-600" : "text-red-500"}`}>
                      {label} Case
                    </div>
                    {cas && Object.entries(cas as Record<string, string>).map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs py-1 border-b border-gray-50">
                        <span className="text-gray-500 capitalize">{k.replace(/_/g, " ")}</span>
                        <span className="font-medium text-gray-800">{v}</span>
                      </div>
                    ))}
                  </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Technicals ────────────────────────────────────────────────────────── */}
      {tab === "technicals" && (
        <div className="space-y-5">
          {latest_technical ? (
            <>
              <div className="grid grid-cols-4 gap-4">
                {[
                  { label: "Trend", value: latest_technical.trend || "—", color: latest_technical.trend === "UPTREND" ? "text-emerald-600" : latest_technical.trend === "DOWNTREND" ? "text-red-500" : "text-amber-600" },
                  { label: "Tech Score", value: `${latest_technical.technical_score?.toFixed(0) || "—"}/100`, color: (latest_technical.technical_score || 0) >= 65 ? "text-emerald-600" : (latest_technical.technical_score || 0) >= 40 ? "text-amber-600" : "text-red-500" },
                  { label: "RSI (14)", value: latest_technical.rsi_14?.toFixed(1) || "—", color: (latest_technical.rsi_14 || 0) > 70 ? "text-red-500" : (latest_technical.rsi_14 || 0) < 30 ? "text-emerald-600" : "text-gray-800" },
                  { label: "From 52W High", value: fmt(latest_technical.pct_from_52w_high, "", "%", 1), color: (latest_technical.pct_from_52w_high || 0) > -10 ? "text-emerald-600" : "text-red-500" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded-xl border border-gray-200 bg-white p-4 text-center">
                    <div className="text-xs text-gray-400 uppercase mb-1">{label}</div>
                    <div className={`text-2xl font-bold ${color}`}>{value}</div>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h4 className="font-semibold text-gray-700 mb-4 text-sm">Moving Averages</h4>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  {[
                    ["SMA 20", latest_technical.sma_20],
                    ["SMA 50", latest_technical.sma_50],
                    ["SMA 200", latest_technical.sma_200],
                  ].map(([label, val]) => (
                    <div key={label as string} className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">{label as string}</div>
                      <div className="font-bold text-gray-800">{val != null ? `₹${(val as number).toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}</div>
                      {latest_technical.close_price && val != null && (
                        <div className={`text-xs mt-0.5 ${latest_technical.close_price > (val as number) ? "text-emerald-500" : "text-red-400"}`}>
                          {latest_technical.close_price > (val as number) ? "Above" : "Below"}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className={`flex items-center gap-2 rounded-lg p-3 ${latest_technical.golden_cross ? "bg-emerald-50 border border-emerald-200" : "bg-gray-50 border border-gray-100"}`}>
                    <span className={latest_technical.golden_cross ? "text-emerald-500 text-lg" : "text-gray-300 text-lg"}>⭐</span>
                    <div>
                      <div className="font-medium text-gray-700">Golden Cross</div>
                      <div className="text-xs text-gray-400">{latest_technical.golden_cross ? "Active — bullish" : "Not active"}</div>
                    </div>
                  </div>
                  <div className={`flex items-center gap-2 rounded-lg p-3 ${latest_technical.death_cross ? "bg-red-50 border border-red-200" : "bg-gray-50 border border-gray-100"}`}>
                    <span className={latest_technical.death_cross ? "text-red-500 text-lg" : "text-gray-300 text-lg"}>☠</span>
                    <div>
                      <div className="font-medium text-gray-700">Death Cross</div>
                      <div className="text-xs text-gray-400">{latest_technical.death_cross ? "Active — bearish" : "Not active"}</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-16 text-gray-400">No technical data.</div>
          )}

          {/* Promoter history */}
          {promoter_history.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
              <div className="bg-gray-50 px-5 py-3 text-sm font-semibold text-gray-700 border-b">Promoter Holding History</div>
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-400 uppercase">
                  <tr>
                    <th className="px-5 py-2 text-left">Quarter</th>
                    <th className="px-5 py-2 text-right">Holding</th>
                    <th className="px-5 py-2 text-right">Pledged</th>
                    <th className="px-5 py-2 text-right">FII</th>
                    <th className="px-5 py-2 text-right">Change</th>
                    <th className="px-5 py-2 text-center">Signal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {promoter_history.map(p => (
                    <tr key={`${p.fiscal_year}${p.quarter}`} className="hover:bg-gray-50/30">
                      <td className="px-5 py-2.5 font-medium text-gray-700">{p.quarter} FY{p.fiscal_year}</td>
                      <td className="px-5 py-2.5 text-right">{fmt(p.promoter_holding_pct, "", "%", 2)}</td>
                      <td className="px-5 py-2.5 text-right">{fmt(p.promoter_pledged_pct, "", "%", 2)}</td>
                      <td className="px-5 py-2.5 text-right">{fmt(p.fii_pct, "", "%", 2)}</td>
                      <td className="px-5 py-2.5 text-right">
                        {p.promoter_change_pct != null ? (
                          <span className={`text-xs font-medium ${p.promoter_change_pct > 0 ? "text-emerald-600" : p.promoter_change_pct < 0 ? "text-red-500" : "text-gray-400"}`}>
                            {p.promoter_change_pct > 0 ? "+" : ""}{p.promoter_change_pct.toFixed(2)}%
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-5 py-2.5 text-center"><SigBadge sig={p.signal} compact /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Alerts ────────────────────────────────────────────────────────────── */}
      {tab === "alerts" && (
        <div className="space-y-3">
          {recent_alerts.length === 0 ? (
            <div className="text-center py-16 text-gray-400">No alerts.</div>
          ) : recent_alerts.map(alert => (
            <div key={alert.id} className={`rounded-xl border p-4 flex items-start gap-4 ${alert.is_read ? "opacity-60" : ""}`}>
              <div className={`text-xs font-semibold px-2 py-1 rounded border ${SEVERITY_COLORS[alert.severity] || "bg-gray-100 text-gray-500 border-gray-200"}`}>
                {alert.severity}
              </div>
              <div className="flex-1">
                <div className="font-medium text-gray-800 text-sm">{alert.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{alert.description}</div>
                <div className="text-xs text-gray-400 mt-1">
                  {alert.fiscal_year && `${alert.quarter} FY${alert.fiscal_year} · `}
                  {new Date(alert.triggered_at).toLocaleDateString("en-IN")}
                  {" · "}{alert.alert_type.replace(/_/g, " ")}
                </div>
              </div>
              {!alert.is_read && (
                <button
                  onClick={() => markAlert(alert.id)}
                  disabled={markingAlerts.has(alert.id)}
                  className="text-xs text-gray-400 hover:text-indigo-600 px-2 py-1 rounded border border-gray-200 hover:border-indigo-300 transition-colors shrink-0"
                >
                  Mark read
                </button>
              )}
              {alert.is_actioned && <span className="text-xs text-emerald-500 shrink-0">✓ Actioned</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

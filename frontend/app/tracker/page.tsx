"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://orderbook-api.stockmaniacs.net";

import { useEffect, useState, useCallback } from "react";

const SIGNAL_CONFIG = {
  GREEN:  { bg: "bg-emerald-50",  text: "text-emerald-700", dot: "bg-emerald-500", border: "border-emerald-200" },
  YELLOW: { bg: "bg-amber-50",    text: "text-amber-700",   dot: "bg-amber-400",   border: "border-amber-200" },
  RED:    { bg: "bg-red-50",      text: "text-red-700",     dot: "bg-red-500",     border: "border-red-200" },
  NA:     { bg: "bg-gray-50",     text: "text-gray-400",    dot: "bg-gray-300",    border: "border-gray-100" },
};

const RATING_COLORS: Record<string, string> = {
  STRONG_BUY: "text-emerald-700 bg-emerald-100",
  BUY:        "text-green-700   bg-green-100",
  HOLD:       "text-amber-700   bg-amber-100",
  SELL:       "text-red-700     bg-red-100",
  STRONG_SELL:"text-red-800     bg-red-200",
  NEUTRAL:    "text-gray-500    bg-gray-100",
};

const TREND_ICONS: Record<string, string> = {
  UPTREND:      "↑",
  DOWNTREND:    "↓",
  SIDEWAYS:     "→",
  REVERSAL_UP:  "↗",
  REVERSAL_DOWN:"↘",
};

interface DashboardItem {
  isin: string;
  symbol_nse: string | null;
  company_name: string;
  sector: string | null;
  market_cap_cr: number | null;
  market_cap_cat: string | null;
  cmp: number | null;
  target_price_12m: number | null;
  upside_pct: number | null;
  expected_cagr_3y: number | null;
  rating: string;
  overall_signal: string;
  thesis_quality: string;
  risk_reward_score: number | null;
  conviction_score: number | null;
  technical_trend: string | null;
  technical_score: number | null;
  consecutive_red: number;
  last_verdict: string | null;
  last_quarter: string | null;
  unread_alert_count: number;
}

function SignalDot({ signal }: { signal: string }) {
  const cfg = SIGNAL_CONFIG[signal as keyof typeof SIGNAL_CONFIG] || SIGNAL_CONFIG.NA;
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${cfg.dot}`} title={signal} />;
}

function VerdictBadge({ verdict }: { verdict: string | null }) {
  if (!verdict) return <span className="text-gray-300">—</span>;
  const colors: Record<string, string> = {
    STRONG_BEAT: "text-emerald-700 bg-emerald-100",
    BEAT:        "text-green-700   bg-green-100",
    IN_LINE:     "text-blue-700    bg-blue-100",
    MISS:        "text-orange-700  bg-orange-100",
    STRONG_MISS: "text-red-700     bg-red-100",
  };
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colors[verdict] || "text-gray-500 bg-gray-100"}`}>
      {verdict.replace("_", " ")}
    </span>
  );
}

export default function MasterTrackerPage() {
  const [items, setItems] = useState<DashboardItem[]>([]);
  const [total, setTotal] = useState(0);
  const [alertCount, setAlertCount] = useState(0);
  const [highSevCount, setHighSevCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const [sortBy, setSortBy] = useState("risk_reward_score");
  const [signal, setSignal] = useState("");
  const [sector, setSector] = useState("");
  const [mcap, setMcap] = useState("");
  const [search, setSearch] = useState("");

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ sort_by: sortBy });
    if (signal) params.set("signal", signal);
    if (sector) params.set("sector", sector);
    if (mcap)   params.set("market_cap_cat", mcap);

    const res = await fetch(`${API_BASE}/api/v1/tracker/dashboard?${params}`);
    const data = await res.json();
    setItems(data.items || []);
    setTotal(data.total || 0);
    setAlertCount(data.alert_count || 0);
    setHighSevCount(data.high_severity_count || 0);
    setLoading(false);
  }, [sortBy, signal, sector, mcap]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const filtered = items.filter(i =>
    !search || i.company_name.toLowerCase().includes(search.toLowerCase()) ||
    (i.symbol_nse || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Master Tracker</h1>
          <p className="text-sm text-gray-500 mt-1">
            {total} stocks tracked ·
            <span className={alertCount > 0 ? "text-orange-600 font-semibold" : "text-gray-400"}> {alertCount} unread alerts</span>
            {highSevCount > 0 && <span className="text-red-600 font-semibold"> · {highSevCount} high severity</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <a href="/tracker/alerts" className={`px-4 py-2 text-sm rounded-lg font-medium ${highSevCount > 0 ? "bg-red-100 text-red-700 border border-red-200" : "bg-gray-100 text-gray-600"}`}>
            🔔 Alerts ({alertCount})
          </a>
          <a href="/master-tracker-dashboard.html" target="_blank"
             className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 font-medium">
            Open Full Dashboard
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input type="text" placeholder="Search company…" value={search}
               onChange={e => setSearch(e.target.value)}
               className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-52 bg-white" />

        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="risk_reward_score">Sort: Risk-Reward</option>
          <option value="expected_cagr_3y">Sort: Expected CAGR</option>
          <option value="upside_pct">Sort: Upside %</option>
          <option value="technical_score">Sort: Technical Strength</option>
          <option value="market_cap_cr">Sort: Market Cap</option>
          <option value="consecutive_red">Sort: Consecutive Red ↑</option>
          <option value="sector">Sort: Sector</option>
        </select>

        <select value={signal} onChange={e => setSignal(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">All Signals</option>
          <option value="GREEN">🟢 Green</option>
          <option value="YELLOW">🟡 Yellow</option>
          <option value="RED">🔴 Red</option>
        </select>

        <select value={mcap} onChange={e => setMcap(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">All Mkt Caps</option>
          <option value="LARGE">Large Cap</option>
          <option value="MID">Mid Cap</option>
          <option value="SMALL">Small Cap</option>
          <option value="MICRO">Micro Cap</option>
        </select>

        <button onClick={fetchDashboard}
                className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-700">
          ↺ Refresh
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          { label: "Green", sig: "GREEN", count: items.filter(i => i.overall_signal === "GREEN").length },
          { label: "Yellow", sig: "YELLOW", count: items.filter(i => i.overall_signal === "YELLOW").length },
          { label: "Red", sig: "RED", count: items.filter(i => i.overall_signal === "RED").length },
          { label: "Consec. Red ≥2", sig: "RED", count: items.filter(i => i.consecutive_red >= 2).length },
        ].map(({ label, sig, count }) => (
          <div key={label}
               onClick={() => setSignal(sig === signal ? "" : (label.startsWith("Consec") ? "RED" : sig))}
               className={`cursor-pointer rounded-xl border p-3 text-center transition-all ${SIGNAL_CONFIG[sig as keyof typeof SIGNAL_CONFIG].bg} ${SIGNAL_CONFIG[sig as keyof typeof SIGNAL_CONFIG].border}`}>
            <div className={`text-2xl font-bold ${SIGNAL_CONFIG[sig as keyof typeof SIGNAL_CONFIG].text}`}>{count}</div>
            <div className="text-xs text-gray-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-20 text-gray-400">Loading tracker…</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm min-w-[1200px]">
            <thead className="bg-gray-50 text-xs text-gray-400 uppercase tracking-wider sticky top-0">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Sector</th>
                <th className="px-4 py-3 text-right">CMP</th>
                <th className="px-4 py-3 text-right">Target</th>
                <th className="px-4 py-3 text-right">Upside</th>
                <th className="px-4 py-3 text-right">CAGR 3Y</th>
                <th className="px-4 py-3 text-center">Signal</th>
                <th className="px-4 py-3 text-center">Rating</th>
                <th className="px-4 py-3 text-center">R/R</th>
                <th className="px-4 py-3 text-center">Technical</th>
                <th className="px-4 py-3 text-center">Last Result</th>
                <th className="px-4 py-3 text-center">Alerts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((item) => {
                const sigCfg = SIGNAL_CONFIG[item.overall_signal as keyof typeof SIGNAL_CONFIG] || SIGNAL_CONFIG.NA;
                return (
                  <tr
                    key={item.isin}
                    onClick={() => window.location.href = `/tracker/${item.isin}`}
                    className={`cursor-pointer hover:bg-indigo-50/30 transition-colors ${item.consecutive_red >= 2 ? "bg-red-50/20" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <SignalDot signal={item.overall_signal} />
                        <div>
                          <div className="font-semibold text-gray-900">{item.company_name}</div>
                          <div className="text-xs text-gray-400">{item.symbol_nse || item.isin}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                        {item.sector || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700 font-medium">
                      {item.cmp ? `₹${item.cmp.toLocaleString("en-IN")}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {item.target_price_12m ? `₹${item.target_price_12m.toLocaleString("en-IN")}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`font-semibold ${(item.upside_pct || 0) > 0 ? "text-emerald-600" : "text-red-500"}`}>
                        {item.upside_pct != null ? `${item.upside_pct > 0 ? "+" : ""}${item.upside_pct.toFixed(1)}%` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="font-medium text-indigo-700">
                        {item.expected_cagr_3y != null ? `${item.expected_cagr_3y.toFixed(0)}%` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${sigCfg.bg} ${sigCfg.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${sigCfg.dot}`} />
                        {item.overall_signal}
                        {item.consecutive_red >= 2 && <span title={`${item.consecutive_red} consecutive red`}>⚠</span>}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${RATING_COLORS[item.rating] || "text-gray-500 bg-gray-100"}`}>
                        {item.rating.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex flex-col items-center">
                        <div className={`text-sm font-bold ${(item.risk_reward_score || 0) >= 7 ? "text-emerald-600" : (item.risk_reward_score || 0) >= 5 ? "text-amber-600" : "text-red-500"}`}>
                          {item.risk_reward_score?.toFixed(1) || "—"}
                        </div>
                        <div className="text-xs text-gray-400">/10</div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {item.technical_trend ? (
                        <div className="flex flex-col items-center">
                          <span className={`text-lg ${item.technical_trend === "UPTREND" ? "text-emerald-500" : item.technical_trend === "DOWNTREND" ? "text-red-500" : "text-amber-500"}`}>
                            {TREND_ICONS[item.technical_trend] || "→"}
                          </span>
                          <div className="text-xs text-gray-400">{item.technical_score?.toFixed(0)}</div>
                        </div>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div>
                        <VerdictBadge verdict={item.last_verdict} />
                        {item.last_quarter && <div className="text-xs text-gray-400 mt-0.5">{item.last_quarter}</div>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {item.unread_alert_count > 0 ? (
                        <span className="inline-flex items-center justify-center w-5 h-5 bg-red-500 text-white text-xs rounded-full font-bold">
                          {item.unread_alert_count}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              No stocks match the current filters.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

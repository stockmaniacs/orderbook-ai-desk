"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  TrendingUp, TrendingDown, Minus, Search,
  BookOpen, RefreshCw, ChevronDown,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface UniverseItem {
  isin: string;
  symbol_nse: string | null;
  company_name: string;
  sector: string | null;
  market_cap_cr: number | null;
  market_cap_cat: string | null;
  rating: string | null;
  confidence_score: number | null;
  expected_cagr_3y: number | null;
  target_price_12m: number | null;
  current_price: number | null;
  upside_pct: number | null;
  last_research_date: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const RATING_STYLES: Record<string, string> = {
  STRONG_BUY: "bg-emerald-100 text-emerald-800",
  BUY:        "bg-emerald-50 text-emerald-700",
  ACCUMULATE: "bg-blue-50 text-blue-700",
  HOLD:       "bg-amber-50 text-amber-700",
  REDUCE:     "bg-orange-50 text-orange-700",
  SELL:       "bg-red-100 text-red-700",
  AVOID:      "bg-gray-100 text-gray-600",
};

function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return <span className="text-gray-300 text-xs">—</span>;
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${RATING_STYLES[rating] ?? "bg-gray-100 text-gray-600"}`}>
      {rating.replace("_", " ")}
    </span>
  );
}

function UpsideCell({ upside }: { upside: number | null }) {
  if (upside == null) return <span className="text-gray-300">—</span>;
  const positive = upside >= 0;
  return (
    <span className={`flex items-center gap-1 font-semibold ${positive ? "text-emerald-600" : "text-red-500"}`}>
      {positive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
      {upside > 0 ? "+" : ""}{upside.toFixed(1)}%
    </span>
  );
}

function ConfidenceBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-gray-300 text-xs">—</span>;
  const color = score >= 70 ? "bg-emerald-400" : score >= 40 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-500">{score.toFixed(0)}</span>
    </div>
  );
}

function formatCr(v: number | null) {
  if (v == null) return "—";
  if (v >= 100000) return `₹${(v / 100000).toFixed(1)}L Cr`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}K Cr`;
  return `₹${v.toFixed(0)} Cr`;
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function ResearchUniversePage() {
  const [universe, setUniverse] = useState<UniverseItem[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [ratingFilter, setRatingFilter] = useState("");
  const [isSeeding, setIsSeeding] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch("/api/v1/research/universe?limit=200").then(r => r.json()),
      fetch("/api/v1/research/universe/sectors").then(r => r.json()),
    ]).then(([uni, sec]) => {
      setUniverse(uni);
      setSectors(sec);
    }).finally(() => setLoading(false));
  }, []);

  const filtered = universe.filter(c => {
    const matchSearch = !search || [c.company_name, c.isin, c.symbol_nse]
      .some(v => v?.toLowerCase().includes(search.toLowerCase()));
    const matchSector = !sectorFilter || c.sector === sectorFilter;
    const matchRating = !ratingFilter || c.rating === ratingFilter;
    return matchSearch && matchSector && matchRating;
  });

  const handleSeed = async () => {
    setIsSeeding(true);
    await fetch("/api/v1/research/admin/seed-universe", { method: "POST" });
    setTimeout(() => setIsSeeding(false), 5000);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-5">
        <div className="mx-auto max-w-screen-xl flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-indigo-600" />
              Research Universe
            </h1>
            <p className="mt-0.5 text-sm text-gray-500">
              AI-generated investment research for all NSE/BSE listed companies
            </p>
          </div>
          <button
            onClick={handleSeed}
            disabled={isSeeding}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            <RefreshCw className={`h-4 w-4 ${isSeeding ? "animate-spin" : ""}`} />
            {isSeeding ? "Seeding…" : "Sync Universe"}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-screen-xl px-6 py-6 space-y-4">
        {/* Filters */}
        <div className="flex gap-3 flex-wrap">
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search company, ISIN, or symbol…"
              className="w-full rounded-xl border border-gray-200 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            />
          </div>
          <select
            value={sectorFilter}
            onChange={e => setSectorFilter(e.target.value)}
            className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="">All Sectors</option>
            {sectors.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            value={ratingFilter}
            onChange={e => setRatingFilter(e.target.value)}
            className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="">All Ratings</option>
            {["STRONG_BUY","BUY","ACCUMULATE","HOLD","REDUCE","SELL","AVOID"].map(r => (
              <option key={r} value={r}>{r.replace("_"," ")}</option>
            ))}
          </select>
        </div>

        {/* Table */}
        <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-gray-100 px-4 py-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Companies</h3>
            <span className="text-xs text-gray-400">{filtered.length} results</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {["Company","Sector","Mkt Cap","Rating","Upside","3Y CAGR","Tgt Price","Confidence",""].map(h => (
                    <th key={h} className="py-2.5 px-3 first:pl-4 last:pr-4 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} className="py-12 text-center text-sm text-gray-400">Loading…</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={9} className="py-12 text-center text-sm text-gray-400">No companies yet. Sync Universe to populate.</td></tr>
                ) : filtered.map(c => (
                  <tr key={c.isin} className="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                    <td className="py-3 pl-4 pr-3">
                      <Link href={`/research/${c.isin}`} className="block">
                        <p className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">{c.company_name}</p>
                        <p className="text-[11px] text-gray-400">{c.symbol_nse ?? c.isin}</p>
                      </Link>
                    </td>
                    <td className="py-3 px-3 text-xs text-gray-500">{c.sector ?? "—"}</td>
                    <td className="py-3 px-3 text-sm text-gray-700">{formatCr(c.market_cap_cr)}</td>
                    <td className="py-3 px-3"><RatingBadge rating={c.rating} /></td>
                    <td className="py-3 px-3"><UpsideCell upside={c.upside_pct} /></td>
                    <td className="py-3 px-3 text-sm text-gray-700">
                      {c.expected_cagr_3y != null ? `${c.expected_cagr_3y > 0 ? "+" : ""}${c.expected_cagr_3y.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-3 px-3 text-sm font-medium text-gray-800">
                      {c.target_price_12m != null ? `₹${c.target_price_12m.toFixed(0)}` : "—"}
                    </td>
                    <td className="py-3 px-3"><ConfidenceBar score={c.confidence_score} /></td>
                    <td className="py-3 pl-3 pr-4">
                      <Link
                        href={`/research/${c.isin}`}
                        className="rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition-colors"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

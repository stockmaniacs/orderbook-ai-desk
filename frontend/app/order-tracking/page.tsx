"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  orderTrackingApi,
  OrderBookMetrics,
  PaginatedOrders,
  formatCr,
  formatPct,
  getMomentumBadge,
} from "@/lib/api/order-tracking";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Search,
  Zap,
  ArrowUpRight,
  Filter,
  RefreshCw,
} from "lucide-react";

// ─── Leaderboard table ────────────────────────────────────────────────────────
function LeaderboardRow({
  rank,
  metrics,
}: {
  rank: number;
  metrics: OrderBookMetrics;
}) {
  const badge = getMomentumBadge(metrics.order_momentum);
  const score = metrics.order_acceleration_score ?? 0;
  const scoreColor =
    score >= 65 ? "text-emerald-600" : score >= 40 ? "text-amber-500" : "text-red-500";
  const growth = metrics.order_inflow_growth_yoy_pct;

  return (
    <tr className="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
      <td className="py-3 pl-4 text-sm font-semibold text-gray-400">#{rank}</td>
      <td className="py-3 px-3">
        <div className="flex flex-col">
          <Link
            href={`/order-tracking/${metrics.isin}`}
            className="flex items-center gap-1 text-sm font-semibold text-indigo-600 hover:text-indigo-800"
          >
            {metrics.company_name ?? metrics.isin}
            <ArrowUpRight className="h-3 w-3" />
          </Link>
          <span className="text-[11px] text-gray-400">{metrics.isin}</span>
        </div>
      </td>
      <td className="py-3 px-3 text-sm font-semibold text-gray-900">
        {formatCr(metrics.current_order_book_cr)}
      </td>
      <td className="py-3 px-3">
        <div className="flex items-center gap-1">
          {growth == null ? (
            <Minus className="h-3.5 w-3.5 text-gray-300" />
          ) : growth >= 0 ? (
            <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-red-500" />
          )}
          <span
            className={`text-sm font-medium ${
              growth == null
                ? "text-gray-400"
                : growth >= 0
                ? "text-emerald-600"
                : "text-red-500"
            }`}
          >
            {formatPct(growth)}
          </span>
        </div>
      </td>
      <td className="py-3 px-3 text-sm text-gray-700">
        {metrics.order_book_to_sales?.toFixed(1) ?? "—"}x
      </td>
      <td className="py-3 px-3 text-sm text-gray-700">
        {metrics.bill_to_book_ratio?.toFixed(2) ?? "—"}x
      </td>
      <td className="py-3 px-3">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${scoreColor}`}>
            {score.toFixed(0)}
          </span>
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full ${
                score >= 65 ? "bg-emerald-400" : score >= 40 ? "bg-amber-400" : "bg-red-400"
              }`}
              style={{ width: `${score}%` }}
            />
          </div>
        </div>
      </td>
      <td className="py-3 px-3">
        <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.className}`}>
          {badge.label}
        </span>
      </td>
      <td className="py-3 pl-3 pr-4">
        <Link
          href={`/order-tracking/${metrics.isin}`}
          className="rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition-colors"
        >
          View →
        </Link>
      </td>
    </tr>
  );
}

// ─── Recent large orders feed ─────────────────────────────────────────────────
function RecentOrdersPanel({ data }: { data: PaginatedOrders }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">
          Recent Large Orders (≥ ₹250 Cr)
        </h3>
      </div>
      <ul className="divide-y divide-gray-50">
        {data.items.map((order) => (
          <li key={order.id} className="px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <Link
                  href={`/order-tracking/${order.isin}`}
                  className="text-sm font-semibold text-gray-900 hover:text-indigo-600 truncate block"
                >
                  {order.company_name}
                </Link>
                <p className="mt-0.5 text-xs text-gray-500 truncate">
                  {order.customer_name ? `← ${order.customer_name}` : "Customer undisclosed"}
                  {order.sector_category && ` · ${order.sector_category.replace(/_/g, " ")}`}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-bold text-gray-900">
                  {formatCr(order.order_amount_cr)}
                </p>
                <p className="text-[11px] text-gray-400">
                  {new Date(order.announced_date).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                  })}
                </p>
              </div>
            </div>
          </li>
        ))}
        {data.items.length === 0 && (
          <li className="py-8 text-center text-sm text-gray-400">
            No recent large orders
          </li>
        )}
      </ul>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function OrderTrackingUniversePage() {
  const [leaderboard, setLeaderboard] = useState<OrderBookMetrics[]>([]);
  const [recentOrders, setRecentOrders] = useState<PaginatedOrders | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [isScraping, setIsScraping] = useState(false);

  useEffect(() => {
    Promise.all([
      orderTrackingApi.getLeaderboard(30),
      orderTrackingApi.getUniverseRecent({ limit: 20, min_amount_cr: 250 }),
    ]).then(([lb, recent]) => {
      setLeaderboard(lb);
      setRecentOrders(recent);
    }).finally(() => setLoading(false));
  }, []);

  const handleScrape = async () => {
    setIsScraping(true);
    try {
      await orderTrackingApi.triggerScrape(3);
      alert("Scrape triggered for last 3 days. Results will appear in ~5 minutes.");
    } finally {
      setTimeout(() => setIsScraping(false), 5000);
    }
  };

  const filtered = leaderboard.filter(
    (m) =>
      !search ||
      (m.company_name?.toLowerCase().includes(search.toLowerCase())) ||
      m.isin.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-5">
        <div className="mx-auto max-w-screen-xl flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <Zap className="h-5 w-5 text-indigo-600" />
              Order Book Intelligence
            </h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Track corporate order wins, pipeline health, and acceleration across Indian markets
            </p>
          </div>
          <button
            onClick={handleScrape}
            disabled={isScraping}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            <RefreshCw className={`h-4 w-4 ${isScraping ? "animate-spin" : ""}`} />
            {isScraping ? "Scraping…" : "Trigger Scrape"}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-screen-xl px-6 py-6 flex gap-6">
        {/* Main: Leaderboard */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search company or ISIN…"
              className="w-full rounded-xl border border-gray-200 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            />
          </div>

          {/* Leaderboard */}
          <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-gray-100 px-4 py-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-900">
                Companies by Acceleration Score
              </h3>
              <span className="text-xs text-gray-400">{filtered.length} companies</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    {[
                      "#", "Company", "Order Book", "YoY Growth",
                      "OB/Sales", "B2B Ratio", "Score", "Momentum", ""
                    ].map((h) => (
                      <th
                        key={h}
                        className="py-2.5 px-3 first:pl-4 last:pr-4 text-[11px] font-semibold uppercase tracking-wide text-gray-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-sm text-gray-400">
                        Loading…
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-sm text-gray-400">
                        No data yet. Trigger a scrape to populate.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((m, i) => (
                      <LeaderboardRow key={m.isin} rank={i + 1} metrics={m} />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Sidebar: Recent large orders */}
        <div className="w-80 shrink-0">
          {recentOrders && <RecentOrdersPanel data={recentOrders} />}
        </div>
      </div>
    </div>
  );
}

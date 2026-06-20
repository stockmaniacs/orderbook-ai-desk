"use client";

export const runtime = "edge";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  orderTrackingApi,
  OrderTrackingDashboard,
  ChartsData,
  PaginatedOrders,
} from "@/lib/api/order-tracking";
import { MetricCards } from "@/components/order-tracking/MetricCards";
import { OrderBookChart } from "@/components/order-tracking/OrderBookChart";
import { ScenarioCards } from "@/components/order-tracking/ScenarioCards";
import { AISummary } from "@/components/order-tracking/AISummary";
import { OrderTable } from "@/components/order-tracking/OrderTable";
import {
  AlertCircle,
  ArrowLeft,
  RefreshCw,
  TrendingUp,
  Building2,
} from "lucide-react";
import Link from "next/link";

// ─── Skeleton loader ──────────────────────────────────────────────────────────
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-lg bg-gray-100 ${className}`} />
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-4 gap-4">
        {[...Array(8)].map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-96" />
      <div className="grid grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-56" />)}
      </div>
      <Skeleton className="h-96" />
      <Skeleton className="h-80" />
    </div>
  );
}

// ─── Error state ──────────────────────────────────────────────────────────────
function ErrorState({ isin, message }: { isin: string; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-red-100 bg-red-50 py-16 text-center">
      <AlertCircle className="mb-3 h-10 w-10 text-red-400" />
      <h3 className="text-base font-semibold text-red-800">No Data Found</h3>
      <p className="mt-1 text-sm text-red-600">
        {message || `No order tracking data available for ${isin}`}
      </p>
      <p className="mt-3 text-xs text-red-500">
        Trigger a scrape from the admin panel or add orders manually.
      </p>
      <div className="mt-4 flex gap-3">
        <Link
          href="/order-tracking"
          className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-red-700 shadow-sm hover:bg-red-50 border border-red-200"
        >
          ← Back to Universe
        </Link>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function OrderTrackingDetailPage() {
  const { isin } = useParams<{ isin: string }>();

  const [dashboard, setDashboard] = useState<OrderTrackingDashboard | null>(null);
  const [charts, setCharts] = useState<ChartsData | null>(null);
  const [orders, setOrders] = useState<PaginatedOrders | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartsLoading, setChartsLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<{ order_type?: string; min_amount_cr?: number }>({});
  const [isRegenerating, setIsRegenerating] = useState(false);

  // ── Data fetching ───────────────────────────────────────────────────────────
  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await orderTrackingApi.getDashboard(isin);
      setDashboard(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [isin]);

  const fetchCharts = useCallback(async () => {
    setChartsLoading(true);
    try {
      const data = await orderTrackingApi.getCharts(isin);
      setCharts(data);
    } catch {
      /* non-critical */
    } finally {
      setChartsLoading(false);
    }
  }, [isin]);

  const fetchOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const data = await orderTrackingApi.getOrders(isin, {
        page,
        limit: 20,
        ...filters,
      });
      setOrders(data);
    } catch {
      /* non-critical */
    } finally {
      setOrdersLoading(false);
    }
  }, [isin, page, filters]);

  useEffect(() => {
    fetchDashboard();
    fetchCharts();
  }, [fetchDashboard, fetchCharts]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      await orderTrackingApi.regenerateAISummary(isin);
      // Poll for new summary after 30s
      setTimeout(fetchDashboard, 30000);
    } catch {
      /* 202 is expected */
    } finally {
      setTimeout(() => setIsRegenerating(false), 30000);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  if (loading) return <div className="p-6"><PageSkeleton /></div>;
  if (error || !dashboard) {
    return (
      <div className="p-6">
        <ErrorState isin={isin} message={error ?? "No data found"} />
      </div>
    );
  }

  const { metrics, history, recent_orders, ai_summary } = dashboard;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Page header */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-screen-xl">
          <div className="mb-3 flex items-center gap-2 text-sm text-gray-500">
            <Link href="/order-tracking" className="flex items-center gap-1 hover:text-gray-700">
              <ArrowLeft className="h-3.5 w-3.5" />
              Order Universe
            </Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">{isin}</span>
          </div>

          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100">
                <Building2 className="h-6 w-6 text-indigo-600" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">{dashboard.company_name}</h1>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-sm text-gray-500">{isin}</span>
                  {dashboard.sector && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                      {dashboard.sector}
                    </span>
                  )}
                  {ai_summary?.trend && (
                    <span
                      className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                        ai_summary.trend === "IMPROVING"
                          ? "bg-emerald-100 text-emerald-700"
                          : ai_summary.trend === "DETERIORATING"
                          ? "bg-red-100 text-red-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      <TrendingUp className="h-3 w-3" />
                      {ai_summary.trend}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <button
              onClick={fetchDashboard}
              className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-screen-xl px-6 py-6 space-y-6">
        {/* Metric cards */}
        {metrics && <MetricCards metrics={metrics} />}

        {/* Charts */}
        {!chartsLoading && charts && charts.quarterly.length > 0 ? (
          <OrderBookChart charts={charts} />
        ) : chartsLoading ? (
          <Skeleton className="h-96" />
        ) : (
          <div className="rounded-xl border border-dashed border-gray-200 bg-white py-12 text-center text-sm text-gray-400">
            Not enough data to build charts yet
          </div>
        )}

        {/* Scenarios */}
        {metrics && (
          <ScenarioCards metrics={metrics} summary={ai_summary ?? undefined} />
        )}

        {/* AI Summary */}
        {ai_summary ? (
          <AISummary
            summary={ai_summary}
            isin={isin}
            onRegenerate={handleRegenerate}
            isRegenerating={isRegenerating}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-gray-200 bg-white py-10 text-center text-sm text-gray-400">
            AI summary not yet generated.{" "}
            <button
              onClick={handleRegenerate}
              className="underline text-indigo-600 hover:text-indigo-700"
            >
              Generate now
            </button>
          </div>
        )}

        {/* Order table */}
        {orders && (
          <OrderTable
            data={orders}
            onPageChange={(p) => setPage(p)}
            onFilterChange={(f) => { setFilters(f); setPage(1); }}
            isLoading={ordersLoading}
          />
        )}
      </div>
    </div>
  );
}

"use client";

import { OrderBookMetrics, formatCr, formatPct, formatMultiple, getMomentumBadge } from "@/lib/api/order-tracking";
import { TrendingUp, TrendingDown, Minus, BarChart3, Target, Zap, Activity } from "lucide-react";

interface Props {
  metrics: OrderBookMetrics;
}

function DeltaIcon({ value }: { value?: number | null }) {
  if (value == null) return <Minus className="h-3 w-3 text-gray-400" />;
  if (value > 0) return <TrendingUp className="h-3 w-3 text-emerald-500" />;
  return <TrendingDown className="h-3 w-3 text-red-500" />;
}

function StatCard({
  label,
  value,
  subValue,
  subLabel,
  icon: Icon,
  color = "blue",
}: {
  label: string;
  value: string;
  subValue?: string;
  subLabel?: string;
  icon: React.ElementType;
  color?: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600",
    green: "bg-emerald-50 text-emerald-600",
    purple: "bg-purple-50 text-purple-600",
    orange: "bg-orange-50 text-orange-600",
    red: "bg-red-50 text-red-600",
  };

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {label}
        </span>
        <span className={`rounded-lg p-1.5 ${colorMap[color]}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {subValue && (
        <p className="mt-1 text-xs text-gray-500">
          {subLabel && <span className="mr-1">{subLabel}:</span>}
          <span
            className={
              subValue.startsWith("+")
                ? "text-emerald-600 font-medium"
                : subValue.startsWith("-")
                ? "text-red-500 font-medium"
                : ""
            }
          >
            {subValue}
          </span>
        </p>
      )}
    </div>
  );
}

export function MetricCards({ metrics }: Props) {
  const momentum = getMomentumBadge(metrics.order_momentum);
  const trendColor =
    metrics.order_to_sales_trend === "IMPROVING"
      ? "text-emerald-600"
      : metrics.order_to_sales_trend === "DETERIORATING"
      ? "text-red-500"
      : "text-amber-500";

  const score = metrics.order_acceleration_score ?? 0;
  const scoreColor =
    score >= 65 ? "text-emerald-600" : score >= 40 ? "text-amber-500" : "text-red-500";

  return (
    <div className="space-y-4">
      {/* Momentum badge */}
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${momentum.className}`}
        >
          <Zap className="h-3 w-3" />
          {momentum.label}
        </span>
        <span className="text-xs text-gray-400">
          Updated {new Date(metrics.updated_at).toLocaleDateString("en-IN")}
        </span>
      </div>

      {/* 8-card grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Order Book"
          value={formatCr(metrics.current_order_book_cr)}
          subValue={formatPct(metrics.order_book_growth_yoy_pct)}
          subLabel="YoY"
          icon={BarChart3}
          color="blue"
        />
        <StatCard
          label="TTM Inflows"
          value={formatCr(metrics.ttm_orders_won_cr)}
          subValue={formatPct(metrics.order_inflow_growth_yoy_pct)}
          subLabel="YoY Growth"
          icon={TrendingUp}
          color="green"
        />
        <StatCard
          label="OB / Sales"
          value={formatMultiple(metrics.order_book_to_sales)}
          subValue={metrics.order_to_sales_trend}
          icon={Activity}
          color="purple"
        />
        <StatCard
          label="Bill-to-Book"
          value={formatMultiple(metrics.bill_to_book_ratio)}
          subValue={
            (metrics.bill_to_book_ratio ?? 0) >= 1.0
              ? "Above 1x — healthy"
              : "Below 1x — caution"
          }
          icon={Target}
          color={
            (metrics.bill_to_book_ratio ?? 0) >= 1.0 ? "green" : "red"
          }
        />
        <StatCard
          label="Order CAGR (3Y)"
          value={formatPct(metrics.order_book_cagr_3y)}
          subValue={
            metrics.order_book_cagr_5y != null
              ? `5Y: ${formatPct(metrics.order_book_cagr_5y)}`
              : undefined
          }
          icon={TrendingUp}
          color="orange"
        />
        <StatCard
          label="Total Orders"
          value={String(metrics.total_orders_count)}
          subValue={
            metrics.last_order_date
              ? `Last: ${new Date(metrics.last_order_date).toLocaleDateString("en-IN")}`
              : undefined
          }
          icon={BarChart3}
          color="blue"
        />
        <StatCard
          label="Domestic Mix"
          value={metrics.domestic_pct != null ? `${metrics.domestic_pct}%` : "—"}
          subValue={
            metrics.export_pct != null ? `Export: ${metrics.export_pct}%` : undefined
          }
          icon={Activity}
          color="purple"
        />

        {/* Acceleration score gauge */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
              Acceleration Score
            </span>
            <Zap className="h-4 w-4 text-amber-500" />
          </div>
          <div className="flex items-end gap-2">
            <span className={`text-3xl font-bold ${scoreColor}`}>
              {score.toFixed(0)}
            </span>
            <span className="mb-1 text-sm text-gray-400">/100</span>
          </div>
          {/* Score bar */}
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                score >= 65
                  ? "bg-emerald-500"
                  : score >= 40
                  ? "bg-amber-400"
                  : "bg-red-400"
              }`}
              style={{ width: `${score}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

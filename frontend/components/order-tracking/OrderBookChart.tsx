"use client";

import { useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  AreaChart,
  ComposedChart,
} from "recharts";
import { ChartsData } from "@/lib/api/order-tracking";

type Tab = "quarterly" | "yoy" | "rolling";

interface Props {
  charts: ChartsData;
}

const COLORS = {
  ob: "#3b82f6",      // blue — order book balance
  inflow: "#10b981",  // emerald — new orders
  executed: "#f59e0b", // amber — revenue executed
  growth: "#8b5cf6",  // purple — growth %
  rolling: "#06b6d4", // cyan — rolling sum
  ratio: "#f97316",   // orange — OB/Sales ratio
};

function fmt(v: number | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}K Cr`;
  return `₹${v.toFixed(0)} Cr`;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-lg text-xs">
      <p className="mb-2 font-semibold text-gray-700">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-gray-600">{p.name}:</span>
          <span className="font-medium">
            {typeof p.value === "number" && p.name?.includes("%")
              ? `${p.value > 0 ? "+" : ""}${p.value.toFixed(1)}%`
              : fmt(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

// ─── Tab: Quarterly Order Book ─────────────────────────────────────────────
function QuarterlyChart({ data }: { data: ChartsData["quarterly"] }) {
  const [showRatio, setShowRatio] = useState(false);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Order book balance (closing), new inflows, and revenue executed per quarter
        </p>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={showRatio}
            onChange={(e) => setShowRatio(e.target.checked)}
            className="rounded"
          />
          Show OB/Sales
        </label>
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="quarter"
            tick={{ fontSize: 11, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="cr"
            tick={{ fontSize: 11, fill: "#6b7280" }}
            tickFormatter={(v) => `${v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v}`}
            axisLine={false}
            tickLine={false}
          />
          {showRatio && (
            <YAxis
              yAxisId="ratio"
              orientation="right"
              tick={{ fontSize: 11, fill: COLORS.ratio }}
              tickFormatter={(v) => `${v.toFixed(1)}x`}
              axisLine={false}
              tickLine={false}
            />
          )}
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            iconType="circle"
            iconSize={8}
          />
          <Bar
            yAxisId="cr"
            dataKey="new_orders_cr"
            name="New Orders"
            fill={COLORS.inflow}
            radius={[3, 3, 0, 0]}
            opacity={0.85}
          />
          <Bar
            yAxisId="cr"
            dataKey="executed_cr"
            name="Executed"
            fill={COLORS.executed}
            radius={[3, 3, 0, 0]}
            opacity={0.7}
          />
          <Line
            yAxisId="cr"
            type="monotone"
            dataKey="order_book_cr"
            name="Order Book"
            stroke={COLORS.ob}
            strokeWidth={2.5}
            dot={{ r: 4, fill: COLORS.ob }}
            activeDot={{ r: 6 }}
          />
          {showRatio && (
            <Line
              yAxisId="ratio"
              type="monotone"
              dataKey="ob_to_sales"
              name="OB/Sales"
              stroke={COLORS.ratio}
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Tab: YoY Order Growth ─────────────────────────────────────────────────
function YoYChart({ data }: { data: ChartsData["yoy_growth"] }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        Annual order inflows and year-on-year growth rate
      </p>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="fiscal_year"
            tickFormatter={(v) => `FY${String(v).slice(-2)}`}
            tick={{ fontSize: 11, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="cr"
            tick={{ fontSize: 11, fill: "#6b7280" }}
            tickFormatter={(v) => `${v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v}`}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="pct"
            orientation="right"
            tick={{ fontSize: 11, fill: COLORS.growth }}
            tickFormatter={(v) => `${v}%`}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
          <ReferenceLine yAxisId="pct" y={0} stroke="#e5e7eb" strokeWidth={1.5} />
          <Bar
            yAxisId="cr"
            dataKey="ttm_orders_cr"
            name="Order Inflows"
            fill={COLORS.inflow}
            radius={[4, 4, 0, 0]}
            opacity={0.85}
          />
          <Line
            yAxisId="pct"
            type="monotone"
            dataKey="yoy_growth_pct"
            name="YoY Growth %"
            stroke={COLORS.growth}
            strokeWidth={2.5}
            dot={{ r: 4, fill: COLORS.growth }}
            activeDot={{ r: 6 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Tab: Rolling Order Book ───────────────────────────────────────────────
function RollingChart({ data }: { data: ChartsData["rolling"] }) {
  const formattedData = data.map((d) => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-IN", {
      month: "short",
      year: "2-digit",
    }),
  }));

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        12-month rolling order inflows — smooths out quarterly lumps
      </p>
      <ResponsiveContainer width="100%" height={340}>
        <AreaChart
          data={formattedData}
          margin={{ top: 4, right: 20, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="rollingGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={COLORS.rolling} stopOpacity={0.25} />
              <stop offset="95%" stopColor={COLORS.rolling} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#6b7280" }}
            tickFormatter={(v) => `${v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v}`}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="rolling_4q_cr"
            name="12M Rolling Inflows"
            stroke={COLORS.rolling}
            strokeWidth={2.5}
            fill="url(#rollingGrad)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────
export function OrderBookChart({ charts }: Props) {
  const [tab, setTab] = useState<Tab>("quarterly");

  const tabs: { id: Tab; label: string }[] = [
    { id: "quarterly", label: "Quarter-wise" },
    { id: "yoy", label: "YoY Growth" },
    { id: "rolling", label: "Rolling 12M" },
  ];

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-900">Order Book Trends</h3>
        <div className="flex rounded-lg bg-gray-100 p-0.5">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                tab === t.id
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "quarterly" && <QuarterlyChart data={charts.quarterly} />}
      {tab === "yoy" && <YoYChart data={charts.yoy_growth} />}
      {tab === "rolling" && <RollingChart data={charts.rolling} />}
    </div>
  );
}

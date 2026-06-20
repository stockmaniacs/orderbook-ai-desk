"use client";

import { OrderBookMetrics, OrderAISummary, formatCr } from "@/lib/api/order-tracking";
import { TrendingUp, Minus, TrendingDown, ChevronRight } from "lucide-react";
import { useState } from "react";

interface Props {
  metrics: OrderBookMetrics;
  summary?: OrderAISummary;
}

type Scenario = "bull" | "base" | "bear";

const SCENARIO_CONFIG = {
  bull: {
    label: "Bull Case",
    icon: TrendingUp,
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    badge: "bg-emerald-100 text-emerald-800",
    valueBg: "bg-emerald-500",
    valueText: "text-white",
    accent: "#10b981",
  },
  base: {
    label: "Base Case",
    icon: Minus,
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100 text-blue-800",
    valueBg: "bg-blue-500",
    valueText: "text-white",
    accent: "#3b82f6",
  },
  bear: {
    label: "Bear Case",
    icon: TrendingDown,
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100 text-red-800",
    valueBg: "bg-red-500",
    valueText: "text-white",
    accent: "#ef4444",
  },
} as const;

function ScenarioCard({
  scenario,
  value,
  currentOB,
  assumptions,
  narrative,
}: {
  scenario: Scenario;
  value?: number;
  currentOB?: number;
  assumptions?: {
    quarterly_inflow_growth_pct: number;
    win_rate_assumption: string;
    key_driver: string;
  };
  narrative?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SCENARIO_CONFIG[scenario];
  const Icon = cfg.icon;

  const upside =
    value != null && currentOB != null && currentOB > 0
      ? ((value - currentOB) / currentOB) * 100
      : null;

  return (
    <div className={`rounded-xl border-2 ${cfg.border} ${cfg.bg} p-5 flex flex-col gap-3`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`rounded-lg p-1.5 ${cfg.badge}`}>
            <Icon className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold text-gray-700">{cfg.label}</span>
        </div>
        {upside != null && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-bold ${
              upside >= 0 ? cfg.badge : "bg-gray-100 text-gray-600"
            }`}
          >
            {upside >= 0 ? "+" : ""}
            {upside.toFixed(0)}% vs current
          </span>
        )}
      </div>

      {/* Value */}
      <div>
        <p className="text-xs text-gray-500 mb-0.5">Order Book ({assumptions ? `+${
          (assumptions.quarterly_inflow_growth_pct * 4).toFixed(0)}` : "4"}Q projection)</p>
        <p className="text-2xl font-bold text-gray-900">
          {formatCr(value)}
        </p>
      </div>

      {/* Visual bar — show value relative to bear/bull range */}
      {currentOB != null && value != null && (
        <div className="h-1.5 w-full rounded-full bg-white/70 overflow-hidden">
          <div
            className={`h-full rounded-full ${cfg.valueBg} opacity-80`}
            style={{ width: `${Math.min(Math.max((value / (currentOB * 2.5)) * 100, 5), 100)}%` }}
          />
        </div>
      )}

      {/* Assumptions */}
      {assumptions && (
        <div className="space-y-1.5 text-xs text-gray-600">
          <div className="flex items-center gap-1.5">
            <span className="text-gray-400">Quarterly inflow growth:</span>
            <span className="font-medium">
              {assumptions.quarterly_inflow_growth_pct > 0 ? "+" : ""}
              {assumptions.quarterly_inflow_growth_pct.toFixed(1)}%
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-400">Win rate:</span>
            <span className="font-medium">{assumptions.win_rate_assumption}</span>
          </div>
          <div className="flex items-start gap-1.5">
            <span className="text-gray-400 shrink-0">Key driver:</span>
            <span className="font-medium">{assumptions.key_driver}</span>
          </div>
        </div>
      )}

      {/* AI narrative (expandable) */}
      {narrative && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700"
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            />
            {expanded ? "Hide" : "Show"} analyst note
          </button>
          {expanded && (
            <p className="mt-2 text-xs leading-relaxed text-gray-600 bg-white/60 rounded-lg p-3">
              {narrative}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function ScenarioCards({ metrics, summary }: Props) {
  const assumptions = metrics.scenario_assumptions;
  const horizon = metrics.scenario_horizon_quarters ?? 4;

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Scenario Projections
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Order book forecast {horizon} quarters out from current ₹
            {(metrics.current_order_book_cr ?? 0).toFixed(0)} Cr
          </p>
        </div>
        <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">
          {horizon}Q horizon
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <ScenarioCard
          scenario="bull"
          value={metrics.bull_case_ob_cr}
          currentOB={metrics.current_order_book_cr}
          assumptions={assumptions?.bull}
          narrative={summary?.bull_narrative}
        />
        <ScenarioCard
          scenario="base"
          value={metrics.base_case_ob_cr}
          currentOB={metrics.current_order_book_cr}
          assumptions={assumptions?.base}
          narrative={summary?.base_narrative}
        />
        <ScenarioCard
          scenario="bear"
          value={metrics.bear_case_ob_cr}
          currentOB={metrics.current_order_book_cr}
          assumptions={assumptions?.bear}
          narrative={summary?.bear_narrative}
        />
      </div>
    </div>
  );
}

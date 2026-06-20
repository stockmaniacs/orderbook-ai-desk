"use client";

import { useState } from "react";
import { OrderAISummary, getTrendColor } from "@/lib/api/order-tracking";
import {
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Users,
  Globe,
  BarChart2,
} from "lucide-react";

interface Props {
  summary: OrderAISummary;
  isin: string;
  onRegenerate?: () => void;
  isRegenerating?: boolean;
}

const SEVERITY_COLORS = {
  HIGH: { bg: "bg-red-50", text: "text-red-700", dot: "bg-red-400" },
  MEDIUM: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-400" },
  LOW: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-300" },
};

const IMPACT_COLORS = {
  HIGH: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-400" },
  MEDIUM: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-400" },
  LOW: { bg: "bg-gray-50", text: "text-gray-600", dot: "bg-gray-300" },
};

function TrendBadge({ trend }: { trend?: string }) {
  const config = {
    IMPROVING: { label: "↑ Improving", className: "bg-emerald-100 text-emerald-800 border border-emerald-200" },
    STABLE: { label: "→ Stable", className: "bg-amber-100 text-amber-800 border border-amber-200" },
    DETERIORATING: { label: "↓ Deteriorating", className: "bg-red-100 text-red-800 border border-red-200" },
  };
  const cfg = config[trend as keyof typeof config];
  if (!cfg) return null;
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-sm font-bold ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

function Section({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-gray-100 pb-4 last:border-0 last:pb-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-2"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-semibold text-gray-700">{title}</span>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

export function AISummary({ summary, isin, onRegenerate, isRegenerating }: Props) {
  const confidence = summary.trend_confidence ?? 0;
  const trendColor = getTrendColor(summary.trend);

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="border-b border-gray-100 px-6 py-4 flex items-center justify-between bg-gradient-to-r from-indigo-50 to-purple-50">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 shadow">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-900">AI Order Flow Analysis</h3>
            <p className="text-xs text-gray-500">
              {summary.model_version && `Model: ${summary.model_version} · `}
              {new Date(summary.generated_at).toLocaleString("en-IN", {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
        </div>
        <button
          onClick={onRegenerate}
          disabled={isRegenerating}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-white/80 border border-gray-200 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRegenerating ? "animate-spin" : ""}`} />
          {isRegenerating ? "Regenerating…" : "Refresh"}
        </button>
      </div>

      <div className="p-6 space-y-5">
        {/* Verdict banner */}
        <div className="rounded-xl bg-gradient-to-r from-gray-50 to-gray-100 p-4">
          <div className="flex items-start gap-3">
            <TrendBadge trend={summary.trend} />
            <div className="flex-1">
              <p className={`text-sm font-semibold leading-snug ${trendColor}`}>
                {summary.ai_verdict}
              </p>
              {/* Confidence bar */}
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[10px] text-gray-400 uppercase tracking-wide">Confidence</span>
                <div className="h-1 w-24 overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full rounded-full bg-indigo-500"
                    style={{ width: `${confidence * 100}%` }}
                  />
                </div>
                <span className="text-[10px] text-gray-500">
                  {(confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Executive Summary */}
        <Section icon={BarChart2} title="Executive Summary">
          <p className="text-sm leading-relaxed text-gray-600">
            {summary.executive_summary}
          </p>
          {summary.pipeline_analysis && (
            <p className="mt-2 text-sm leading-relaxed text-gray-600">
              {summary.pipeline_analysis}
            </p>
          )}
        </Section>

        {/* Positive Signals */}
        {summary.positive_signals && summary.positive_signals.length > 0 && (
          <Section icon={CheckCircle2} title="Positive Signals">
            <ul className="space-y-2">
              {summary.positive_signals.map((s, i) => {
                const cfg = IMPACT_COLORS[s.impact as keyof typeof IMPACT_COLORS] ?? IMPACT_COLORS.MEDIUM;
                return (
                  <li key={i} className={`flex items-start gap-2 rounded-lg px-3 py-2 ${cfg.bg}`}>
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${cfg.dot}`} />
                    <div className="flex-1">
                      <span className={`text-xs font-medium ${cfg.text}`}>{s.signal}</span>
                      <span className={`ml-2 rounded px-1 py-0.5 text-[10px] font-bold uppercase ${cfg.bg} ${cfg.text}`}>
                        {s.impact}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Section>
        )}

        {/* Risk Factors */}
        {summary.risk_factors && summary.risk_factors.length > 0 && (
          <Section icon={AlertTriangle} title="Risk Factors" defaultOpen={true}>
            <ul className="space-y-2">
              {summary.risk_factors.map((r, i) => {
                const cfg = SEVERITY_COLORS[r.severity as keyof typeof SEVERITY_COLORS] ?? SEVERITY_COLORS.MEDIUM;
                return (
                  <li key={i} className={`flex items-start gap-2 rounded-lg px-3 py-2 ${cfg.bg}`}>
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${cfg.dot}`} />
                    <div className="flex-1">
                      <span className={`text-xs font-medium ${cfg.text}`}>{r.risk}</span>
                      <span className={`ml-2 rounded px-1 py-0.5 text-[10px] font-bold uppercase ${cfg.bg} ${cfg.text}`}>
                        {r.severity}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Section>
        )}

        {/* Geographic + Customer mix */}
        <div className="grid gap-4 sm:grid-cols-2">
          {summary.geographic_mix_note && (
            <div className="rounded-lg bg-blue-50 p-4">
              <div className="mb-2 flex items-center gap-2">
                <Globe className="h-4 w-4 text-blue-600" />
                <span className="text-xs font-semibold text-blue-800">Geographic Mix</span>
              </div>
              <p className="text-xs leading-relaxed text-blue-700">
                {summary.geographic_mix_note}
              </p>
            </div>
          )}
          {summary.customer_concentration_note && (
            <div className="rounded-lg bg-purple-50 p-4">
              <div className="mb-2 flex items-center gap-2">
                <Users className="h-4 w-4 text-purple-600" />
                <span className="text-xs font-semibold text-purple-800">
                  Customer Concentration
                </span>
              </div>
              <p className="text-xs leading-relaxed text-purple-700">
                {summary.customer_concentration_note}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

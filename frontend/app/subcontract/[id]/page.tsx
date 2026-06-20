"use client";

export const runtime = "edge";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const ACTION_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  STRONG_BUY_TRIGGER: { label: "STRONG BUY", color: "text-emerald-700", bg: "bg-emerald-50",  border: "border-emerald-400" },
  BUY_TRIGGER:        { label: "BUY",         color: "text-green-700",   bg: "bg-green-50",    border: "border-green-400" },
  MONITOR:            { label: "MONITOR",      color: "text-blue-700",    bg: "bg-blue-50",     border: "border-blue-400" },
  WATCH:              { label: "WATCH",        color: "text-amber-700",   bg: "bg-amber-50",    border: "border-amber-400" },
  UNLIKELY:           { label: "UNLIKELY",     color: "text-gray-500",    bg: "bg-gray-50",     border: "border-gray-300" },
};

interface Beneficiary {
  rank: number;
  beneficiary_isin: string;
  beneficiary_name: string;
  beneficiary_sector: string;
  beneficiary_mcap_cr: number;
  relationship_type: string;
  product_category: string;
  supply_chain_hops: number;
  probability_score: number;
  revenue_impact_cr: number;
  revenue_impact_pct: number;
  confidence_score: number;
  overall_score: number;
  investment_action: string;
  rationale: string;
  key_catalysts: string[];
  key_risks: string[];
  score_breakdown: Record<string, number>;
}

interface Opportunity {
  id: string;
  prime_contractor_name: string;
  prime_contractor_isin: string;
  order_amount_cr: number;
  order_customer: string;
  order_description: string;
  theme: string;
  sub_themes: string[];
  announced_date: string;
  estimated_subcontract_cr: number;
  subcontract_ratio: number;
  beneficiary_count: number;
  beneficiaries: Beneficiary[];
}

function ScoreBar({ value, max = 100, color = "bg-indigo-500" }: { value: number; max?: number; color?: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${(value / max) * 100}%` }} />
      </div>
      <span className="text-xs text-gray-600 w-8 text-right">{value.toFixed(0)}</span>
    </div>
  );
}

function BeneficiaryCard({ ben, rank }: { ben: Beneficiary; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = ACTION_CONFIG[ben.investment_action] || ACTION_CONFIG.UNLIKELY;

  return (
    <div className={`border rounded-xl p-4 ${cfg.border} ${cfg.bg}`}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: rank + name */}
        <div className="flex items-start gap-3">
          <div className="text-2xl font-bold text-gray-300 w-8 text-right leading-none pt-0.5">
            #{rank}
          </div>
          <div>
            <div className="font-semibold text-gray-900 text-base">{ben.beneficiary_name}</div>
            <div className="text-xs text-gray-500 mt-0.5">
              {ben.beneficiary_isin} · {ben.beneficiary_sector} · {ben.product_category}
              {ben.supply_chain_hops > 1 && <span className="ml-1 text-orange-500">(Tier {ben.supply_chain_hops})</span>}
            </div>
          </div>
        </div>

        {/* Right: action badge + scores */}
        <div className="text-right shrink-0">
          <span className={`inline-block px-3 py-1 rounded-full text-xs font-bold border ${cfg.color} ${cfg.bg} ${cfg.border}`}>
            {cfg.label}
          </span>
          <div className="mt-1 text-xs text-gray-500">Score: {ben.overall_score.toFixed(1)}</div>
        </div>
      </div>

      {/* Key metrics */}
      <div className="mt-3 grid grid-cols-3 gap-3">
        <div className="bg-white/70 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-gray-900">{ben.probability_score.toFixed(0)}</div>
          <div className="text-xs text-gray-500">Probability /100</div>
        </div>
        <div className="bg-white/70 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-indigo-700">₹{ben.revenue_impact_cr.toFixed(0)} Cr</div>
          <div className="text-xs text-gray-500">Est. Revenue Impact</div>
        </div>
        <div className="bg-white/70 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-gray-900">{ben.revenue_impact_pct.toFixed(1)}%</div>
          <div className="text-xs text-gray-500">of TTM Revenue</div>
        </div>
      </div>

      {/* Rationale */}
      {ben.rationale && (
        <p className="mt-3 text-sm text-gray-700 leading-relaxed">{ben.rationale}</p>
      )}

      {/* Expand: catalysts + risks + score breakdown */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 text-xs text-gray-400 hover:text-gray-600"
      >
        {expanded ? "▲ Less detail" : "▼ More detail"}
      </button>

      {expanded && (
        <div className="mt-3 grid grid-cols-2 gap-4">
          {/* Catalysts */}
          {ben.key_catalysts?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-green-700 mb-1">Key Catalysts</div>
              <ul className="space-y-1">
                {ben.key_catalysts.map((c, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-1"><span className="text-green-500">✓</span>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Risks */}
          {ben.key_risks?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-red-700 mb-1">Key Risks</div>
              <ul className="space-y-1">
                {ben.key_risks.map((r, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-1"><span className="text-red-400">⚠</span>{r}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Score breakdown */}
          {ben.score_breakdown && (
            <div className="col-span-2 mt-2">
              <div className="text-xs font-semibold text-gray-500 mb-2">Score Breakdown</div>
              <div className="space-y-1.5">
                {Object.entries(ben.score_breakdown)
                  .filter(([k]) => !["hop_penalty", "subcontract_ratio"].includes(k))
                  .map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2">
                      <div className="w-36 text-xs text-gray-500 capitalize">{key.replace(/_/g, " ")}</div>
                      <ScoreBar value={val * 100} max={100} color="bg-indigo-400" />
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [opp, setOpp] = useState<Opportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/v1/subcontract/opportunities/${id}`)
      .then((r) => r.json())
      .then((d) => { setOpp(d); setLoading(false); });
  }, [id]);

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading...</div>;
  if (!opp)   return <div className="flex items-center justify-center h-64 text-gray-400">Opportunity not found.</div>;

  const actions = ["STRONG_BUY_TRIGGER", "BUY_TRIGGER", "MONITOR", "WATCH", "UNLIKELY"];
  const filtered = activeFilter
    ? opp.beneficiaries.filter((b) => b.investment_action === activeFilter)
    : opp.beneficiaries;

  const actionCounts = actions.reduce<Record<string, number>>((acc, a) => {
    acc[a] = opp.beneficiaries.filter((b) => b.investment_action === a).length;
    return acc;
  }, {});

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <a href="/subcontract" className="text-sm text-indigo-600 hover:underline">← All Opportunities</a>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">
          {opp.prime_contractor_name} — ₹{opp.order_amount_cr.toLocaleString("en-IN")} Cr Order
        </h1>
        <div className="flex flex-wrap gap-3 mt-2 text-sm text-gray-600">
          {opp.order_customer && <span>Customer: <strong>{opp.order_customer}</strong></span>}
          <span>Theme: <strong>{opp.theme}</strong></span>
          {opp.announced_date && (
            <span>Date: <strong>{new Date(opp.announced_date).toLocaleDateString("en-IN")}</strong></span>
          )}
        </div>
        {opp.order_description && (
          <p className="mt-2 text-sm text-gray-500 italic max-w-3xl">"{opp.order_description}"</p>
        )}
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">₹{opp.order_amount_cr.toLocaleString("en-IN")}</div>
          <div className="text-xs text-gray-500 mt-1">Order Value (₹ Cr)</div>
        </div>
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-indigo-700">₹{Math.round(opp.estimated_subcontract_cr).toLocaleString("en-IN")}</div>
          <div className="text-xs text-gray-500 mt-1">Est. Subcontract Pool</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{Math.round((opp.subcontract_ratio || 0) * 100)}%</div>
          <div className="text-xs text-gray-500 mt-1">Subcontract Ratio</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{opp.beneficiary_count}</div>
          <div className="text-xs text-gray-500 mt-1">Beneficiary Companies</div>
        </div>
      </div>

      {/* Filter by action */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveFilter(null)}
          className={`px-3 py-1 text-xs rounded-full border ${!activeFilter ? "bg-gray-800 text-white border-gray-800" : "bg-white text-gray-500 border-gray-300"}`}
        >
          All ({opp.beneficiaries.length})
        </button>
        {actions.map((a) => {
          const cfg = ACTION_CONFIG[a];
          return actionCounts[a] > 0 ? (
            <button
              key={a}
              onClick={() => setActiveFilter(activeFilter === a ? null : a)}
              className={`px-3 py-1 text-xs rounded-full border ${activeFilter === a ? `${cfg.bg} ${cfg.color} ${cfg.border}` : "bg-white text-gray-500 border-gray-300"}`}
            >
              {cfg.label} ({actionCounts[a]})
            </button>
          ) : null;
        })}
      </div>

      {/* Beneficiary cards */}
      <div className="space-y-3">
        {filtered.map((ben) => (
          <BeneficiaryCard key={ben.beneficiary_isin} ben={ben} rank={ben.rank} />
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-10 text-gray-400">No beneficiaries for selected filter.</div>
        )}
      </div>
    </div>
  );
}

"use client";

export const runtime = "edge";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

interface Relationship {
  id: string;
  source_isin: string;
  source_name: string;
  target_isin: string;
  target_name: string;
  rel_type: string;
  product_category: string | null;
  strength: number;
  revenue_share_pct: number | null;
  confidence: number;
  evidence_count: number;
}

interface GraphData {
  isin: string;
  company_name: string;
  sector: string | null;
  centrality_score: number | null;
  supply_chain_tier: number | null;
  stats: Record<string, number | string[]>;
  suppliers: Relationship[];
  customers: Relationship[];
}

function StrengthBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-gray-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 bg-gray-100 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">{pct}%</span>
    </div>
  );
}

function RelTable({ rels, title, emptyMsg }: { rels: Relationship[]; title: string; emptyMsg: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-2">{title} ({rels.length})</h3>
      {rels.length === 0 ? (
        <div className="text-sm text-gray-400 italic py-4">{emptyMsg}</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-400 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-3 py-2 text-left">Company</th>
                <th className="px-3 py-2 text-left">Relationship</th>
                <th className="px-3 py-2 text-left">Product</th>
                <th className="px-3 py-2 text-left">Strength</th>
                <th className="px-3 py-2 text-right">Rev Share</th>
                <th className="px-3 py-2 text-right">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rels.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-800">
                      {title.startsWith("Supplier") ? r.source_name : r.target_name}
                    </div>
                    <div className="text-gray-400">
                      {title.startsWith("Supplier") ? r.source_isin : r.target_isin}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">
                      {r.rel_type.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500">{r.product_category || "—"}</td>
                  <td className="px-3 py-2"><StrengthBar value={r.strength} /></td>
                  <td className="px-3 py-2 text-right text-gray-600">
                    {r.revenue_share_pct != null ? `${r.revenue_share_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">
                      {r.evidence_count}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CompanyGraphPage() {
  const { isin } = useParams<{ isin: string }>();
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/v1/subcontract/companies/${isin}/graph`)
      .then((r) => r.json())
      .then((d) => { setGraph(d); setLoading(false); });
  }, [isin]);

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading graph...</div>;
  if (!graph)  return <div className="flex items-center justify-center h-64 text-gray-400">Company not found in graph.</div>;

  const stats = graph.stats;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <a href="/subcontract" className="text-sm text-indigo-600 hover:underline">← Opportunities</a>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">{graph.company_name}</h1>
        <div className="flex gap-4 text-sm text-gray-500 mt-1">
          <span>{isin}</span>
          {graph.sector && <span>{graph.sector}</span>}
          {graph.supply_chain_tier && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${graph.supply_chain_tier === 1 ? "bg-purple-100 text-purple-700" : "bg-gray-100 text-gray-600"}`}>
              Tier {graph.supply_chain_tier}
            </span>
          )}
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{stats.supplier_count ?? 0}</div>
          <div className="text-xs text-gray-500 mt-1">Suppliers</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{stats.customer_count ?? 0}</div>
          <div className="text-xs text-gray-500 mt-1">Customers</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">
            {typeof stats.avg_supplier_strength === "number"
              ? `${Math.round(stats.avg_supplier_strength * 100)}%`
              : "—"}
          </div>
          <div className="text-xs text-gray-500 mt-1">Avg Supplier Strength</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">
            {graph.centrality_score != null ? graph.centrality_score.toFixed(3) : "—"}
          </div>
          <div className="text-xs text-gray-500 mt-1">Centrality Score</div>
        </div>
      </div>

      {/* Graph tables */}
      <div className="space-y-6">
        <RelTable
          rels={graph.suppliers}
          title="Suppliers to this company"
          emptyMsg="No suppliers found in the graph. Run graph rebuild to extract from documents."
        />
        <RelTable
          rels={graph.customers}
          title="Customers of this company"
          emptyMsg="No customer relationships found."
        />
      </div>
    </div>
  );
}

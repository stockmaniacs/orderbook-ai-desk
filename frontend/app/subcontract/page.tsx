"use client";

import { useEffect, useState } from "react";

const ACTION_COLORS: Record<string, string> = {
  STRONG_BUY_TRIGGER: "bg-emerald-100 text-emerald-800 border-emerald-300",
  BUY_TRIGGER:        "bg-green-100  text-green-800  border-green-300",
  MONITOR:            "bg-blue-100   text-blue-800   border-blue-300",
  WATCH:              "bg-amber-100  text-amber-800  border-amber-300",
  UNLIKELY:           "bg-gray-100   text-gray-500   border-gray-200",
};

const THEME_COLORS: Record<string, string> = {
  "POWER_T&D":      "bg-yellow-100 text-yellow-800",
  RAILWAYS:         "bg-blue-100   text-blue-800",
  ROADS_HIGHWAYS:   "bg-orange-100 text-orange-800",
  DEFENCE:          "bg-red-100    text-red-800",
  HYDROCARBON:      "bg-purple-100 text-purple-800",
  GREEN_ENERGY:     "bg-green-100  text-green-800",
  URBAN_INFRA:      "bg-cyan-100   text-cyan-800",
  DATA_CENTRES:     "bg-indigo-100 text-indigo-800",
  WATER_SANITATION: "bg-teal-100   text-teal-800",
  PORTS_WATERWAYS:  "bg-sky-100    text-sky-800",
};

interface OpportunityItem {
  id: string;
  prime_contractor_name: string;
  prime_contractor_isin: string;
  order_amount_cr: number;
  order_customer: string | null;
  theme: string;
  announced_date: string | null;
  estimated_subcontract_cr: number;
  beneficiary_count: number;
  status: string;
  top_beneficiary_name: string | null;
  top_beneficiary_action: string | null;
  top_beneficiary_score: number | null;
}

export default function SubcontractOpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useState("");
  const [minAmount, setMinAmount] = useState("");

  const fetchOpportunities = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (theme) params.set("theme", theme);
    if (minAmount) params.set("min_amount_cr", minAmount);
    params.set("limit", "50");

    const res = await fetch(`/api/v1/subcontract/opportunities?${params}`);
    const data = await res.json();
    setOpportunities(data.items || []);
    setTotal(data.total || 0);
    setLoading(false);
  };

  useEffect(() => { fetchOpportunities(); }, [theme, minAmount]);

  const themes = [
    "", "POWER_T&D", "RAILWAYS", "ROADS_HIGHWAYS", "DEFENCE", "HYDROCARBON",
    "GREEN_ENERGY", "URBAN_INFRA", "DATA_CENTRES", "WATER_SANITATION", "PORTS_WATERWAYS",
  ];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Subcontract Opportunities</h1>
          <p className="text-sm text-gray-500 mt-1">
            {total} opportunities — find listed companies that benefit from large order wins
          </p>
        </div>
        <a
          href="/subcontract-dashboard.html"
          target="_blank"
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
        >
          Open Dashboard
        </a>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <select
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          {themes.map((t) => (
            <option key={t} value={t}>{t || "All Themes"}</option>
          ))}
        </select>

        <input
          type="number"
          placeholder="Min Order Size (₹ Cr)"
          value={minAmount}
          onChange={(e) => setMinAmount(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-52"
        />

        <button
          onClick={fetchOpportunities}
          className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-700"
        >
          Refresh
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-20 text-gray-400">Loading opportunities...</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Prime Contractor</th>
                <th className="px-4 py-3 text-left">Customer</th>
                <th className="px-4 py-3 text-right">Order (₹ Cr)</th>
                <th className="px-4 py-3 text-right">Sub-contract (₹ Cr)</th>
                <th className="px-4 py-3 text-left">Theme</th>
                <th className="px-4 py-3 text-center">Beneficiaries</th>
                <th className="px-4 py-3 text-left">Top Pick</th>
                <th className="px-4 py-3 text-left">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {opportunities.map((opp) => (
                <tr
                  key={opp.id}
                  onClick={() => window.location.href = `/subcontract/${opp.id}`}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{opp.prime_contractor_name}</div>
                    <div className="text-xs text-gray-400">{opp.prime_contractor_isin}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-600 max-w-[160px] truncate">
                    {opp.order_customer || "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-gray-900">
                    ₹{opp.order_amount_cr.toLocaleString("en-IN")}
                  </td>
                  <td className="px-4 py-3 text-right text-indigo-700 font-medium">
                    ₹{opp.estimated_subcontract_cr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${THEME_COLORS[opp.theme] || "bg-gray-100 text-gray-700"}`}>
                      {opp.theme}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="font-medium text-gray-700">{opp.beneficiary_count}</span>
                  </td>
                  <td className="px-4 py-3">
                    {opp.top_beneficiary_name ? (
                      <div>
                        <div className="text-xs font-medium text-gray-800">{opp.top_beneficiary_name}</div>
                        <span className={`inline-block mt-0.5 px-1.5 py-0.5 text-xs border rounded ${ACTION_COLORS[opp.top_beneficiary_action || ""] || ""}`}>
                          {opp.top_beneficiary_action?.replace("_TRIGGER", "").replace("_", " ")}
                        </span>
                      </div>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                    {opp.announced_date ? new Date(opp.announced_date).toLocaleDateString("en-IN") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {opportunities.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              No opportunities found. Trigger analysis for a new order win.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

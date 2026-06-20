"use client";

import { useState } from "react";
import { OrderAnnouncement, PaginatedOrders, formatCr } from "@/lib/api/order-tracking";
import {
  ArrowUpDown,
  ExternalLink,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Globe,
  Home,
  RefreshCw,
} from "lucide-react";

interface Props {
  data: PaginatedOrders;
  onPageChange: (page: number) => void;
  onFilterChange: (filters: { order_type?: string; min_amount_cr?: number }) => void;
  isLoading?: boolean;
}

const ORDER_TYPE_ICONS: Record<string, React.ReactNode> = {
  EXPORT: <Globe className="h-3 w-3 text-blue-500" />,
  DOMESTIC: <Home className="h-3 w-3 text-emerald-500" />,
  MIXED: <RefreshCw className="h-3 w-3 text-purple-500" />,
};

const SECTOR_COLORS: Record<string, string> = {
  INFRASTRUCTURE: "bg-orange-100 text-orange-700",
  DEFENSE: "bg-red-100 text-red-700",
  POWER: "bg-yellow-100 text-yellow-700",
  RAILWAYS: "bg-blue-100 text-blue-700",
  OIL_GAS: "bg-gray-100 text-gray-700",
  RENEWABLE: "bg-emerald-100 text-emerald-700",
  TELECOM: "bg-indigo-100 text-indigo-700",
  INDUSTRIAL: "bg-purple-100 text-purple-700",
  CHEMICAL: "bg-pink-100 text-pink-700",
  OTHER: "bg-gray-100 text-gray-600",
};

function OrderRow({ order }: { order: OrderAnnouncement }) {
  const [expanded, setExpanded] = useState(false);
  const sectorClass = SECTOR_COLORS[order.sector_category ?? "OTHER"] ?? "bg-gray-100 text-gray-600";

  return (
    <>
      <tr
        onClick={() => setExpanded(!expanded)}
        className="cursor-pointer border-b border-gray-50 hover:bg-gray-50/70 transition-colors"
      >
        <td className="py-3.5 pl-4 pr-2">
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-gray-900">
              {formatCr(order.order_amount_cr)}
            </span>
            {order.order_amount_raw && (
              <span className="text-xs text-gray-400">{order.order_amount_raw}</span>
            )}
          </div>
        </td>
        <td className="py-3.5 px-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-gray-800">
              {order.customer_name ?? (
                <span className="text-gray-400 italic">Undisclosed</span>
              )}
            </span>
            <div className="flex items-center gap-1">
              {ORDER_TYPE_ICONS[order.order_type ?? "DOMESTIC"]}
              <span className="text-[11px] text-gray-400">{order.order_type ?? "DOMESTIC"}</span>
            </div>
          </div>
        </td>
        <td className="py-3.5 px-2">
          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${sectorClass}`}>
            {(order.sector_category ?? "OTHER").replace(/_/g, " ")}
          </span>
        </td>
        <td className="py-3.5 px-2 text-sm text-gray-600">
          {order.duration_months
            ? `${order.duration_months} months`
            : order.execution_end
            ? new Date(order.execution_end).getFullYear()
            : "—"}
        </td>
        <td className="py-3.5 px-2 text-sm text-gray-500">
          {new Date(order.announced_date).toLocaleDateString("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </td>
        <td className="py-3.5 px-2 text-xs text-gray-400">{order.quarter}</td>
        <td className="py-3.5 pl-2 pr-4">
          <div className="flex items-center gap-2">
            {order.source_url && (
              <a
                href={order.source_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
              {order.source}
            </span>
          </div>
        </td>
      </tr>

      {/* Expanded row */}
      {expanded && (
        <tr className="bg-indigo-50/40">
          <td colSpan={7} className="px-6 py-3 text-xs leading-relaxed text-gray-600">
            <div className="grid grid-cols-2 gap-4">
              {order.project_description && (
                <div>
                  <span className="font-semibold text-gray-700 block mb-1">Project Description</span>
                  {order.project_description}
                </div>
              )}
              <div className="space-y-1">
                {order.project_type && (
                  <div>
                    <span className="font-medium text-gray-700">Type: </span>
                    {order.project_type}
                  </div>
                )}
                {order.execution_start && (
                  <div>
                    <span className="font-medium text-gray-700">Start: </span>
                    {new Date(order.execution_start).toLocaleDateString("en-IN")}
                  </div>
                )}
                {order.execution_end && (
                  <div>
                    <span className="font-medium text-gray-700">End: </span>
                    {new Date(order.execution_end).toLocaleDateString("en-IN")}
                  </div>
                )}
                {order.is_repeat_order && (
                  <div className="inline-block rounded-full bg-purple-100 px-2 py-0.5 text-purple-700 font-medium">
                    Repeat Order
                  </div>
                )}
                {order.extraction_confidence != null && (
                  <div>
                    <span className="font-medium text-gray-700">AI confidence: </span>
                    {(order.extraction_confidence * 100).toFixed(0)}%
                  </div>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function OrderTable({ data, onPageChange, onFilterChange, isLoading }: Props) {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [minAmount, setMinAmount] = useState("");

  const handleFilter = () => {
    onFilterChange({
      order_type: typeFilter || undefined,
      min_amount_cr: minAmount ? parseFloat(minAmount) : undefined,
    });
  };

  const filtered = data.items.filter(
    (o) =>
      !search ||
      o.customer_name?.toLowerCase().includes(search.toLowerCase()) ||
      o.project_description?.toLowerCase().includes(search.toLowerCase()) ||
      o.sector_category?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      {/* Toolbar */}
      <div className="border-b border-gray-100 px-4 py-3 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-gray-900 mr-2">Order Announcements</h3>

        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customer, project..."
            className="w-full rounded-lg border border-gray-200 py-2 pl-8 pr-3 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>

        {/* Type filter */}
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); }}
          className="rounded-lg border border-gray-200 py-2 px-3 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
        >
          <option value="">All Types</option>
          <option value="DOMESTIC">Domestic</option>
          <option value="EXPORT">Export</option>
          <option value="MIXED">Mixed</option>
        </select>

        {/* Min amount */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Min ₹</span>
          <input
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
            placeholder="Cr"
            className="w-20 rounded-lg border border-gray-200 py-2 px-2 text-xs focus:outline-none"
          />
          <span className="text-xs text-gray-400">Cr</span>
        </div>

        <button
          onClick={handleFilter}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 transition-colors"
        >
          <Filter className="h-3.5 w-3.5" />
          Filter
        </button>

        <span className="ml-auto text-xs text-gray-400">
          {data.total.toLocaleString()} orders
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              {["Amount", "Customer / Type", "Sector", "Duration", "Date", "Quarter", ""].map(
                (h) => (
                  <th
                    key={h}
                    className="py-2.5 px-2 first:pl-4 last:pr-4 text-[11px] font-semibold uppercase tracking-wide text-gray-500"
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-sm text-gray-400">
                  Loading orders…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-sm text-gray-400">
                  No orders found
                </td>
              </tr>
            ) : (
              filtered.map((order) => <OrderRow key={order.id} order={order} />)
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data.total > data.limit && (
        <div className="border-t border-gray-100 px-4 py-3 flex items-center justify-between">
          <span className="text-xs text-gray-500">
            Page {data.page} of {Math.ceil(data.total / data.limit)}
          </span>
          <div className="flex items-center gap-2">
            <button
              disabled={data.page === 1}
              onClick={() => onPageChange(data.page - 1)}
              className="rounded-lg border border-gray-200 p-1.5 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              disabled={data.page >= Math.ceil(data.total / data.limit)}
              onClick={() => onPageChange(data.page + 1)}
              className="rounded-lg border border-gray-200 p-1.5 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

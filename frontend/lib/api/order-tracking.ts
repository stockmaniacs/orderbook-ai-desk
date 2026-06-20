/**
 * Order Tracking API Client
 * Typed fetch wrapper for all order tracking endpoints.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface OrderAnnouncement {
  id: string;
  source: string;
  source_id: string;
  source_url?: string;
  isin: string;
  company_name: string;
  symbol_nse?: string;
  symbol_bse?: string;
  sector?: string;
  customer_name?: string;
  order_amount_cr?: number;
  order_amount_raw?: string;
  order_currency: string;
  order_type?: "DOMESTIC" | "EXPORT" | "MIXED";
  project_description?: string;
  announced_date: string;
  execution_start?: string;
  execution_end?: string;
  duration_months?: number;
  sector_category?: string;
  project_type?: string;
  is_repeat_order: boolean;
  fiscal_year?: number;
  quarter?: string;
  extraction_confidence?: number;
  processing_status: string;
  created_at: string;
}

export interface SnapshotPoint {
  quarter: string;
  fiscal_year: number;
  quarter_num: number;
  snapshot_date: string;
  opening_order_book_cr?: number;
  new_orders_cr?: number;
  revenue_executed_cr?: number;
  closing_order_book_cr?: number;
  order_count: number;
  domestic_orders_cr?: number;
  export_orders_cr?: number;
  quarterly_revenue_cr?: number;
  annual_revenue_ttm_cr?: number;
  is_estimated: boolean;
}

export interface ScenarioAssumptions {
  quarterly_inflow_growth_pct: number;
  win_rate_assumption: string;
  key_driver: string;
}

export interface OrderBookMetrics {
  isin: string;
  company_name?: string;
  current_order_book_cr?: number;
  last_order_date?: string;
  total_orders_count: number;
  ttm_orders_won_cr?: number;
  // Growth
  order_inflow_growth_yoy_pct?: number;
  order_book_growth_yoy_pct?: number;
  order_book_cagr_3y?: number;
  order_book_cagr_5y?: number;
  // Ratios
  order_book_to_sales?: number;
  bill_to_book_ratio?: number;
  order_to_sales_trend?: "IMPROVING" | "STABLE" | "DETERIORATING";
  // Acceleration
  order_acceleration_score?: number;
  order_momentum?: "ACCELERATING" | "STABLE" | "DECELERATING";
  // Scenarios
  bull_case_ob_cr?: number;
  base_case_ob_cr?: number;
  bear_case_ob_cr?: number;
  scenario_horizon_quarters: number;
  scenario_assumptions?: {
    bull: ScenarioAssumptions;
    base: ScenarioAssumptions;
    bear: ScenarioAssumptions;
  };
  // Mix
  domestic_pct?: number;
  export_pct?: number;
  sector_breakdown?: Record<string, number>;
  customer_concentration?: Array<{ name: string; amount_cr: number; pct: number }>;
  updated_at: string;
}

export interface RiskFactor {
  risk: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
}

export interface PositiveSignal {
  signal: string;
  impact: "HIGH" | "MEDIUM" | "LOW";
}

export interface OrderAISummary {
  id: string;
  isin: string;
  generated_at: string;
  trend?: "IMPROVING" | "STABLE" | "DETERIORATING";
  trend_confidence?: number;
  executive_summary?: string;
  pipeline_analysis?: string;
  customer_concentration_note?: string;
  geographic_mix_note?: string;
  risk_factors?: RiskFactor[];
  positive_signals?: PositiveSignal[];
  key_customers?: Array<{ name: string; pct: number }>;
  bull_narrative?: string;
  base_narrative?: string;
  bear_narrative?: string;
  ai_verdict?: string;
  model_version?: string;
}

export interface OrderTrackingDashboard {
  isin: string;
  company_name: string;
  sector?: string;
  metrics?: OrderBookMetrics;
  history: {
    isin: string;
    company_name: string;
    snapshots: SnapshotPoint[];
  };
  recent_orders: OrderAnnouncement[];
  ai_summary?: OrderAISummary;
}

export interface ChartsData {
  quarterly: Array<{
    quarter: string;
    order_book_cr?: number;
    new_orders_cr?: number;
    executed_cr?: number;
    ob_to_sales?: number;
  }>;
  yoy_growth: Array<{
    fiscal_year: number;
    ttm_orders_cr?: number;
    yoy_growth_pct?: number;
  }>;
  rolling: Array<{
    date: string;
    rolling_4q_cr?: number;
  }>;
}

export interface PaginatedOrders {
  items: OrderAnnouncement[];
  total: number;
  page: number;
  limit: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ─── API Functions ────────────────────────────────────────────────────────────

export const orderTrackingApi = {
  /** Full dashboard for a stock */
  getDashboard: (isin: string) =>
    apiFetch<OrderTrackingDashboard>(`/api/v1/order-tracking/${isin}/dashboard`),

  /** Computed metrics + scenarios */
  getMetrics: (isin: string, refresh = false) =>
    apiFetch<OrderBookMetrics>(
      `/api/v1/order-tracking/${isin}/metrics?refresh=${refresh}`
    ),

  /** Paginated order list */
  getOrders: (
    isin: string,
    params: { page?: number; limit?: number; order_type?: string; min_amount_cr?: number } = {}
  ) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return apiFetch<PaginatedOrders>(
      `/api/v1/order-tracking/${isin}/orders${qs ? `?${qs}` : ""}`
    );
  },

  /** Chart data */
  getCharts: (isin: string) =>
    apiFetch<ChartsData>(`/api/v1/order-tracking/${isin}/charts`),

  /** Quarterly snapshot history */
  getHistory: (isin: string) =>
    apiFetch<{ isin: string; company_name: string; snapshots: SnapshotPoint[] }>(
      `/api/v1/order-tracking/${isin}/history`
    ),

  /** AI summary */
  getAISummary: (isin: string) =>
    apiFetch<OrderAISummary>(`/api/v1/order-tracking/${isin}/ai-summary`),

  /** Regenerate AI summary */
  regenerateAISummary: (isin: string) =>
    apiFetch<{ detail: string }>(
      `/api/v1/order-tracking/${isin}/ai-summary?regenerate=true`,
      { method: "GET" }
    ),

  /** Latest large orders across universe */
  getUniverseRecent: (params: {
    page?: number;
    limit?: number;
    min_amount_cr?: number;
    sector?: string;
    order_type?: string;
  } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return apiFetch<PaginatedOrders>(
      `/api/v1/order-tracking/universe/recent${qs ? `?${qs}` : ""}`
    );
  },

  /** Leaderboard by acceleration score */
  getLeaderboard: (limit = 20) =>
    apiFetch<OrderBookMetrics[]>(
      `/api/v1/order-tracking/universe/leaderboard?limit=${limit}`
    ),

  /** Trigger scrape */
  triggerScrape: (days_back = 1) =>
    apiFetch<{ status: string }>(
      `/api/v1/order-tracking/admin/trigger-scrape?days_back=${days_back}`,
      { method: "POST" }
    ),
};

// ─── Formatters ───────────────────────────────────────────────────────────────

export function formatCr(value?: number | null, decimals = 0): string {
  if (value == null) return "—";
  if (value >= 10000) return `₹${(value / 10000).toFixed(1)}L Cr`;
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: decimals })} Cr`;
}

export function formatPct(value?: number | null): string {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function formatMultiple(value?: number | null): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}x`;
}

export function getTrendColor(trend?: string): string {
  switch (trend) {
    case "IMPROVING":
    case "ACCELERATING":
      return "text-emerald-600";
    case "DETERIORATING":
    case "DECELERATING":
      return "text-red-500";
    default:
      return "text-amber-500";
  }
}

export function getMomentumBadge(
  momentum?: string
): { label: string; className: string } {
  switch (momentum) {
    case "ACCELERATING":
      return { label: "Accelerating ↑", className: "bg-emerald-100 text-emerald-800" };
    case "DECELERATING":
      return { label: "Decelerating ↓", className: "bg-red-100 text-red-800" };
    default:
      return { label: "Stable →", className: "bg-amber-100 text-amber-800" };
  }
}

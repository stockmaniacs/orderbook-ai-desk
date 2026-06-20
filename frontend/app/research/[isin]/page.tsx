"use client";

export const runtime = "edge";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, RefreshCw, BookOpen, FileText,
  TrendingUp, TrendingDown, Shield, Zap,
  ChevronDown, ChevronUp, AlertCircle, Star,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────
interface SwotItem { point: string; evidence?: string; confidence?: number }
interface Thesis {
  one_liner: string | null;
  thesis_text: string | null;
  strengths: SwotItem[] | null;
  weaknesses: SwotItem[] | null;
  opportunities: SwotItem[] | null;
  threats: SwotItem[] | null;
  bull_case: string | null; bull_cagr_pct: number | null;
  base_case: string | null; base_cagr_pct: number | null;
  bear_case: string | null; bear_cagr_pct: number | null;
  bull_probability: number | null;
  base_probability: number | null;
  bear_probability: number | null;
  current_price: number | null;
  fair_value_low: number | null;
  fair_value_mid: number | null;
  fair_value_high: number | null;
  target_price_12m: number | null;
  expected_cagr_3y: number | null;
  rating: string | null;
  confidence_score: number | null;
  version: number;
  last_updated: string | null;
  update_trigger: string | null;
}
interface ResearchField {
  field_name: string; field_category: string | null;
  value_text: string | null; value_json: any;
  confidence: number | null; fiscal_period: string | null;
  is_stale: boolean; version: number; last_updated: string | null;
}
interface Company {
  isin: string; symbol_nse: string | null; company_name: string;
  sector: string | null; industry: string | null;
  market_cap_cr: number | null; market_cap_cat: string | null;
  research_status: string | null; last_research_date: string | null;
}
interface Dashboard {
  company: Company; thesis: Thesis | null;
  fields: ResearchField[]; latest_report: { markdown_content: string } | null;
  recent_docs: { id: string; doc_type: string; title: string; published_date: string; source: string }[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const RATING_STYLE: Record<string, string> = {
  STRONG_BUY: "bg-emerald-100 text-emerald-800 border-emerald-200",
  BUY:        "bg-emerald-50 text-emerald-700 border-emerald-100",
  ACCUMULATE: "bg-blue-50 text-blue-700 border-blue-100",
  HOLD:       "bg-amber-50 text-amber-700 border-amber-100",
  REDUCE:     "bg-orange-50 text-orange-700 border-orange-100",
  SELL:       "bg-red-100 text-red-700 border-red-200",
  AVOID:      "bg-gray-100 text-gray-600 border-gray-200",
};

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-gray-100 ${className}`} />;
}

function Section({ title, icon, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50/50 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-900">
          {icon}{title}
        </span>
        {open ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
}

function SwotList({ items, emoji }: { items: SwotItem[] | null; emoji: string }) {
  if (!items?.length) return <p className="text-sm text-gray-400 italic">Not yet assessed.</p>;
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span>{emoji}</span>
          <div>
            <p className="font-medium text-gray-800">{item.point}</p>
            {item.evidence && <p className="text-gray-500 text-xs mt-0.5">{item.evidence}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ScenarioCard({
  label, emoji, text, cagr, prob, fv, currentPrice, style,
}: {
  label: string; emoji: string; text: string | null; cagr: number | null;
  prob: number | null; fv: number | null; currentPrice: number | null;
  style: string;
}) {
  const upside = fv && currentPrice ? ((fv / currentPrice) - 1) * 100 : null;
  return (
    <div className={`rounded-xl border p-5 space-y-3 ${style}`}>
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-sm">{emoji} {label} Case</h4>
        {prob != null && <span className="text-xs font-medium opacity-70">{prob.toFixed(0)}% probability</span>}
      </div>
      <div className="flex gap-4">
        {cagr != null && (
          <div>
            <p className="text-[11px] opacity-60 uppercase tracking-wide">3Y CAGR</p>
            <p className="font-bold text-lg">{cagr > 0 ? "+" : ""}{cagr.toFixed(1)}%</p>
          </div>
        )}
        {fv != null && (
          <div>
            <p className="text-[11px] opacity-60 uppercase tracking-wide">Fair Value</p>
            <p className="font-bold text-lg">₹{fv.toFixed(0)}</p>
          </div>
        )}
        {upside != null && (
          <div>
            <p className="text-[11px] opacity-60 uppercase tracking-wide">Upside</p>
            <p className={`font-bold text-lg ${upside >= 0 ? "text-current" : ""}`}>{upside > 0 ? "+" : ""}{upside.toFixed(1)}%</p>
          </div>
        )}
      </div>
      {text && <p className="text-sm leading-relaxed opacity-80">{text}</p>}
    </div>
  );
}

function FieldCard({ field }: { field: ResearchField }) {
  const [open, setOpen] = useState(false);
  const label = field.field_name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const text = field.value_text || (Array.isArray(field.value_json)
    ? field.value_json.map((v: any) => (typeof v === "string" ? `• ${v}` : `• ${v.point || JSON.stringify(v)}`)).join("\n")
    : field.value_json ? JSON.stringify(field.value_json, null, 2) : null);

  if (!text) return null;
  const preview = text.length > 200 ? text.slice(0, 200) + "…" : text;

  return (
    <div className={`rounded-lg border p-4 ${field.is_stale ? "border-amber-200 bg-amber-50/30" : "border-gray-100 bg-gray-50/30"}`}>
      <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => setOpen(!open)}>
        <div className="flex-1">
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{label}</p>
          <p className="text-sm text-gray-700 mt-1 whitespace-pre-line leading-relaxed">{open ? text : preview}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {field.confidence != null && (
            <span className="text-[10px] text-gray-400">{(field.confidence * 100).toFixed(0)}% conf</span>
          )}
          {field.fiscal_period && (
            <span className="text-[10px] bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">{field.fiscal_period}</span>
          )}
          {field.is_stale && <span className="text-[10px] text-amber-600 font-medium">Stale</span>}
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function CompanyResearchPage() {
  const { isin } = useParams<{ isin: string }>();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "report" | "docs">("overview");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/research/${isin}`);
      if (!res.ok) throw new Error(res.statusText);
      setData(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [isin]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleTrigger = async () => {
    setTriggering(true);
    await fetch(`/api/v1/research/${isin}/trigger`, { method: "POST" });
    setTimeout(() => { setTriggering(false); fetchData(); }, 5000);
  };

  if (loading) return (
    <div className="p-6 space-y-4 max-w-screen-xl mx-auto">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-80" /><Skeleton className="h-60" />
    </div>
  );

  if (error || !data) return (
    <div className="p-6 max-w-screen-xl mx-auto">
      <div className="rounded-xl border border-red-100 bg-red-50 p-10 text-center">
        <AlertCircle className="mx-auto h-10 w-10 text-red-400 mb-3" />
        <p className="text-red-700 font-medium">{error ?? "Company not found"}</p>
        <Link href="/research" className="mt-4 inline-block text-sm text-red-600 underline">← Back to Universe</Link>
      </div>
    </div>
  );

  const { company, thesis: t, fields, latest_report, recent_docs } = data;
  const fieldsByCategory: Record<string, ResearchField[]> = {};
  for (const f of fields) {
    const cat = f.field_category || "OTHER";
    (fieldsByCategory[cat] ||= []).push(f);
  }

  const upside = t?.current_price && t?.target_price_12m
    ? ((t.target_price_12m / t.current_price) - 1) * 100 : null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-screen-xl">
          <div className="mb-3 flex items-center gap-2 text-sm text-gray-500">
            <Link href="/research" className="flex items-center gap-1 hover:text-gray-700">
              <ArrowLeft className="h-3.5 w-3.5" /> Research Universe
            </Link>
            <span>/</span>
            <span className="text-gray-900 font-medium">{company.symbol_nse ?? isin}</span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100">
                <BookOpen className="h-6 w-6 text-indigo-600" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">{company.company_name}</h1>
                <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                  <span className="text-sm text-gray-500">{isin}</span>
                  {company.sector && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{company.sector}</span>
                  )}
                  {t?.rating && (
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${RATING_STYLE[t.rating] ?? ""}`}>
                      {t.rating.replace("_", " ")}
                    </span>
                  )}
                  {upside != null && (
                    <span className={`flex items-center gap-1 text-xs font-semibold ${upside >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                      {upside >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {upside > 0 ? "+" : ""}{upside.toFixed(1)}% upside
                    </span>
                  )}
                </div>
              </div>
            </div>
            <button
              onClick={handleTrigger}
              disabled={triggering}
              className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${triggering ? "animate-spin" : ""}`} />
              {triggering ? "Queued…" : "Refresh Research"}
            </button>
          </div>

          {/* Tabs */}
          <div className="mt-4 flex gap-1 border-b border-gray-200 -mb-px">
            {(["overview", "report", "docs"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab ? "border-indigo-600 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {tab === "overview" ? "Overview" : tab === "report" ? "Full Report" : "Documents"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-screen-xl px-6 py-6">

        {/* ── OVERVIEW TAB ─────────────────────────────────────────────── */}
        {activeTab === "overview" && (
          <div className="space-y-5">
            {/* Quick stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Market Cap", value: company.market_cap_cr ? `₹${(company.market_cap_cr / 1000).toFixed(1)}K Cr` : "—" },
                { label: "Current Price", value: t?.current_price ? `₹${t.current_price.toFixed(2)}` : "—" },
                { label: "Target (12M)", value: t?.target_price_12m ? `₹${t.target_price_12m.toFixed(0)}` : "—" },
                { label: "3Y CAGR Est.", value: t?.expected_cagr_3y ? `${t.expected_cagr_3y > 0 ? "+" : ""}${t.expected_cagr_3y.toFixed(1)}%` : "—" },
              ].map(s => (
                <div key={s.label} className="rounded-xl bg-white border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{s.label}</p>
                  <p className="text-xl font-bold text-gray-900 mt-1">{s.value}</p>
                </div>
              ))}
            </div>

            {/* One-liner + confidence */}
            {t?.one_liner && (
              <div className="rounded-xl bg-indigo-50 border border-indigo-100 px-5 py-4 flex items-start gap-3">
                <Star className="h-5 w-5 text-indigo-500 shrink-0 mt-0.5" />
                <p className="text-sm font-medium text-indigo-900">{t.one_liner}</p>
                {t.confidence_score != null && (
                  <span className="ml-auto shrink-0 text-xs text-indigo-500">Confidence: {t.confidence_score.toFixed(0)}/100</span>
                )}
              </div>
            )}

            {/* Investment Thesis */}
            <Section title="Investment Thesis" icon={<BookOpen className="h-4 w-4 text-indigo-500" />}>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                {t?.thesis_text ?? "Not yet generated. Trigger a research run to populate."}
              </p>
            </Section>

            {/* SWOT */}
            <Section title="SWOT Analysis" icon={<Shield className="h-4 w-4 text-purple-500" />}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div><p className="text-xs font-semibold text-emerald-700 uppercase mb-2">Strengths</p><SwotList items={t?.strengths ?? null} emoji="✅" /></div>
                <div><p className="text-xs font-semibold text-red-600 uppercase mb-2">Weaknesses</p><SwotList items={t?.weaknesses ?? null} emoji="⚠️" /></div>
                <div><p className="text-xs font-semibold text-blue-600 uppercase mb-2">Opportunities</p><SwotList items={t?.opportunities ?? null} emoji="🚀" /></div>
                <div><p className="text-xs font-semibold text-orange-600 uppercase mb-2">Threats</p><SwotList items={t?.threats ?? null} emoji="🔴" /></div>
              </div>
            </Section>

            {/* Scenarios */}
            <Section title="Bull / Base / Bear Scenarios" icon={<Zap className="h-4 w-4 text-amber-500" />}>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ScenarioCard label="Bull" emoji="🟢" text={t?.bull_case ?? null} cagr={t?.bull_cagr_pct ?? null}
                  prob={t?.bull_probability ?? null} fv={t?.fair_value_high ?? null}
                  currentPrice={t?.current_price ?? null}
                  style="bg-emerald-50 border-emerald-200 text-emerald-900" />
                <ScenarioCard label="Base" emoji="🔵" text={t?.base_case ?? null} cagr={t?.base_cagr_pct ?? null}
                  prob={t?.base_probability ?? null} fv={t?.fair_value_mid ?? null}
                  currentPrice={t?.current_price ?? null}
                  style="bg-blue-50 border-blue-200 text-blue-900" />
                <ScenarioCard label="Bear" emoji="🔴" text={t?.bear_case ?? null} cagr={t?.bear_cagr_pct ?? null}
                  prob={t?.bear_probability ?? null} fv={t?.fair_value_low ?? null}
                  currentPrice={t?.current_price ?? null}
                  style="bg-red-50 border-red-200 text-red-900" />
              </div>
            </Section>

            {/* Research fields by category */}
            {Object.entries(fieldsByCategory).map(([cat, catFields]) => (
              <Section key={cat} title={cat.replace("_", " ")} icon={<FileText className="h-4 w-4 text-gray-400" />} defaultOpen={false}>
                <div className="space-y-3">
                  {catFields.map(f => <FieldCard key={f.field_name} field={f} />)}
                </div>
              </Section>
            ))}
          </div>
        )}

        {/* ── REPORT TAB ───────────────────────────────────────────────── */}
        {activeTab === "report" && (
          <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-6">
            {latest_report ? (
              <article
                className="prose prose-sm prose-indigo max-w-none"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(latest_report.markdown_content) }}
              />
            ) : (
              <div className="py-16 text-center">
                <FileText className="mx-auto h-10 w-10 text-gray-300 mb-3" />
                <p className="text-gray-500">No report generated yet.</p>
                <button onClick={handleTrigger} className="mt-4 text-sm text-indigo-600 underline">
                  Trigger research run
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── DOCS TAB ─────────────────────────────────────────────────── */}
        {activeTab === "docs" && (
          <div className="rounded-xl bg-white border border-gray-100 shadow-sm overflow-hidden">
            <div className="divide-y divide-gray-50">
              {recent_docs.length === 0 && (
                <p className="py-10 text-center text-sm text-gray-400">No documents fetched yet.</p>
              )}
              {recent_docs.map(doc => (
                <div key={doc.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50/50">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{doc.title || doc.doc_type}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{doc.source} · {doc.published_date}</p>
                  </div>
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{doc.doc_type.replace("_", " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Minimal markdown → HTML for report tab
function markdownToHtml(md: string): string {
  return md
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/_(.+?)_/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, s => `<ul>${s}</ul>`)
    .replace(/^\|(.+)\|$/gm, row => {
      const cells = row.split("|").filter(Boolean).map(c =>
        `<td class="border border-gray-200 px-3 py-1.5 text-sm">${c.trim()}</td>`
      ).join("");
      return `<tr>${cells}</tr>`;
    })
    .replace(/(<tr>.*<\/tr>\n?)+/g, s => `<table class="border-collapse w-full my-3">${s}</table>`)
    .replace(/^---+$/gm, "<hr>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[htuol])/gm, "")
    || md;
}

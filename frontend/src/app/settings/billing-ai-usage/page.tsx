"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

interface BillingRecord {
  id: string;
  date: string;
  description: string;
  subtext: string;
  amount: number;
  status: "paid" | "pending";
}

interface AiUsageRecord {
  id: string;
  date: string;
  feature: string;
  subtext: string;
  tokens: number;
  estimatedCost: number;
}

interface AiUsageSummary {
  estimatedCost: number;
  tokensUsed: number;
  cycleEnds: string;
  periodLabel: string;
}

function formatCurrency(value: number) {
  return "$" + value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function SidebarNav() {
  const adminItems = [
    { label: "Workspace", active: false },
    { label: "Roles & access", active: false },
    { label: "Integrations", active: false },
    { label: "Billing & AI Usage", active: true },
  ];
  const opsItems = ["Overview", "People", "Scheduling", "Time & attendance", "Payroll", "Analytics"];

  return (
    <div className="flex w-64 flex-shrink-0 flex-col border-r border-white/10 px-4 py-6">
      <div className="mb-6 flex items-center gap-3 px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
            <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-bold leading-tight">Elevare</p>
          <p className="text-xs text-gray-500">Workforce OS</p>
        </div>
      </div>

      <div className="mb-6 flex items-center justify-between rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2.5">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">Northstar Retail</p>
          <p className="truncate text-xs text-gray-500">HR Administrator</p>
        </div>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0 text-gray-500">
          <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
        </svg>
      </div>

      <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-gray-600">Operations</p>
      <nav className="mb-6 flex flex-col gap-1">
        {opsItems.map(function (item) {
          return (
            <a key={item} href="#" className="rounded-lg px-3 py-2 text-sm text-gray-400 transition hover:bg-white/5 hover:text-gray-200">
              {item}
            </a>
          );
        })}
      </nav>

      <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-gray-600">Administration</p>
      <nav className="flex flex-col gap-1">
        {adminItems.map(function (item) {
          const isActive = item.active;
          let linkClass = "rounded-lg px-3 py-2 text-sm transition ";
          if (isActive) {
            linkClass = linkClass + "bg-indigo-500/15 font-medium text-indigo-300";
          } else {
            linkClass = linkClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
          }
          return (
            <a key={item.label} href="#" className={linkClass}>
              {item.label}
            </a>
          );
        })}
      </nav>

      <div className="mt-auto flex items-center gap-3 border-t border-white/10 pt-4">
        <div className="h-9 w-9 rounded-full bg-white/10" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">Maya Chen</p>
          <p className="truncate text-xs text-gray-500">maya@northstar.co</p>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: "paid" | "pending" }) {
  if (status === "paid") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Paid
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400">
      <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> Pending
    </span>
  );
}

export default function BillingAiUsagePage() {
  const [billing, setBilling] = useState<BillingRecord[]>([]);
  const [aiUsage, setAiUsage] = useState<AiUsageRecord[]>([]);
  const [summary, setSummary] = useState<AiUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(function () {
    let cancelled = false;

    // NOTE: real fetch wiring goes here once NEXT_PUBLIC_API_URL is set.
    // Example:
    //   apiFetch("/billing/history").catch((err) => {
    //     if (err instanceof ApiError) setError(err.message);
    //     else if (err instanceof Error) setError(err.message);
    //   });
    // Using mock data below in the meantime.

    setTimeout(function () {
      if (cancelled) return;
      setBilling([
        { id: "1", date: "Sep 01, 2026", description: "Elevare Workforce OS", subtext: "September 2026 - 248 active employees", amount: 4216.0, status: "pending" },
        { id: "2", date: "Aug 01, 2026", description: "Elevare Workforce OS", subtext: "August 2026 - 248 active employees", amount: 4182.0, status: "paid" },
        { id: "3", date: "Jul 01, 2026", description: "Elevare Workforce OS", subtext: "July 2026 - 241 active employees", amount: 4097.0, status: "paid" },
        { id: "4", date: "Jun 01, 2026", description: "Elevare Workforce OS", subtext: "June 2026 - 236 active employees", amount: 4046.0, status: "paid" },
      ]);
      setAiUsage([
        { id: "1", date: "Sep 20, 2026", feature: "Shift Planning Copilot", subtext: "Schedule optimization - West region", tokens: 184320, estimatedCost: 3.69 },
        { id: "2", date: "Sep 18, 2026", feature: "Policy Assistant", subtext: "Handbook Q&A - 42 queries", tokens: 96540, estimatedCost: 1.93 },
        { id: "3", date: "Sep 15, 2026", feature: "Performance Review Drafts", subtext: "Manager review summaries", tokens: 312880, estimatedCost: 6.26 },
        { id: "4", date: "Sep 11, 2026", feature: "Workforce Insights", subtext: "Absence trend analysis", tokens: 228190, estimatedCost: 4.56 },
        { id: "5", date: "Sep 06, 2026", feature: "Job Description Builder", subtext: "Operations roles - 18 drafts", tokens: 143700, estimatedCost: 2.87 },
      ]);
      setSummary({ estimatedCost: 19.31, tokensUsed: 965630, cycleEnds: "Sep 30, 2026", periodLabel: "Sep 1-30" });
      setLoading(false);
    }, 400);

    return function () {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <SidebarNav />

      <div className="flex-1 overflow-y-auto px-10 py-8">
        <p className="text-xs text-gray-500">Settings &gt; Billing &amp; AI Usage</p>
        <h1 className="mt-1 text-2xl font-bold">Billing &amp; AI Usage</h1>
        <p className="mt-2 flex items-center gap-2 text-sm text-gray-400">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="11" width="18" height="10" rx="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          Read-only account information. Billing and payments are managed externally by your Elevare account team.
        </p>

        {error ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        <div className="mt-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold">Billing History</h2>
              <p className="text-sm text-gray-500">A record of recent organization billing activity.</p>
            </div>
            <span className="text-xs text-gray-600">ACCOUNT - ELV-10482</span>
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Description</th>
                  <th className="px-5 py-3 text-right font-medium">Amount</th>
                  <th className="px-5 py-3 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 4 }).map(function (_, i) {
                      return (
                        <tr key={i} className="border-b border-white/5">
                          <td className="px-5 py-4" colSpan={4}>
                            <div className="h-4 w-full animate-pulse rounded bg-white/5" />
                          </td>
                        </tr>
                      );
                    })
                  : billing.map(function (row) {
                      return (
                        <tr key={row.id} className="border-b border-white/5 transition hover:bg-white/5">
                          <td className="px-5 py-4 text-gray-400">{row.date}</td>
                          <td className="px-5 py-4">
                            <p className="font-medium">{row.description}</p>
                            <p className="text-xs text-gray-500">{row.subtext}</p>
                          </td>
                          <td className="px-5 py-4 text-right font-semibold">{formatCurrency(row.amount)}</td>
                          <td className="px-5 py-4 text-right">
                            <StatusBadge status={row.status} />
                          </td>
                        </tr>
                      );
                    })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-10">
          <h2 className="text-base font-semibold">AI Usage</h2>
          <p className="text-sm text-gray-500">Estimated usage across AI-assisted workforce modules for the current billing cycle.</p>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-indigo-500/30 bg-indigo-500/5 p-5">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-300">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2l1.9 5.8L20 9.5l-5.8 1.9L12 17l-1.9-5.8L4 9.5l5.8-1.9L12 2z" />
                </svg>
              </span>
              <div>
                <p className="text-xs uppercase tracking-wide text-indigo-300">
                  Estimated Cost - {summary ? summary.periodLabel : "..."}
                </p>
                <p className="text-2xl font-bold">
                  {loading ? (
                    <span className="inline-block h-7 w-20 animate-pulse rounded bg-white/10" />
                  ) : (
                    formatCurrency(summary ? summary.estimatedCost : 0)
                  )}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-8 text-sm">
              <div>
                <p className="text-xs text-gray-500">Tokens Used</p>
                <p className="font-semibold">{loading ? "..." : summary ? summary.tokensUsed.toLocaleString() : ""}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Cycle Ends</p>
                <p className="font-semibold">{loading ? "..." : summary ? summary.cycleEnds : ""}</p>
              </div>
              <span className="rounded-full border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300">
                Estimate only
              </span>
            </div>
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Feature / Module Used</th>
                  <th className="px-5 py-3 text-right font-medium">Token Count</th>
                  <th className="px-5 py-3 text-right font-medium">Estimated Cost</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map(function (_, i) {
                    return (
                      <tr key={i} className="border-b border-white/5">
                        <td className="px-5 py-4" colSpan={4}>
                          <div className="h-4 w-full animate-pulse rounded bg-white/5" />
                        </td>
                      </tr>
                    );
                  })
                ) : aiUsage.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-5 py-10 text-center text-gray-500">
                      No AI usage recorded for this billing cycle yet.
                    </td>
                  </tr>
                ) : (
                  aiUsage.map(function (row) {
                    return (
                      <tr key={row.id} className="border-b border-white/5 transition hover:bg-white/5">
                        <td className="px-5 py-4 text-gray-400">{row.date}</td>
                        <td className="px-5 py-4">
                          <p className="font-medium">{row.feature}</p>
                          <p className="text-xs text-gray-500">{row.subtext}</p>
                        </td>
                        <td className="px-5 py-4 text-right text-gray-300">{row.tokens.toLocaleString()}</td>
                        <td className="px-5 py-4 text-right font-semibold">{formatCurrency(row.estimatedCost)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

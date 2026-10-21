"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import AppShell from "@/components/AppShell";

interface MeResponse {
  user: { id: string; full_name: string };
  memberships: { role: string; deactivated_at: string | null }[];
}

interface BillingRecord {
  id: string;
  description: string;
  amount: string | number;
  currency: string;
  paid_at: string;
  provider: string | null;
  provider_reference: string | null;
}

interface AiUsageRow {
  id: string;
  purpose: string;
  model: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cache_write_tokens: number;
  cache_read_tokens: number;
  estimated_cost_usd: string | number | null;
  created_at: string;
}

interface Pagination {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

interface Paged<T> {
  data: T[];
  pagination: Pagination;
}

interface BillingResult {
  key: string;
  records: BillingRecord[];
  // The billing endpoint may not be live yet; that is shown as a plain notice, not an error.
  unavailable: boolean;
  error: string;
}

interface UsageResult {
  key: string;
  rows: AiUsageRow[];
  totalPages: number;
  total: number;
  error: string;
}

interface SummaryResult {
  key: string;
  cost: number;
  tokens: number;
  calls: number;
  error: string;
}

const PAGE_SIZE = 20;
const billingKey = "billing";
const summaryKey = "summary";

function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function formatMoney(value: string | number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  const n = toNumber(value);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
  } catch {
    return currency + " " + n.toFixed(2);
  }
}

// AI costs are tiny amounts, so show up to 4 decimals instead of rounding to 0.00.
function formatUsd(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return "$" + toNumber(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function providerLabel(provider: string | null): string {
  if (provider === "paystack") return "Paystack";
  if (provider === "flutterwave") return "Flutterwave";
  if (provider === "bank_transfer") return "Bank transfer";
  return "—";
}

function purposeLabel(purpose: string): string {
  if (purpose === "ai_suggestion_generation") return "AI Suggestions";
  if (purpose === "executive_summary_generation") return "Executive summary";
  return purpose;
}

function tokensOf(row: AiUsageRow): number {
  return (
    toNumber(row.prompt_tokens) + toNumber(row.completion_tokens) + toNumber(row.cache_write_tokens) + toNumber(row.cache_read_tokens)
  );
}

function monthStart(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1);
}

function messageOf(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  return fallback;
}

export default function BillingAiUsagePage() {
  const [userName, setUserName] = useState("");
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [meError, setMeError] = useState("");

  const [billingResult, setBillingResult] = useState<BillingResult | null>(null);
  const [usagePage, setUsagePage] = useState(1);
  const [usageResult, setUsageResult] = useState<UsageResult | null>(null);
  const [summaryResult, setSummaryResult] = useState<SummaryResult | null>(null);

  const usageKey = "usage|" + usagePage;
  const billingLoading = allowed !== true || billingResult === null || billingResult.key !== billingKey;
  const usageLoading = allowed !== true || usageResult === null || usageResult.key !== usageKey;
  const summaryLoading = allowed !== true || summaryResult === null || summaryResult.key !== summaryKey;

  // Billing and AI usage are for HR Administrators only.
  useEffect(function () {
    let cancelled = false;
    apiFetch<MeResponse>("/auth/me", { method: "GET" })
      .then(function (me) {
        if (cancelled) return;
        let role = "";
        for (const m of me.memberships) {
          if (!m.deactivated_at) {
            role = m.role;
            break;
          }
        }
        setUserName(me.user.full_name);
        setAllowed(role === "hr_administrator");
      })
      .catch(function (err) {
        if (cancelled) return;
        setMeError(messageOf(err, "Couldn't check your access. Check your connection and try again."));
      });
    return function () {
      cancelled = true;
    };
  }, []);

  useEffect(
    function () {
      if (allowed !== true) return;
      let cancelled = false;
      apiFetch<Paged<BillingRecord> | BillingRecord[]>("/billing/history?page=1&limit=100", { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          const records = Array.isArray(res) ? res : res.data;
          setBillingResult({ key: billingKey, records: records, unavailable: false, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          const notThere = err instanceof ApiError && err.status === 404;
          setBillingResult({
            key: billingKey,
            records: [],
            unavailable: notThere,
            error: notThere ? "" : messageOf(err, "Couldn't load billing history. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [allowed]
  );

  useEffect(
    function () {
      if (allowed !== true) return;
      let cancelled = false;
      apiFetch<Paged<AiUsageRow>>("/ai-usage?page=" + usagePage + "&limit=" + PAGE_SIZE, { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setUsageResult({
            key: usageKey,
            rows: res.data,
            totalPages: res.pagination.total_pages,
            total: res.pagination.total,
            error: "",
          });
        })
        .catch(function (err) {
          if (cancelled) return;
          setUsageResult({
            key: usageKey,
            rows: [],
            totalPages: 1,
            total: 0,
            error: messageOf(err, "Couldn't load AI usage. Check your connection and try again."),
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [allowed, usagePage, usageKey]
  );

  // This month's totals. The log is newest-first, so paging stops as soon as
  // a row from before this month appears.
  useEffect(
    function () {
      if (allowed !== true) return;
      let cancelled = false;
      const start = monthStart().getTime();

      async function sum(): Promise<SummaryResult> {
        let cost = 0;
        let tokens = 0;
        let calls = 0;
        let page = 1;
        let more = true;
        while (more && page <= 20) {
          const res = await apiFetch<Paged<AiUsageRow>>("/ai-usage?page=" + page + "&limit=100", { method: "GET" });
          for (const row of res.data) {
            if (new Date(row.created_at).getTime() < start) {
              more = false;
              break;
            }
            cost = cost + toNumber(row.estimated_cost_usd);
            tokens = tokens + tokensOf(row);
            calls = calls + 1;
          }
          if (!res.pagination.has_next) more = false;
          page = page + 1;
        }
        return { key: summaryKey, cost: cost, tokens: tokens, calls: calls, error: "" };
      }

      sum()
        .then(function (done) {
          if (cancelled) return;
          setSummaryResult(done);
        })
        .catch(function (err) {
          if (cancelled) return;
          setSummaryResult({ key: summaryKey, cost: 0, tokens: 0, calls: 0, error: messageOf(err, "Couldn't work out this month's total.") });
        });
      return function () {
        cancelled = true;
      };
    },
    [allowed]
  );

  const billingRecords = billingResult ? billingResult.records : [];
  const usageRows = usageResult ? usageResult.rows : [];
  const monthName = monthStart().toLocaleDateString(undefined, { month: "long", year: "numeric" });

  let body: ReactNode;
  if (meError) {
    body = <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{meError}</div>;
  } else if (allowed === null) {
    body = <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-500">Loading…</div>;
  } else if (allowed === false) {
    body = (
      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-400">
        Billing and AI usage can only be seen by HR Administrators.
      </div>
    );
  } else {
    body = (
      <>
        <p className="flex items-center gap-2 text-sm text-gray-400">
          Read-only. Invoices and payments are handled by Paystack or Flutterwave and your Elevare account team; nothing can be paid or changed here.
        </p>

        <section className="mt-8">
          <h2 className="text-base font-semibold">Billing history</h2>
          <p className="text-sm text-gray-500">Payments recorded for your organization.</p>

          <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-5 py-3 font-medium">Paid on</th>
                  <th className="px-5 py-3 font-medium">Description</th>
                  <th className="px-5 py-3 font-medium">Paid through</th>
                  <th className="px-5 py-3 font-medium">Reference</th>
                  <th className="px-5 py-3 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {billingLoading ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                      Loading…
                    </td>
                  </tr>
                ) : billingResult && billingResult.error ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-red-300">
                      {billingResult.error}
                    </td>
                  </tr>
                ) : billingResult && billingResult.unavailable ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                      Billing history isn&apos;t available yet. It will appear here once it is switched on for your account.
                    </td>
                  </tr>
                ) : billingRecords.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                      No payments have been recorded yet.
                    </td>
                  </tr>
                ) : (
                  billingRecords.map(function (r) {
                    return (
                      <tr key={r.id} className="border-b border-white/5 hover:bg-white/5">
                        <td className="px-5 py-4 text-gray-400">{formatDate(r.paid_at)}</td>
                        <td className="px-5 py-4 font-medium">{r.description}</td>
                        <td className="px-5 py-4 text-gray-300">{providerLabel(r.provider)}</td>
                        <td className="px-5 py-4 text-xs text-gray-500">{r.provider_reference || "—"}</td>
                        <td className="px-5 py-4 text-right font-semibold">{formatMoney(r.amount, r.currency)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-10">
          <h2 className="text-base font-semibold">AI usage</h2>
          <p className="text-sm text-gray-500">Each time Elevare asked the AI for something on your behalf. Costs are estimates.</p>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-indigo-500/30 bg-indigo-500/5 p-5">
            <div>
              <p className="text-xs uppercase tracking-wide text-indigo-300">Estimated cost · {monthName}</p>
              <p className="text-2xl font-bold">
                {summaryLoading ? "…" : summaryResult && summaryResult.error ? "—" : formatUsd(summaryResult ? summaryResult.cost : 0)}
              </p>
              {summaryResult && summaryResult.error && <p className="mt-1 text-xs text-red-300">{summaryResult.error}</p>}
            </div>
            <div className="flex items-center gap-8 text-sm">
              <div>
                <p className="text-xs text-gray-500">AI requests</p>
                <p className="font-semibold">{summaryLoading || !summaryResult ? "…" : summaryResult.calls.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Tokens used</p>
                <p className="font-semibold">{summaryLoading || !summaryResult ? "…" : summaryResult.tokens.toLocaleString()}</p>
              </div>
              <span className="rounded-full border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300">Estimate only</span>
            </div>
          </div>

          <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-[#0d1220]/80">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-5 py-3 font-medium">When</th>
                  <th className="px-5 py-3 font-medium">Used for</th>
                  <th className="px-5 py-3 font-medium">Model</th>
                  <th className="px-5 py-3 text-right font-medium">Tokens</th>
                  <th className="px-5 py-3 text-right font-medium">Estimated cost</th>
                </tr>
              </thead>
              <tbody>
                {usageLoading ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                      Loading…
                    </td>
                  </tr>
                ) : usageResult && usageResult.error ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-red-300">
                      {usageResult.error}
                    </td>
                  </tr>
                ) : usageRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                      No AI usage has been recorded yet.
                    </td>
                  </tr>
                ) : (
                  usageRows.map(function (row) {
                    return (
                      <tr key={row.id} className="border-b border-white/5 hover:bg-white/5">
                        <td className="px-5 py-4 text-gray-400">{formatDateTime(row.created_at)}</td>
                        <td className="px-5 py-4 font-medium">{purposeLabel(row.purpose)}</td>
                        <td className="px-5 py-4 text-xs text-gray-500">{row.model}</td>
                        <td className="px-5 py-4 text-right text-gray-300">{tokensOf(row).toLocaleString()}</td>
                        <td className="px-5 py-4 text-right font-semibold">{formatUsd(row.estimated_cost_usd)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {usageResult && usageResult.totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-gray-400">
              <span>
                Page {usagePage} of {usageResult.totalPages} · {usageResult.total} requests
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={usagePage <= 1}
                  onClick={function () {
                    setUsagePage(usagePage - 1);
                  }}
                  className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={usagePage >= usageResult.totalPages}
                  onClick={function () {
                    setUsagePage(usagePage + 1);
                  }}
                  className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </section>
      </>
    );
  }

  return (
    <AppShell
      activeLabel="Settings"
      title="Billing & AI Usage"
      breadcrumb="Dashboard > Settings > Billing & AI Usage"
      userName={userName || undefined}
      userRole={allowed ? "HR Administrator" : undefined}
      actions={
        <Link href="/settings" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5">
          Back to settings
        </Link>
      }
    >
      {body}
    </AppShell>
  );
}

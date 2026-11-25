"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { apiFetch, ApiError, pickActiveMembership } from "@/lib/api";
import AppShell from "@/components/AppShell";

interface MeResponse {
  user: { id: string; full_name: string };
  memberships: { role: string; deactivated_at: string | null; organization: { id: string } }[];
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

const billingKey = "billing";

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

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function providerLabel(provider: string | null): string {
  if (provider === "paystack") return "Paystack";
  if (provider === "flutterwave") return "Flutterwave";
  if (provider === "bank_transfer") return "Bank transfer";
  return "—";
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
  const billingLoading = allowed !== true || billingResult === null || billingResult.key !== billingKey;

  // Billing is for HR Administrators only. Usage is Elevare's own and is not shown here.
  useEffect(function () {
    let cancelled = false;
    apiFetch<MeResponse>("/auth/me", { method: "GET" })
      .then(function (me) {
        if (cancelled) return;
        const activeMembership = pickActiveMembership(me.memberships);
        const role = activeMembership ? activeMembership.role : "";
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

  const billingRecords = billingResult ? billingResult.records : [];

  let body: ReactNode;
  if (meError) {
    body = <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{meError}</div>;
  } else if (allowed === null) {
    body = <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-500">Loading…</div>;
  } else if (allowed === false) {
    body = (
      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center text-sm text-gray-400">
        Billing can only be seen by HR Administrators.
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
      </>
    );
  }

  return (
    <AppShell
      activeLabel="Settings"
      title="Billing"
      breadcrumb="Dashboard > Settings > Billing"
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
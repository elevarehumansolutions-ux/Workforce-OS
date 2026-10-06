"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

type SentStatus = "invited" | "added";

interface SentInvite {
  id: string;
  email: string;
  role: string;
  status: SentStatus;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

// Matches MembershipRole on the backend exactly — these are sent as-is in
// the request body, so the value must be the real enum string, not a label.
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

const ROLE_LABELS: Record<string, string> = ROLE_OPTIONS.reduce(function (acc, opt) {
  acc[opt.value] = opt.label;
  return acc;
}, {} as Record<string, string>);

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

interface InviteTeammateResponse {
  status: SentStatus;
  membership?: { id: string } | null;
  invite?: { id: string; email: string; role: string } | null;
}

export default function InviteTeamPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [sending, setSending] = useState(false);
  const [formError, setFormError] = useState("");
  const [sentInvites, setSentInvites] = useState<SentInvite[]>([]);

  async function addInvite() {
    if (!email.trim() || !role) {
      window.alert("Please fill in both email and role before adding.");
      return;
    }
    setFormError("");
    setSending(true);
    try {
      const result = await apiFetch<InviteTeammateResponse>("/memberships", {
        method: "POST",
        body: { email: email.trim(), role },
      });
      setSentInvites([
        ...sentInvites,
        { id: makeId(), email: email.trim(), role, status: result.status },
      ]);
      setEmail("");
      setRole("");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't send that invite.");
    } finally {
      setSending(false);
    }
  }

  function handleContinue() {
    router.push("/dashboard");
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="flex items-center justify-between border-b border-white/10 px-8 py-4 sm:px-12">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <circle cx="9" cy="8" r="3" />
              <path d="M2 20c0-3 3-5 7-5s7 2 7 5" />
              <circle cx="17" cy="8" r="2.5" />
              <path d="M22 20c0-2.5-2-4-4.5-4.5" />
            </svg>
          </div>
          <span className="text-base font-bold">Elevare</span>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {ONBOARDING_STEPS.map(function (step, i) {
            let circleClass = "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ";
            let labelClass = "text-sm ";
            let isCheck = false;

            if (i < 5) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else {
              circleClass += "bg-indigo-500 text-white";
              labelClass += "font-medium text-indigo-400";
            }

            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className={circleClass}>
                    {isCheck ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      i + 1
                    )}
                  </span>
                  <span className={labelClass}>{step}</span>
                </div>
                {i < ONBOARDING_STEPS.length - 1 && <span className="h-px w-6 bg-white/10" />}
              </div>
            );
          })}
        </div>

        <div className="text-sm text-gray-400">
          Need help? <a href="#" className="text-indigo-400 hover:text-indigo-300">Contact Support</a>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Invite your team</h1>
          <p className="mt-2 text-gray-400">Bring in the people who will help run your organization</p>
        </div>

        <div className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
          {formError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {formError}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-5">
            <div className="sm:col-span-3">
              <label className="mb-2 block text-sm font-medium text-gray-200">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                  setEmail(e.target.value);
                }}
                placeholder="e.g. ngozi@zenith.com"
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-2 block text-sm font-medium text-gray-200">Role</label>
              <select
                value={role}
                onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                  setRole(e.target.value);
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
              >
                <option value="">Select role</option>
                {ROLE_OPTIONS.map(function (opt) {
                  return (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <p className="text-xs text-gray-500">
            Department and reporting manager aren&apos;t part of a team invite — those get set when
            the person is added as an employee from the Employee Directory, after they&apos;ve joined.
          </p>

          <button
            type="button"
            onClick={addInvite}
            disabled={sending}
            className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {sending ? "Sending…" : "+ Add"}
          </button>

          <div className="border-t border-white/10 pt-6">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">{sentInvites.length} invites sent</h2>
              <span className="text-sm text-gray-500">Sent immediately — this is a running log</span>
            </div>

            <div className="mt-4 space-y-2">
              {sentInvites.map(function (invite: SentInvite) {
                return (
                  <div
                    key={invite.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-6 text-sm">
                      <span className="font-medium">{invite.email}</span>
                      <span className="text-gray-400">{ROLE_LABELS[invite.role] || invite.role}</span>
                    </div>
                    {invite.status === "invited" ? (
                      <span className="flex items-center gap-1.5 rounded-full bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                        Invite Pending
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        Added — already had an account
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/kpis");
              }}
              className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Go Back
            </button>
            <button
              type="button"
              onClick={handleContinue}
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              {sentInvites.length > 0 ? "Finish" : "Skip for now"}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, currentOrganizationId, getAccessToken, setAccessToken } from "@/lib/api";
import Logo from "@/components/Logo";

interface Organization {
  id: string;
  name: string | null;
  subscription_status: string;
}

interface Membership {
  id: string;
  role: string;
  is_owner: boolean;
  deactivated_at: string | null;
  organization: Organization;
}

interface MeResponse {
  user: { id: string; full_name: string; email: string };
  memberships: Membership[];
}

const ROLE_LABELS: Record<string, string> = {
  hr_administrator: "HR Administrator",
  manager: "Manager",
  business_executive: "Executive",
  employee: "Employee",
  system_administrator: "System Administrator",
};

function initials(name: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function OrganizationsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  // "Create a new company": the form is hidden until asked for.
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(function () {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    apiFetch<MeResponse>("/auth/me", { method: "GET" })
      .then(function (data) {
        setMe(data);
      })
      .catch(function (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't load your organizations. Please try again.");
      })
      .finally(function () {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSwitch(membership: Membership) {
    if (membership.organization.id === currentOrganizationId()) {
      router.push("/dashboard");
      return;
    }
    setSwitching(membership.organization.id);
    setError("");
    try {
      // The server issues a new access token for the chosen company (POST /auth/switch-organization).
      const data = await apiFetch<{ access_token: string }>("/auth/switch-organization", {
        method: "POST",
        body: { organization_id: membership.organization.id },
      });
      setAccessToken(data.access_token);
      if (typeof window !== "undefined") {
        // A full page load, so the menu and every cached role start fresh for the new company.
        window.location.assign("/dashboard");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't switch company. Please try again.");
      setSwitching(null);
    }
  }

  // Matches the server's limit (MAX_OWNED_COMPANIES): companies this person started, not ones they joined.
  const MAX_OWNED = 3;
  const ownedCount = me
    ? me.memberships.filter(function (m) { return m.is_owner && !m.deactivated_at; }).length
    : 0;

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return; // a double click must not send two
    setCreateError("");
    if (newName.trim().length < 2) {
      setCreateError("Give the company a name of at least 2 characters.");
      return;
    }
    setSaving(true);
    try {
      // The answer is a session for the NEW company (POST /auth/create-organization).
      const data = await apiFetch<{ access_token: string }>("/auth/create-organization", {
        method: "POST",
        body: { name: newName.trim() },
      });
      setAccessToken(data.access_token);
      // A full page load into its onboarding, so every cached role and menu starts fresh.
      window.location.assign("/onboarding/business-dna");
    } catch (err) {
      // 409: you already have one with that name, or you own the most allowed. The message says which.
      setCreateError(err instanceof ApiError ? err.message : "Couldn't create the company. Please try again.");
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="mb-8 flex items-center gap-3">
          <Logo size={44} textClassName="text-lg font-bold" />
        </div>

        <h1 className="text-2xl font-bold">Your companies</h1>
        <p className="mt-1 text-sm text-gray-400">
          {me ? me.user.full_name + "'s workspaces" : "Choose which workspace you want to work in."}
        </p>

        {error ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="mt-8 space-y-3">
            {[0, 1].map(function (i) {
              return <div key={i} className="h-20 animate-pulse rounded-xl border border-white/10 bg-white/5" />;
            })}
          </div>
        ) : null}

        {!loading && me && me.memberships.length === 0 ? (
          <div className="mt-8 rounded-xl border border-white/10 bg-[#0d1220] px-6 py-8 text-center text-sm text-gray-400">
            You don&apos;t belong to any organization yet.
          </div>
        ) : null}

        {!loading && me ? (
          <div className="mt-8 space-y-3">
            {me.memberships.map(function (membership) {
              const org = membership.organization;
              const isActive = org.id === currentOrganizationId();
              const isDeactivated = Boolean(membership.deactivated_at);
              return (
                <button
                  key={membership.id}
                  onClick={function () {
                    if (!isDeactivated) handleSwitch(membership);
                  }}
                  disabled={isDeactivated || switching === org.id}
                  className={
                    "flex w-full items-center justify-between rounded-xl border px-5 py-4 text-left transition " +
                    (isActive
                      ? "border-indigo-500/50 bg-indigo-500/10"
                      : "border-white/10 bg-[#0d1220] hover:border-white/20 hover:bg-white/5") +
                    (isDeactivated ? " cursor-not-allowed opacity-50" : "")
                  }
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-indigo-500/20 text-sm font-semibold text-indigo-300">
                      {initials(org.name)}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">{org.name || "Untitled organization"}</p>
                      <p className="text-xs text-gray-400">
                        {ROLE_LABELS[membership.role] || membership.role}
                        {membership.is_owner ? " · Owner" : ""}
                        {isDeactivated ? " · Access removed" : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {isActive ? (
                      <span className="rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-medium text-indigo-300">
                        Current
                      </span>
                    ) : null}
                    {switching === org.id ? (
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                        <path d="M7 4l6 6-6 6" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        ) : null}

        {!loading && me ? (
          <div className="mt-8 rounded-xl border border-white/10 bg-[#0d1220] px-5 py-4">
            {!creating ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">Start another company</p>
                  <p className="text-xs text-gray-400">
                    {ownedCount >= MAX_OWNED
                      ? "You own " + MAX_OWNED + " companies, the most one login can create."
                      : "You own " + ownedCount + " of " + MAX_OWNED + ". It gets its own people, plan and settings."}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={ownedCount >= MAX_OWNED}
                  onClick={function () { setCreating(true); }}
                  className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Create a new company
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="space-y-3">
                <label htmlFor="new-company" className="block text-sm font-medium text-gray-200">
                  Company name
                </label>
                <input
                  id="new-company"
                  type="text"
                  value={newName}
                  onChange={function (e) { setNewName(e.target.value); }}
                  placeholder="e.g. Zenith Foods Ltd"
                  autoFocus
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
                {createError ? <p className="text-xs text-red-300">{createError}</p> : null}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
                  >
                    {saving ? "Creating…" : "Create and open it"}
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={function () { setCreating(false); setCreateError(""); }}
                    className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 hover:border-white/30"
                  >
                    Cancel
                  </button>
                </div>
                <p className="text-xs text-gray-500">
                  You will set it up from the start: its business details, plan and people.
                </p>
              </form>
            )}
          </div>
        ) : null}

        <a
          href="/dashboard"
          className="mt-8 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          ← Back to dashboard
        </a>
      </div>
    </div>
  );
}
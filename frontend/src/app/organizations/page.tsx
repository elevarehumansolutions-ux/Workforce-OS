"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";

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

const ACTIVE_ORG_KEY = "elevare_active_org_id";

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
  const [activeOrgId, setActiveOrgId] = useState<string | null>(function () {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACTIVE_ORG_KEY);
  });
  const [switching, setSwitching] = useState<string | null>(null);

  useEffect(function () {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    apiFetch<MeResponse>("/me", { method: "GET" })
      .then(function (data) {
        setMe(data);
        if (typeof window !== "undefined" && !window.localStorage.getItem(ACTIVE_ORG_KEY) && data.memberships.length > 0) {
          window.localStorage.setItem(ACTIVE_ORG_KEY, data.memberships[0].organization.id);
          setActiveOrgId(data.memberships[0].organization.id);
        }
      })
      .catch(function (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't load your organizations. Please try again.");
      })
      .finally(function () {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSwitch(membership: Membership) {
    if (membership.organization.id === activeOrgId) {
      router.push("/dashboard");
      return;
    }
    setSwitching(membership.organization.id);
    // NOTE: 05_API_DESIGN.md doesn't yet define a "switch active org" endpoint —
    // org_id is currently baked into the JWT at /auth/login and never re-issued
    // mid-session. Until that endpoint exists, this records the chosen org
    // locally and sends the person through login again so a fresh token gets
    // issued for it. Flag this gap to Emmanuel; a real switch-org endpoint
    // (re-issuing access_token scoped to the new org_id) would let this skip
    // the login round-trip.
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_ORG_KEY, membership.organization.id);
    }
    router.push("/login?org=" + membership.organization.id);
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
              <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
            </svg>
          </div>
          <span className="text-lg font-bold">Elevare</span>
        </div>

        <h1 className="text-2xl font-bold">Switch organization</h1>
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
              const isActive = org.id === activeOrgId;
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

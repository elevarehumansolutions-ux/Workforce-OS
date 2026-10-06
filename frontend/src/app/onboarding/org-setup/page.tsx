"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

interface Department {
  id: string;
  name: string;
  is_critical: boolean;
}

interface Location {
  id: string;
  name: string;
  address: string | null;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

export default function OrgSetupPage() {
  const router = useRouter();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyDeptId, setBusyDeptId] = useState<string | null>(null);
  const [busyLocId, setBusyLocId] = useState<string | null>(null);
  const [addingDept, setAddingDept] = useState(false);
  const [addingLoc, setAddingLoc] = useState(false);

  useEffect(function () {
    let cancelled = false;
    async function load() {
      try {
        const [deptRes, locRes] = await Promise.all([
          apiFetch<PaginatedResponse<Department>>("/departments?limit=100", { method: "GET" }),
          apiFetch<PaginatedResponse<Location>>("/locations?limit=100", { method: "GET" }),
        ]);
        if (cancelled) return;
        setDepartments(deptRes.data);
        setLocations(locRes.data);
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load your organization's departments and locations."
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return function () {
      cancelled = true;
    };
  }, []);

  async function toggleCritical(dept: Department) {
    setActionError("");
    setBusyDeptId(dept.id);
    try {
      const updated = await apiFetch<Department>("/departments/" + dept.id, {
        method: "PATCH",
        body: { is_critical: !dept.is_critical },
      });
      setDepartments(departments.map((d) => (d.id === dept.id ? updated : d)));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update that department.");
    } finally {
      setBusyDeptId(null);
    }
  }

  async function removeDepartment(id: string) {
    setActionError("");
    setBusyDeptId(id);
    try {
      await apiFetch("/departments/" + id, { method: "DELETE" });
      setDepartments(departments.filter((d) => d.id !== id));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't remove that department.");
    } finally {
      setBusyDeptId(null);
    }
  }

  async function addDepartment() {
    const name = window.prompt("Department name:");
    if (!name || !name.trim()) return;
    setActionError("");
    setAddingDept(true);
    try {
      const created = await apiFetch<Department>("/departments", {
        method: "POST",
        body: { name: name.trim(), is_critical: false },
      });
      setDepartments([...departments, created]);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add that department.");
    } finally {
      setAddingDept(false);
    }
  }

  async function removeLocation(id: string) {
    setActionError("");
    setBusyLocId(id);
    try {
      await apiFetch("/locations/" + id, { method: "DELETE" });
      setLocations(locations.filter((l) => l.id !== id));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't remove that location.");
    } finally {
      setBusyLocId(null);
    }
  }

  async function addLocation() {
    const name = window.prompt("Location name (e.g. Head Office):");
    if (!name || !name.trim()) return;
    const address = window.prompt("Address (e.g. City, Country) — optional:") || undefined;
    setActionError("");
    setAddingLoc(true);
    try {
      const created = await apiFetch<Location>("/locations", {
        method: "POST",
        body: { name: name.trim(), address: address ? address.trim() : null },
      });
      setLocations([...locations, created]);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add that location.");
    } finally {
      setAddingLoc(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // Departments and locations are already persisted the moment they're
    // added or edited above (each change hits the real API immediately),
    // so there's nothing left to batch-save here — this just advances the
    // wizard. Positions & the reporting-hierarchy editor are deliberately
    // not built yet: backend validation for them isn't ready.
    router.push("/onboarding/okrs");
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      {/* Top nav */}
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
          {ONBOARDING_STEPS.map((step, i) => {
            const status = i < 1 ? "done" : i === 1 ? "active" : "upcoming";
            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                      status === "active"
                        ? "bg-indigo-500 text-white"
                        : status === "done"
                        ? "border border-indigo-500 text-indigo-400"
                        : "border border-white/20 text-gray-400"
                    }`}
                  >
                    {status === "done" ? "✓" : i + 1}
                  </span>
                  <span
                    className={`text-sm ${
                      status === "active" ? "font-medium text-indigo-400" : "text-gray-500"
                    }`}
                  >
                    {step}
                  </span>
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

      {/* Main content */}
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Set up your organization</h1>
          <p className="mt-2 text-gray-400">
            Design corporate compartments and regional bases. Reporting hierarchy comes later.
          </p>
        </div>

        {loadError ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {loadError}
          </div>
        ) : null}
        {actionError ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {actionError}
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          {/* Departments + Locations */}
          <div className="grid grid-cols-1 gap-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm lg:grid-cols-2">
            {/* Departments */}
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Departments</h2>
                <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                  {departments.length} Total
                </span>
              </div>
              <p className="mt-1 text-sm text-gray-500">
                Mark departments that are revenue-critical or operationally critical
              </p>

              <div className="mt-4 space-y-3">
                {loading ? (
                  <div className="h-14 animate-pulse rounded-lg border border-white/10 bg-white/5" />
                ) : null}

                {!loading &&
                  departments.map((dept) => (
                    <div
                      key={dept.id}
                      className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                    >
                      <div>
                        <p className="text-sm font-medium">{dept.name}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => toggleCritical(dept)}
                          disabled={busyDeptId === dept.id}
                          className={`relative h-6 w-11 rounded-full transition disabled:opacity-50 ${
                            dept.is_critical ? "bg-indigo-500" : "bg-white/10"
                          }`}
                          aria-label="Toggle critical"
                        >
                          <span
                            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
                              dept.is_critical ? "left-5" : "left-0.5"
                            }`}
                          />
                        </button>
                        {dept.is_critical && (
                          <span className="rounded bg-red-500/15 px-2 py-1 text-xs font-medium text-red-400">
                            Critical
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => removeDepartment(dept.id)}
                          disabled={busyDeptId === dept.id}
                          className="text-gray-500 hover:text-red-400 disabled:opacity-50"
                          aria-label="Remove department"
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </div>
                  ))}

                <button
                  type="button"
                  onClick={addDepartment}
                  disabled={addingDept}
                  className="w-full rounded-lg border border-dashed border-indigo-500/40 py-3 text-sm font-medium text-indigo-400 hover:border-indigo-500/70 disabled:opacity-50"
                >
                  {addingDept ? "Adding…" : "+ Add Department"}
                </button>
              </div>
            </div>

            {/* Locations */}
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Locations</h2>
                <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                  {locations.length} Bases
                </span>
              </div>

              <div className="mt-4 space-y-3">
                {loading ? (
                  <div className="h-14 animate-pulse rounded-lg border border-white/10 bg-white/5" />
                ) : null}

                {!loading &&
                  locations.map((loc) => (
                    <div
                      key={loc.id}
                      className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                    >
                      <div>
                        <p className="text-sm font-medium">{loc.name}</p>
                        {loc.address ? <p className="text-xs text-gray-500">{loc.address}</p> : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => removeLocation(loc.id)}
                        disabled={busyLocId === loc.id}
                        className="text-gray-500 hover:text-red-400 disabled:opacity-50"
                        aria-label="Remove location"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  ))}

                <button
                  type="button"
                  onClick={addLocation}
                  disabled={addingLoc}
                  className="w-full rounded-lg border border-dashed border-indigo-500/40 py-3 text-sm font-medium text-indigo-400 hover:border-indigo-500/70 disabled:opacity-50"
                >
                  {addingLoc ? "Adding…" : "+ Add Location"}
                </button>
              </div>
            </div>
          </div>

          {/* Reporting Hierarchy — intentionally not built yet */}
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Positions & Reporting Hierarchy</h2>
              <span className="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-300">
                Coming soon
              </span>
            </div>
            <p className="mt-3 text-sm text-gray-500">
              Setting up positions and who-reports-to-whom will open here once the backend&apos;s
              validation for it is ready. You can skip this for now and come back to it later.
            </p>
          </div>

          {/* Footer nav */}
          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/business-dna");
              }}
              className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Go Back
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
    </svg>
  );
}


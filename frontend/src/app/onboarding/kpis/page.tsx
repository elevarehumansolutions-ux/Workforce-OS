"use client";

import React, { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

interface Department {
  id: string;
  name: string;
}

interface KpiApiResponse {
  id: string;
  department_id: string;
  name: string;
  description: string | null;
  weight: string | number;
  is_inverse: boolean;
  target_value: string | number | null;
  unit: string | null;
}

interface KpiGroupUpdateResponse {
  kpis: KpiApiResponse[];
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

interface KpiRow {
  localId: string;
  id: string | null;
  name: string;
  weight: string;
  targetValue: string;
  unit: string;
  isInverse: boolean;
}

interface DepartmentGroup {
  department: Department;
  kpis: KpiRow[];
  saving: boolean;
  error: string;
  saved: boolean;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

function makeLocalId() {
  return Math.random().toString(36).slice(2, 10);
}

function toKpiRow(kpi: KpiApiResponse): KpiRow {
  return {
    localId: kpi.id,
    id: kpi.id,
    name: kpi.name,
    weight: String(kpi.weight),
    targetValue: kpi.target_value === null || kpi.target_value === undefined ? "" : String(kpi.target_value),
    unit: kpi.unit || "",
    isInverse: kpi.is_inverse,
  };
}

function weightSum(rows: KpiRow[]): number {
  return rows.reduce(function (total, row) {
    const n = Number(row.weight);
    return total + (Number.isFinite(n) ? n : 0);
  }, 0);
}

export default function KpisPage() {
  const router = useRouter();
  const [groups, setGroups] = useState<DepartmentGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(function () {
    let cancelled = false;
    async function load() {
      try {
        const deptRes = await apiFetch<PaginatedResponse<Department>>("/departments?limit=100", {
          method: "GET",
        });
        if (cancelled) return;

        const loadedGroups = await Promise.all(
          deptRes.data.map(async function (department) {
            let kpiRows: KpiRow[] = [];
            try {
              const kpiRes = await apiFetch<PaginatedResponse<KpiApiResponse>>(
                "/kpis?department_id=" + department.id + "&limit=100",
                { method: "GET" }
              );
              kpiRows = kpiRes.data.map(toKpiRow);
            } catch {
              // If one department's KPIs fail to load, show it empty rather
              // than blocking the rest of the page.
            }
            return { department, kpis: kpiRows, saving: false, error: "", saved: true };
          })
        );
        if (cancelled) return;
        setGroups(loadedGroups);
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load your organization's departments."
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

  function updateGroup(deptId: string, updater: (g: DepartmentGroup) => DepartmentGroup) {
    setGroups(
      groups.map(function (g) {
        return g.department.id === deptId ? updater(g) : g;
      })
    );
  }

  function addKpiRow(deptId: string) {
    updateGroup(deptId, function (g) {
      return {
        ...g,
        saved: false,
        kpis: [
          ...g.kpis,
          { localId: makeLocalId(), id: null, name: "", weight: "0", targetValue: "", unit: "", isInverse: false },
        ],
      };
    });
  }

  function removeKpiRow(deptId: string, localId: string) {
    updateGroup(deptId, function (g) {
      return {
        ...g,
        saved: false,
        kpis: g.kpis.filter(function (row) {
          return row.localId !== localId;
        }),
      };
    });
  }

  function updateKpiRow(deptId: string, localId: string, patch: Partial<KpiRow>) {
    updateGroup(deptId, function (g) {
      return {
        ...g,
        saved: false,
        kpis: g.kpis.map(function (row) {
          return row.localId === localId ? { ...row, ...patch } : row;
        }),
      };
    });
  }

  async function saveGroup(deptId: string) {
    const group = groups.find(function (g) {
      return g.department.id === deptId;
    });
    if (!group) return;

    const total = weightSum(group.kpis);
    if (group.kpis.length > 0 && Math.round(total * 100) / 100 !== 100) {
      updateGroup(deptId, function (g) {
        return { ...g, error: "Weights must add up to exactly 100 (currently " + total + ")." };
      });
      return;
    }

    updateGroup(deptId, function (g) {
      return { ...g, saving: true, error: "" };
    });

    try {
      const payload = {
        kpis: group.kpis.map(function (row) {
          return {
            id: row.id || undefined,
            name: row.name.trim(),
            weight: Number(row.weight),
            is_inverse: row.isInverse,
            target_value: row.targetValue ? Number(row.targetValue) : null,
            unit: row.unit.trim() || null,
          };
        }),
      };
      const result = await apiFetch<KpiGroupUpdateResponse>("/departments/" + deptId + "/kpis", {
        method: "PUT",
        body: payload,
      });
      updateGroup(deptId, function (g) {
        return { ...g, saving: false, saved: true, kpis: result.kpis.map(toKpiRow) };
      });
    } catch (err) {
      updateGroup(deptId, function (g) {
        return {
          ...g,
          saving: false,
          error: err instanceof ApiError ? err.message : "Couldn't save this department's KPIs.",
        };
      });
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // Each department's KPIs save via its own "Save" button above (the
    // backend reconciles a whole department's list in one call, so there's
    // no single combined submit) — this just advances the wizard.
    router.push("/onboarding/invite-team");
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

            if (i < 4) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else if (i === 4) {
              circleClass += "bg-indigo-500 text-white";
              labelClass += "font-medium text-indigo-400";
            } else {
              circleClass += "border border-white/20 text-gray-400";
              labelClass += "text-gray-500";
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

      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Assign departmental KPIs</h1>
          <p className="mt-2 text-gray-400">
            Each department&apos;s KPI weights must add up to exactly 100. Save a department once its
            weights balance.
          </p>
        </div>

        {loadError ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {loadError}
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          {loading ? (
            <div className="h-24 animate-pulse rounded-2xl border border-white/10 bg-white/5" />
          ) : null}

          {!loading && groups.length === 0 ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-center text-sm text-gray-400 shadow-2xl backdrop-blur-sm">
              No departments yet — add some on the Organization step first.
            </div>
          ) : null}

          {!loading &&
            groups.map(function (group) {
              const total = weightSum(group.kpis);
              const totalOk = group.kpis.length === 0 || Math.round(total * 100) / 100 === 100;
              return (
                <div
                  key={group.department.id}
                  className="space-y-4 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-semibold">{group.department.name}</h2>
                    <span
                      className={
                        "rounded-full px-3 py-1 text-xs font-medium " +
                        (totalOk ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400")
                      }
                    >
                      Total weight: {total}
                      {totalOk ? "" : " (must be 100)"}
                    </span>
                  </div>

                  {group.error ? (
                    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-300">
                      {group.error}
                    </div>
                  ) : null}

                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                          <th className="pb-3 pr-4 font-medium">KPI Name</th>
                          <th className="pb-3 pr-4 font-medium">Weight %</th>
                          <th className="pb-3 pr-4 font-medium">Target</th>
                          <th className="pb-3 pr-4 font-medium">Unit</th>
                          <th className="pb-3 pr-4 font-medium">Inverse</th>
                          <th className="pb-3 font-medium" />
                        </tr>
                      </thead>
                      <tbody>
                        {group.kpis.map(function (row) {
                          return (
                            <tr key={row.localId} className="border-b border-white/5">
                              <td className="py-2 pr-4">
                                <input
                                  type="text"
                                  value={row.name}
                                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                    updateKpiRow(group.department.id, row.localId, { name: e.target.value });
                                  }}
                                  placeholder="e.g. Sprint Velocity"
                                  className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                                />
                              </td>
                              <td className="py-2 pr-4">
                                <input
                                  type="number"
                                  value={row.weight}
                                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                    updateKpiRow(group.department.id, row.localId, { weight: e.target.value });
                                  }}
                                  className="w-20 rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
                                />
                              </td>
                              <td className="py-2 pr-4">
                                <input
                                  type="number"
                                  value={row.targetValue}
                                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                    updateKpiRow(group.department.id, row.localId, { targetValue: e.target.value });
                                  }}
                                  placeholder="optional"
                                  className="w-24 rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                                />
                              </td>
                              <td className="py-2 pr-4">
                                <input
                                  type="text"
                                  value={row.unit}
                                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                    updateKpiRow(group.department.id, row.localId, { unit: e.target.value });
                                  }}
                                  placeholder="e.g. hrs"
                                  className="w-20 rounded-lg border border-white/10 bg-[#111726] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                                />
                              </td>
                              <td className="py-2 pr-4 text-center">
                                <input
                                  type="checkbox"
                                  checked={row.isInverse}
                                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                                    updateKpiRow(group.department.id, row.localId, { isInverse: e.target.checked });
                                  }}
                                  title="Check if lower is better (e.g. bug count)"
                                />
                              </td>
                              <td className="py-2">
                                <button
                                  type="button"
                                  onClick={function () {
                                    removeKpiRow(group.department.id, row.localId);
                                  }}
                                  className="text-gray-500 hover:text-red-400"
                                  aria-label="Remove KPI"
                                >
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M18 6 6 18M6 6l12 12" />
                                  </svg>
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <button
                      type="button"
                      onClick={function () {
                        addKpiRow(group.department.id);
                      }}
                      className="rounded-full border border-dashed border-indigo-500/40 px-4 py-1.5 text-xs font-medium text-indigo-400 hover:border-indigo-500/70"
                    >
                      + Add KPI
                    </button>
                    <button
                      type="button"
                      onClick={function () {
                        saveGroup(group.department.id);
                      }}
                      disabled={group.saving}
                      className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {group.saving ? "Saving…" : group.saved ? "Saved" : "Save this department's KPIs"}
                    </button>
                  </div>
                </div>
              );
            })}

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/ai-suggestions");
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


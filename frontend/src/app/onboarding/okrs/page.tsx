"use client";

import React, { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

interface KeyResult {
  id: string;
  description: string;
  savedDescription: string;
}

interface Objective {
  id: string;
  title: string;
  savedTitle: string;
  departmentId: string | null;
  keyResults: KeyResult[];
}

interface Department {
  id: string;
  name: string;
}

interface OkrApiResponse {
  id: string;
  title: string;
  department_id: string | null;
}

interface KeyResultApiResponse {
  id: string;
  description: string;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

export default function OkrsPage() {
  const router = useRouter();
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [addingObjective, setAddingObjective] = useState(false);
  const [addingKeyResultFor, setAddingKeyResultFor] = useState<string | null>(null);

  useEffect(function () {
    let cancelled = false;
    async function load() {
      try {
        const [deptRes, okrRes] = await Promise.all([
          apiFetch<PaginatedResponse<Department>>("/departments?limit=100", { method: "GET" }),
          apiFetch<PaginatedResponse<OkrApiResponse>>("/okrs?limit=100", { method: "GET" }),
        ]);
        if (cancelled) return;
        setDepartments(deptRes.data);

        const okrsWithKeyResults = await Promise.all(
          okrRes.data.map(async function (okr) {
            let keyResults: KeyResultApiResponse[] = [];
            try {
              const krRes = await apiFetch<PaginatedResponse<KeyResultApiResponse>>(
                "/okrs/" + okr.id + "/key-results?limit=100",
                { method: "GET" }
              );
              keyResults = krRes.data;
            } catch {
              // If a single OKR's key results fail to load, don't block the
              // rest of the page — it just shows that one with none yet.
            }
            return {
              id: okr.id,
              title: okr.title,
              savedTitle: okr.title,
              departmentId: okr.department_id,
              keyResults: keyResults.map(function (kr) {
                return { id: kr.id, description: kr.description, savedDescription: kr.description };
              }),
            };
          })
        );
        if (cancelled) return;
        setObjectives(okrsWithKeyResults);
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load your organization's objectives."
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

  async function addObjective() {
    const title = window.prompt("Objective title:");
    if (!title || !title.trim()) return;
    setActionError("");
    setAddingObjective(true);
    try {
      const created = await apiFetch<OkrApiResponse>("/okrs", {
        method: "POST",
        body: { title: title.trim(), department_id: null },
      });
      setObjectives([
        ...objectives,
        {
          id: created.id,
          title: created.title,
          savedTitle: created.title,
          departmentId: created.department_id,
          keyResults: [],
        },
      ]);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add that objective.");
    } finally {
      setAddingObjective(false);
    }
  }

  function setObjectiveTitleLocal(objId: string, newTitle: string) {
    setObjectives(
      objectives.map(function (obj) {
        return obj.id === objId ? { ...obj, title: newTitle } : obj;
      })
    );
  }

  async function saveObjectiveTitleIfChanged(obj: Objective) {
    if (obj.title === obj.savedTitle) return;
    if (!obj.title.trim()) {
      // Don't save a blank title — revert to what's on the server.
      setObjectiveTitleLocal(obj.id, obj.savedTitle);
      return;
    }
    setActionError("");
    try {
      const updated = await apiFetch<OkrApiResponse>("/okrs/" + obj.id, {
        method: "PATCH",
        body: { title: obj.title },
      });
      setObjectives(function (prev) {
        return prev.map(function (o) {
          return o.id === obj.id ? { ...o, title: updated.title, savedTitle: updated.title } : o;
        });
      });
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save that objective's title.");
      setObjectiveTitleLocal(obj.id, obj.savedTitle);
    }
  }

  async function updateObjectiveDepartment(obj: Objective, newDepartmentId: string) {
    const departmentId = newDepartmentId || null;
    setActionError("");
    try {
      const updated = await apiFetch<OkrApiResponse>("/okrs/" + obj.id, {
        method: "PATCH",
        body: { department_id: departmentId },
      });
      setObjectives(
        objectives.map(function (o) {
          return o.id === obj.id ? { ...o, departmentId: updated.department_id } : o;
        })
      );
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update that objective's scope.");
    }
  }

  async function addKeyResult(objId: string) {
    const description = window.prompt("Key result:");
    if (!description || !description.trim()) return;
    setActionError("");
    setAddingKeyResultFor(objId);
    try {
      const created = await apiFetch<KeyResultApiResponse>("/okrs/" + objId + "/key-results", {
        method: "POST",
        body: { description: description.trim() },
      });
      setObjectives(
        objectives.map(function (obj) {
          if (obj.id !== objId) return obj;
          return {
            ...obj,
            keyResults: [
              ...obj.keyResults,
              { id: created.id, description: created.description, savedDescription: created.description },
            ],
          };
        })
      );
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add that key result.");
    } finally {
      setAddingKeyResultFor(null);
    }
  }

  function setKeyResultTextLocal(objId: string, krId: string, newText: string) {
    setObjectives(
      objectives.map(function (obj) {
        if (obj.id !== objId) return obj;
        return {
          ...obj,
          keyResults: obj.keyResults.map(function (kr) {
            return kr.id === krId ? { ...kr, description: newText } : kr;
          }),
        };
      })
    );
  }

  async function saveKeyResultIfChanged(objId: string, kr: KeyResult) {
    if (kr.description === kr.savedDescription) return;
    if (!kr.description.trim()) {
      setKeyResultTextLocal(objId, kr.id, kr.savedDescription);
      return;
    }
    setActionError("");
    try {
      const updated = await apiFetch<KeyResultApiResponse>("/key-results/" + kr.id, {
        method: "PATCH",
        body: { description: kr.description },
      });
      setObjectives(function (prev) {
        return prev.map(function (obj) {
          if (obj.id !== objId) return obj;
          return {
            ...obj,
            keyResults: obj.keyResults.map(function (k) {
              return k.id === kr.id
                ? { ...k, description: updated.description, savedDescription: updated.description }
                : k;
            }),
          };
        });
      });
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't save that key result.");
      setKeyResultTextLocal(objId, kr.id, kr.savedDescription);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // Every objective and key result above is already saved the moment it's
    // added or edited (each hits the real API immediately), so there's
    // nothing left to batch-submit — this only advances the wizard. OKRs
    // are additive by design: nothing here ever clears or overwrites an
    // existing objective someone else already created this quarter.
    router.push("/onboarding/ai-suggestions");
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
            let content: string | number = i + 1;

            if (i < 2) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              content = "check";
            } else if (i === 2) {
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
                    {content === "check" ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      content
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

      <div className="mx-auto max-w-3xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Set your corporate objectives</h1>
          <p className="mt-2 text-gray-400">
            Define strategic objectives and measurable key results for your organization.
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

        <form
          onSubmit={handleSubmit}
          className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Corporate Objectives</h2>
            <span className="text-xs text-gray-500">Saved automatically as you type</span>
          </div>

          {loading ? (
            <div className="h-24 animate-pulse rounded-lg border border-white/10 bg-white/5" />
          ) : null}

          {!loading &&
            objectives.map(function (obj: Objective) {
              return (
                <div key={obj.id} className="space-y-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={obj.title}
                      onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                        setObjectiveTitleLocal(obj.id, e.target.value);
                      }}
                      onBlur={function () {
                        saveObjectiveTitleIfChanged(obj);
                      }}
                      placeholder="Objective title"
                      className="flex-1 rounded-lg border border-white/10 bg-[#111726] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                    />
                    <select
                      value={obj.departmentId || ""}
                      onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                        updateObjectiveDepartment(obj, e.target.value);
                      }}
                      className="rounded-lg border border-white/10 bg-[#111726] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
                    >
                      <option value="">Corporate</option>
                      {departments.map(function (dept) {
                        return (
                          <option key={dept.id} value={dept.id}>
                            {dept.name}
                          </option>
                        );
                      })}
                    </select>
                  </div>

                  <p className="text-xs uppercase tracking-wide text-gray-500">Key Results</p>

                  {obj.keyResults.map(function (kr: KeyResult) {
                    return (
                      <div key={kr.id} className="flex items-center gap-2 pl-4">
                        <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-500" />
                        <input
                          type="text"
                          value={kr.description}
                          onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                            setKeyResultTextLocal(obj.id, kr.id, e.target.value);
                          }}
                          onBlur={function () {
                            saveKeyResultIfChanged(obj.id, kr);
                          }}
                          placeholder="Key result"
                          className="flex-1 rounded-lg border border-white/10 bg-[#111726] px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                        />
                      </div>
                    );
                  })}

                  <button
                    type="button"
                    onClick={function () {
                      addKeyResult(obj.id);
                    }}
                    disabled={addingKeyResultFor === obj.id}
                    className="ml-4 rounded-full border border-indigo-500/40 px-4 py-1.5 text-xs font-medium text-indigo-400 hover:border-indigo-500/70 disabled:opacity-50"
                  >
                    {addingKeyResultFor === obj.id ? "Adding…" : "+ Add Key Result"}
                  </button>
                </div>
              );
            })}

          <button
            type="button"
            onClick={addObjective}
            disabled={addingObjective}
            className="rounded-full border border-indigo-500/40 px-4 py-1.5 text-sm font-medium text-indigo-400 hover:border-indigo-500/70 disabled:opacity-50"
          >
            {addingObjective ? "Adding…" : "+ Add Objective"}
          </button>

          <p className="text-xs text-gray-500">
            Removing an objective or key result isn&apos;t available yet — the backend doesn&apos;t
            support deleting them. Edit the wording instead if something needs to change.
          </p>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/org-setup");
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


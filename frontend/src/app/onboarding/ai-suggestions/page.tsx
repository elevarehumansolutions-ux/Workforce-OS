"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

type SuggestionType = "critical_position" | "revenue_allocation" | "missing_department" | "kpi_weight";
type Decision = "pending" | "approved" | "edited" | "rejected";

interface Suggestion {
  id: string;
  suggestion_type: SuggestionType;
  position_id: string | null;
  department_id: string | null;
  suggested_department_name: string | null;
  suggested_criticality_type: string | null;
  suggested_risk_level: string | null;
  suggested_revenue_allocation_percentage: string | number | null;
  kpi_id: string | null;
  suggested_weight: string | number | null;
  rationale: string;
  status: string;
}

interface Department {
  id: string;
  name: string;
}

interface Position {
  id: string;
  department_id: string;
  title: string;
}

interface Kpi {
  id: string;
  department_id: string;
  name: string;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: { has_next: boolean };
}

interface LoadedData {
  suggestions: Suggestion[];
  departments: Department[];
  positions: Position[];
  kpis: Kpi[];
}

interface EditValues {
  criticality: string;
  risk: string;
  percent: string;
  name: string;
  weight: string;
}

const ONBOARDING_STEPS = ["Business DNA", "Organization", "OKRs", "AI Suggestions", "KPIs", "Invite Team"];

// The exact values the backend accepts (CriticalityType / RiskLevel enums).
const CRITICALITY_OPTIONS: { value: string; label: string }[] = [
  { value: "revenue_generating", label: "Revenue generating" },
  { value: "revenue_enabling", label: "Revenue enabling" },
  { value: "operational", label: "Operational" },
  { value: "customer", label: "Customer" },
  { value: "compliance", label: "Compliance" },
  { value: "strategic", label: "Strategic" },
  { value: "financial", label: "Financial" },
  { value: "legal", label: "Legal" },
  { value: "reputational", label: "Reputational" },
];

const RISK_OPTIONS: { value: string; label: string }[] = [
  { value: "very_low", label: "Very low" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "very_high", label: "Very high" },
];

function labelFor(options: { value: string; label: string }[], value: string | null): string {
  if (!value) return "";
  for (const o of options) {
    if (o.value === value) return o.label;
  }
  return value;
}

function riskClasses(risk: string | null): string {
  if (risk === "high" || risk === "very_high") return "bg-red-500/15 text-red-400";
  if (risk === "medium") return "bg-amber-500/15 text-amber-400";
  return "bg-emerald-500/15 text-emerald-400";
}

function numberText(value: string | number | null): string {
  if (value === null || value === undefined) return "";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  // 22.00 -> "22", 12.5 -> "12.5"
  return String(Math.round(n * 100) / 100);
}

async function fetchAllPages<T>(path: string): Promise<T[]> {
  const all: T[] = [];
  const joiner = path.indexOf("?") === -1 ? "?" : "&";
  let page = 1;
  while (page <= 50) {
    const res = await apiFetch<PaginatedResponse<T>>(path + joiner + "page=" + page + "&limit=100", {
      method: "GET",
    });
    for (const item of res.data) {
      all.push(item);
    }
    if (!res.pagination.has_next) break;
    page = page + 1;
  }
  return all;
}

async function loadData(): Promise<LoadedData> {
  const results = await Promise.all([
    fetchAllPages<Suggestion>("/ai-suggestions?status=pending"),
    fetchAllPages<Department>("/departments"),
    fetchAllPages<Position>("/positions"),
  ]);
  const suggestions = results[0];
  const departments = results[1];
  const positions = results[2];

  // KPI names are only needed for KPI-weight suggestions, so only fetch them then.
  const kpis: Kpi[] = [];
  const needsKpis = suggestions.some(function (s) {
    return s.suggestion_type === "kpi_weight";
  });
  if (needsKpis) {
    const perDepartment = await Promise.all(
      departments.map(function (d) {
        return fetchAllPages<Kpi>("/kpis?department_id=" + d.id).catch(function () {
          return [] as Kpi[];
        });
      })
    );
    for (const list of perDepartment) {
      for (const k of list) {
        kpis.push(k);
      }
    }
  }
  return { suggestions: suggestions, departments: departments, positions: positions, kpis: kpis };
}

const EMPTY_EDIT: EditValues = { criticality: "", risk: "", percent: "", name: "", weight: "" };

export default function AiSuggestionsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Suggestion[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [departments, setDepartments] = useState<Department[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [kpis, setKpis] = useState<Kpi[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<EditValues>(EMPTY_EDIT);
  const [editError, setEditError] = useState("");

  function applyLoaded(data: LoadedData) {
    setItems(data.suggestions);
    setDepartments(data.departments);
    setPositions(data.positions);
    setKpis(data.kpis);
    setDecisions({});
    setEditingId(null);
  }

  useEffect(function () {
    let cancelled = false;
    loadData()
      .then(function (data) {
        if (cancelled) return;
        setItems(data.suggestions);
        setDepartments(data.departments);
        setPositions(data.positions);
        setKpis(data.kpis);
      })
      .catch(function (err) {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load your AI suggestions.");
      })
      .finally(function () {
        if (!cancelled) setLoading(false);
      });
    return function () {
      cancelled = true;
    };
  }, []);

  async function refresh() {
    setLoadError("");
    setActionError("");
    setNotice("");
    setLoading(true);
    try {
      const data = await loadData();
      applyLoaded(data);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Couldn't load your AI suggestions.");
    } finally {
      setLoading(false);
    }
  }

  function departmentName(id: string | null): string {
    for (const d of departments) {
      if (d.id === id) return d.name;
    }
    return "";
  }

  function positionOf(id: string | null): Position | null {
    for (const p of positions) {
      if (p.id === id) return p;
    }
    return null;
  }

  function kpiOf(id: string | null): Kpi | null {
    for (const k of kpis) {
      if (k.id === id) return k;
    }
    return null;
  }

  function titleFor(s: Suggestion): { title: string; where: string } {
    if (s.suggestion_type === "critical_position") {
      const p = positionOf(s.position_id);
      return {
        title: p ? p.title : "A position",
        where: p ? departmentName(p.department_id) : "",
      };
    }
    if (s.suggestion_type === "revenue_allocation") {
      return { title: "Revenue share", where: departmentName(s.department_id) };
    }
    if (s.suggestion_type === "missing_department") {
      return { title: "New department: " + (s.suggested_department_name || ""), where: "" };
    }
    const k = kpiOf(s.kpi_id);
    return { title: "KPI weight: " + (k ? k.name : "a KPI"), where: k ? departmentName(k.department_id) : "" };
  }

  function typeLabel(s: Suggestion): string {
    if (s.suggestion_type === "critical_position") return "Critical role";
    if (s.suggestion_type === "revenue_allocation") return "Revenue allocation";
    if (s.suggestion_type === "missing_department") return "Missing department";
    return "KPI weight";
  }

  function decisionOf(id: string): Decision {
    return decisions[id] || "pending";
  }

  function markDecision(id: string, d: Decision) {
    const next: Record<string, Decision> = { ...decisions };
    next[id] = d;
    setDecisions(next);
  }

  // An error that means "this suggestion is no longer reviewable" (already
  // handled by someone else, or the thing it pointed at changed): reload so
  // the page matches the server.
  async function afterFailure(err: unknown) {
    setActionError(err instanceof ApiError ? err.message : "Couldn't save that. Check your connection and try again.");
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      try {
        const data = await loadData();
        applyLoaded(data);
      } catch {
        // Keep what is on screen.
      }
    }
  }

  async function review(s: Suggestion, action: "approve" | "reject") {
    setActionError("");
    setNotice("");
    setBusyId(s.id);
    try {
      await apiFetch("/ai-suggestions/" + s.id + "/" + action, { method: "POST" });
      markDecision(s.id, action === "approve" ? "approved" : "rejected");
    } catch (err) {
      await afterFailure(err);
    } finally {
      setBusyId(null);
    }
  }

  function startEdit(s: Suggestion) {
    setActionError("");
    setNotice("");
    setEditError("");
    setEditingId(s.id);
    setEditValues({
      criticality: s.suggested_criticality_type || "",
      risk: s.suggested_risk_level || "",
      percent: numberText(s.suggested_revenue_allocation_percentage),
      name: s.suggested_department_name || "",
      weight: numberText(s.suggested_weight),
    });
  }

  async function saveEdit(s: Suggestion) {
    setEditError("");
    // Send only what actually changed — the server rejects an edit that
    // matches the AI's proposal, and leaves omitted fields alone.
    const body: Record<string, string | number> = {};
    if (s.suggestion_type === "critical_position") {
      if (editValues.criticality && editValues.criticality !== s.suggested_criticality_type) {
        body.criticality_type = editValues.criticality;
      }
      if (editValues.risk && editValues.risk !== s.suggested_risk_level) {
        body.risk_level = editValues.risk;
      }
    } else if (s.suggestion_type === "revenue_allocation") {
      const n = Number(editValues.percent);
      if (editValues.percent.trim() === "" || Number.isNaN(n) || n < 0) {
        setEditError("Enter a percentage of 0 or more.");
        return;
      }
      if (n !== Number(s.suggested_revenue_allocation_percentage)) {
        body.revenue_allocation_percentage = n;
      }
    } else if (s.suggestion_type === "missing_department") {
      const name = editValues.name.trim();
      if (!name) {
        setEditError("Enter a department name.");
        return;
      }
      if (name !== s.suggested_department_name) {
        body.department_name = name;
      }
    } else {
      const n = Number(editValues.weight);
      if (editValues.weight.trim() === "" || Number.isNaN(n) || n < 0 || n > 100) {
        setEditError("Enter a weight between 0 and 100.");
        return;
      }
      if (n !== Number(s.suggested_weight)) {
        body.weight = n;
      }
    }
    if (Object.keys(body).length === 0) {
      setEditError("Change a value first, or just use Approve to accept it as suggested.");
      return;
    }

    setActionError("");
    setBusyId(s.id);
    try {
      await apiFetch("/ai-suggestions/" + s.id + "/edit", { method: "POST", body: body });
      markDecision(s.id, "edited");
      setEditingId(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setEditError(err.message);
      } else {
        setEditError("Couldn't save that. Check your connection and try again.");
      }
      if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
        await afterFailure(err);
      }
    } finally {
      setBusyId(null);
    }
  }

  async function approveAll() {
    setActionError("");
    setNotice("");
    setBulkBusy(true);
    let approved = 0;
    let failed = 0;
    let firstMessage = "";
    const nextDecisions: Record<string, Decision> = { ...decisions };
    for (const s of items) {
      if ((nextDecisions[s.id] || "pending") !== "pending") continue;
      try {
        await apiFetch("/ai-suggestions/" + s.id + "/approve", { method: "POST" });
        nextDecisions[s.id] = "approved";
        approved = approved + 1;
      } catch (err) {
        failed = failed + 1;
        if (!firstMessage) {
          firstMessage = err instanceof ApiError ? err.message : "Couldn't reach the server.";
        }
      }
    }
    setDecisions(nextDecisions);
    if (approved > 0) {
      setNotice(approved + (approved === 1 ? " suggestion approved." : " suggestions approved."));
    }
    if (failed > 0) {
      setActionError(
        failed + (failed === 1 ? " suggestion" : " suggestions") + " couldn't be applied: " + firstMessage + " Review those one by one."
      );
    }
    setBulkBusy(false);
  }

  const pendingCount = items.filter(function (s) {
    return decisionOf(s.id) === "pending";
  }).length;

  const inputClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500";

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

            if (i < 3) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else if (i === 3) {
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

      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Review AI suggestions</h1>
          <p className="mt-2 text-gray-400">
            Our AI looks at your departments, roles and goals and suggests what to flag or adjust. Nothing changes
            until you approve it.
          </p>
        </div>

        <div className="mt-8 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                AI Engine Active
              </span>
              <span className="text-sm text-gray-300">
                {loading ? "Loading…" : pendingCount + (pendingCount === 1 ? " suggestion" : " suggestions") + " waiting for review"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={refresh}
                disabled={loading || bulkBusy}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Check for new
              </button>
              <button
                type="button"
                onClick={approveAll}
                disabled={loading || bulkBusy || pendingCount === 0}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {bulkBusy ? "Approving…" : "Approve All"}
              </button>
            </div>
          </div>

          {loadError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{loadError}</div>
          ) : null}
          {actionError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div>
          ) : null}
          {notice ? (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</div>
          ) : null}

          {!loading && !loadError && items.length === 0 ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-center shadow-xl">
              <p className="text-base font-semibold">No suggestions yet</p>
              <p className="mx-auto mt-2 max-w-md text-sm text-gray-400">
                Suggestions are prepared in the background after you set up your departments, roles and goals, so
                they can take a little while to appear. Press &quot;Check for new&quot; in a minute, or just continue.
              </p>
            </div>
          ) : null}

          <div className="space-y-4">
            {items.map(function (s) {
              const decision = decisionOf(s.id);
              const isDecided = decision !== "pending";
              const isBusy = busyId === s.id || bulkBusy;
              const isEditing = editingId === s.id;
              const heading = titleFor(s);
              return (
                <div
                  key={s.id}
                  className={
                    "rounded-2xl border p-5 shadow-xl backdrop-blur-sm " +
                    (isDecided ? "border-white/5 bg-[#0d1220]/40 opacity-60" : "border-white/10 bg-[#0d1220]/80")
                  }
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold">{heading.title}</h3>
                        {heading.where ? <span className="text-sm text-gray-500">• {heading.where}</span> : null}
                        <span className="rounded bg-white/10 px-2 py-0.5 text-xs font-medium text-gray-300">
                          AI SUGGESTED
                        </span>
                        {isDecided ? (
                          <span
                            className={
                              "rounded px-2 py-0.5 text-xs font-medium " +
                              (decision === "rejected" ? "bg-red-500/15 text-red-400" : "bg-emerald-500/15 text-emerald-400")
                            }
                          >
                            {decision === "approved" ? "APPROVED" : decision === "edited" ? "EDITED & APPLIED" : "REJECTED"}
                          </span>
                        ) : null}
                      </div>

                      <p className="mt-2 text-sm text-gray-400">
                        <span className="italic text-gray-500">AI Rationale:</span> {s.rationale}
                      </p>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className="rounded bg-white/10 px-2 py-1 text-xs font-medium text-gray-300">{typeLabel(s)}</span>
                        {s.suggestion_type === "critical_position" ? (
                          <>
                            <span className="rounded bg-cyan-500/15 px-2 py-1 text-xs font-medium text-cyan-300">
                              {labelFor(CRITICALITY_OPTIONS, s.suggested_criticality_type)}
                            </span>
                            <span className={"rounded px-2 py-1 text-xs font-medium " + riskClasses(s.suggested_risk_level)}>
                              {labelFor(RISK_OPTIONS, s.suggested_risk_level)} risk
                            </span>
                          </>
                        ) : null}
                        {s.suggestion_type === "revenue_allocation" ? (
                          <span className="text-xs text-gray-400">
                            Suggested revenue allocation: {numberText(s.suggested_revenue_allocation_percentage)}% (scoring
                            and dashboards only)
                          </span>
                        ) : null}
                        {s.suggestion_type === "kpi_weight" ? (
                          <span className="text-xs text-gray-400">Suggested weight: {numberText(s.suggested_weight)}%</span>
                        ) : null}
                      </div>

                      {isEditing ? (
                        <div className="mt-4 space-y-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                          {s.suggestion_type === "critical_position" ? (
                            <div className="flex flex-wrap gap-3">
                              <div>
                                <label className="mb-1 block text-xs text-gray-500">Why it matters</label>
                                <select
                                  value={editValues.criticality}
                                  onChange={function (e) {
                                    setEditValues({ ...editValues, criticality: e.target.value });
                                  }}
                                  className={inputClass}
                                >
                                  {CRITICALITY_OPTIONS.map(function (o) {
                                    return (
                                      <option key={o.value} value={o.value}>
                                        {o.label}
                                      </option>
                                    );
                                  })}
                                </select>
                              </div>
                              <div>
                                <label className="mb-1 block text-xs text-gray-500">Risk level</label>
                                <select
                                  value={editValues.risk}
                                  onChange={function (e) {
                                    setEditValues({ ...editValues, risk: e.target.value });
                                  }}
                                  className={inputClass}
                                >
                                  {RISK_OPTIONS.map(function (o) {
                                    return (
                                      <option key={o.value} value={o.value}>
                                        {o.label}
                                      </option>
                                    );
                                  })}
                                </select>
                              </div>
                            </div>
                          ) : null}
                          {s.suggestion_type === "revenue_allocation" ? (
                            <div>
                              <label className="mb-1 block text-xs text-gray-500">Revenue allocation (%)</label>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={editValues.percent}
                                onChange={function (e) {
                                  setEditValues({ ...editValues, percent: e.target.value });
                                }}
                                className={inputClass + " w-32"}
                              />
                            </div>
                          ) : null}
                          {s.suggestion_type === "missing_department" ? (
                            <div>
                              <label className="mb-1 block text-xs text-gray-500">Department name</label>
                              <input
                                type="text"
                                value={editValues.name}
                                onChange={function (e) {
                                  setEditValues({ ...editValues, name: e.target.value });
                                }}
                                className={inputClass + " w-72"}
                              />
                            </div>
                          ) : null}
                          {s.suggestion_type === "kpi_weight" ? (
                            <div>
                              <label className="mb-1 block text-xs text-gray-500">Weight (%)</label>
                              <input
                                type="number"
                                min="0"
                                max="100"
                                step="0.01"
                                value={editValues.weight}
                                onChange={function (e) {
                                  setEditValues({ ...editValues, weight: e.target.value });
                                }}
                                className={inputClass + " w-32"}
                              />
                            </div>
                          ) : null}
                          {editError ? <p className="text-xs text-red-400">{editError}</p> : null}
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              disabled={isBusy}
                              onClick={function () {
                                saveEdit(s);
                              }}
                              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {isBusy ? "Saving…" : "Save changes"}
                            </button>
                            <button
                              type="button"
                              disabled={isBusy}
                              onClick={function () {
                                setEditingId(null);
                                setEditError("");
                              }}
                              className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </div>

                    <div className="flex flex-shrink-0 items-center gap-2">
                      <button
                        type="button"
                        disabled={isDecided || isBusy}
                        onClick={function () {
                          review(s, "approve");
                        }}
                        className="rounded-lg border border-emerald-500/40 px-4 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={isDecided || isBusy}
                        onClick={function () {
                          startEdit(s);
                        }}
                        className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={isDecided || isBusy}
                        onClick={function () {
                          review(s, "reject");
                        }}
                        className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/okrs");
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
              onClick={function () {
                router.push("/onboarding/kpis");
              }}
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          {pendingCount > 0 && !loading ? (
            <p className="text-right text-xs text-gray-500">
              You can continue without reviewing everything. Anything you skip stays pending.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

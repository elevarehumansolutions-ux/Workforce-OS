"use client";

import { useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchAllPages, roleLabel } from "@/lib/tasks";
import type { Department, Position } from "@/lib/tasks";
import { isHrRole, loadMe, SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS } from "@/lib/settings";
import type { MeData } from "@/lib/settings";
import { CRITICALITY_OPTIONS, RISK_OPTIONS, optionLabel, riskClasses } from "@/lib/criticalRoles";
import { useLoad } from "@/lib/useLoad";

interface Suggestion {
  id: string;
  position_id: string | null;
  suggested_criticality_type: string | null;
  suggested_risk_level: string | null;
  rationale: string;
}

interface PageData {
  me: MeData;
  suggestions: Suggestion[];
  positions: Record<string, Position>;
  departments: Record<string, string>;
}

type Decision = "approved" | "edited" | "rejected";

async function loadPage(): Promise<PageData> {
  const me = await loadMe();
  const results = await Promise.all([
    fetchAllPages<Suggestion>("/ai-suggestions?status=pending&suggestion_type=critical_position"),
    fetchAllPages<Position>("/positions"),
    fetchAllPages<Department>("/departments"),
  ]);
  const positions: Record<string, Position> = {};
  for (const p of results[1]) positions[p.id] = p;
  const departments: Record<string, string> = {};
  for (const d of results[2]) departments[d.id] = d.name;
  return { me: me, suggestions: results[0], positions: positions, departments: departments };
}

const DECISION_TEXT: Record<Decision, string> = {
  approved: "Approved",
  edited: "Approved with your changes",
  rejected: "Rejected",
};

export default function CriticalRolesSuggestionsPage() {
  const [reloads, setReloads] = useState(0);
  const state = useLoad<PageData>("critical-suggestions-" + reloads, loadPage, "Couldn't load suggestions. Check your connection and try again.");
  const data = state.data;

  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editCriticality, setEditCriticality] = useState("");
  const [editRisk, setEditRisk] = useState("");
  const [editError, setEditError] = useState("");

  const canReview = data !== null && isHrRole(data.me.role);
  const suggestions = data ? data.suggestions : [];
  const pending = suggestions.filter(function (s) {
    return !decisions[s.id];
  });

  function positionTitle(s: Suggestion): string {
    if (!data || !s.position_id || !data.positions[s.position_id]) return "A position";
    return data.positions[s.position_id].title;
  }

  function departmentOf(s: Suggestion): string {
    if (!data || !s.position_id || !data.positions[s.position_id]) return "";
    return data.departments[data.positions[s.position_id].department_id] || "";
  }

  async function failed(err: unknown) {
    setError(err instanceof ApiError ? err.message : "Couldn't save that. Check your connection and try again.");
    // Someone else already handled it, or the position changed: show the server's current list.
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      setDecisions({});
      setReloads(reloads + 1);
    }
  }

  async function review(s: Suggestion, action: "approve" | "reject") {
    setError("");
    setNotice("");
    setBusyId(s.id);
    try {
      await apiFetch("/ai-suggestions/" + s.id + "/" + action, { method: "POST" });
      setDecisions({ ...decisions, [s.id]: action === "approve" ? "approved" : "rejected" });
    } catch (err) {
      await failed(err);
    } finally {
      setBusyId(null);
    }
  }

  function startEdit(s: Suggestion) {
    setError("");
    setNotice("");
    setEditError("");
    setEditingId(s.id);
    setEditCriticality(s.suggested_criticality_type || "");
    setEditRisk(s.suggested_risk_level || "");
  }

  async function saveEdit(s: Suggestion) {
    // Send only what changed: the server refuses an edit identical to the AI's own values.
    const body: Record<string, string> = {};
    if (editCriticality && editCriticality !== s.suggested_criticality_type) body.criticality_type = editCriticality;
    if (editRisk && editRisk !== s.suggested_risk_level) body.risk_level = editRisk;
    if (Object.keys(body).length === 0) {
      setEditError("Change a value first, or just use Approve to accept it as suggested.");
      return;
    }
    setEditError("");
    setBusyId(s.id);
    try {
      await apiFetch("/ai-suggestions/" + s.id + "/edit", { method: "POST", body: body });
      setDecisions({ ...decisions, [s.id]: "edited" });
      setEditingId(null);
    } catch (err) {
      setEditError(err instanceof ApiError ? err.message : "Couldn't save that. Check your connection and try again.");
      if (err instanceof ApiError && (err.status === 404 || err.status === 409)) await failed(err);
    } finally {
      setBusyId(null);
    }
  }

  async function approveAll() {
    setError("");
    setNotice("");
    setBulkBusy(true);
    const next: Record<string, Decision> = { ...decisions };
    let approved = 0;
    let failedCount = 0;
    let firstMessage = "";
    for (const s of pending) {
      try {
        await apiFetch("/ai-suggestions/" + s.id + "/approve", { method: "POST" });
        next[s.id] = "approved";
        approved = approved + 1;
      } catch (err) {
        failedCount = failedCount + 1;
        if (!firstMessage) firstMessage = err instanceof ApiError ? err.message : "Couldn't reach the server.";
      }
    }
    setDecisions(next);
    if (approved > 0) setNotice(approved + (approved === 1 ? " suggestion approved." : " suggestions approved."));
    if (failedCount > 0) {
      setError(failedCount + (failedCount === 1 ? " suggestion" : " suggestions") + " couldn't be applied: " + firstMessage + " Review those one by one.");
    }
    setBulkBusy(false);
  }

  return (
    <AppShell
      activeLabel="Employees"
      title="Critical Role Suggestions"
      breadcrumb="Employees > Critical Roles > AI Suggestions"
      userName={data ? data.me.fullName : undefined}
      userRole={data ? roleLabel(data.me.role) : undefined}
    >
      {state.error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</div>
      ) : null}
      {error ? <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div> : null}
      {notice ? <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</div> : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-[#0d1220]/80 px-6 py-4 shadow-xl">
        <div>
          <p className="text-sm font-medium text-white">
            {state.loading ? "Loading…" : pending.length + (pending.length === 1 ? " role waiting for review" : " roles waiting for review")}
          </p>
          <p className="mt-0.5 text-xs text-gray-500">
            Approving marks the role as critical. New suggestions can take a few minutes to appear after you add positions.{" "}
            <Link href="/employees/critical-roles" className="text-indigo-400 hover:text-indigo-300">Back to registry</Link>
          </p>
        </div>
        {canReview && pending.length > 1 ? (
          <button
            type="button"
            disabled={bulkBusy}
            onClick={approveAll}
            className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:opacity-50"
          >
            {bulkBusy ? "Approving…" : "Approve all"}
          </button>
        ) : null}
      </div>

      {data && !canReview ? (
        <p className="mt-4 text-sm text-gray-500">Only an HR administrator can approve or reject suggestions.</p>
      ) : null}

      {!state.loading && !state.error && suggestions.length === 0 ? (
        <p className="mt-6 text-sm text-gray-500">Nothing to review right now.</p>
      ) : null}

      <div className="mt-6 flex flex-col gap-4">
        {suggestions.map(function (s) {
          const decision = decisions[s.id];
          const busy = busyId === s.id || bulkBusy;
          return (
            <div key={s.id} className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {positionTitle(s)}
                    {departmentOf(s) ? (
                      <>
                        <span className="mx-2 text-gray-600">&bull;</span>
                        <span className="font-normal text-gray-400">{departmentOf(s)}</span>
                      </>
                    ) : null}
                    <span className="ml-2 rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-medium text-indigo-300">AI SUGGESTED</span>
                  </p>
                  <p className="mt-1 text-sm text-gray-500">AI rationale: {s.rationale}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="rounded-full bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-300">
                      {optionLabel(CRITICALITY_OPTIONS, s.suggested_criticality_type)}
                    </span>
                    <span className={"rounded-full px-2.5 py-1 text-xs font-medium " + riskClasses(s.suggested_risk_level)}>
                      {optionLabel(RISK_OPTIONS, s.suggested_risk_level)} risk
                    </span>
                  </div>
                </div>

                {decision ? (
                  <span className="rounded-full bg-white/5 px-3 py-1 text-xs font-medium text-gray-300">{DECISION_TEXT[decision]}</span>
                ) : canReview ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={function () { review(s, "approve"); }}
                      className="rounded-lg bg-emerald-500/15 px-3 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/25 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={function () { startEdit(s); }}
                      className="rounded-lg border border-white/10 px-3 py-1.5 text-sm font-medium text-gray-300 transition hover:bg-white/5 disabled:opacity-50"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={function () { review(s, "reject"); }}
                      className="rounded-lg bg-red-500/15 px-3 py-1.5 text-sm font-medium text-red-300 transition hover:bg-red-500/25 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                ) : null}
              </div>

              {editingId === s.id && !decision ? (
                <div className="mt-4 border-t border-white/10 pt-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label className={SETTINGS_LABEL_CLASS}>Why it is critical</label>
                      <select value={editCriticality} onChange={function (e) { setEditCriticality(e.target.value); }} className={SETTINGS_INPUT_CLASS}>
                        {CRITICALITY_OPTIONS.map(function (o) {
                          return <option key={o.value} value={o.value}>{o.label}</option>;
                        })}
                      </select>
                    </div>
                    <div>
                      <label className={SETTINGS_LABEL_CLASS}>Risk level</label>
                      <select value={editRisk} onChange={function (e) { setEditRisk(e.target.value); }} className={SETTINGS_INPUT_CLASS}>
                        {RISK_OPTIONS.map(function (o) {
                          return <option key={o.value} value={o.value}>{o.label}</option>;
                        })}
                      </select>
                    </div>
                  </div>
                  {editError ? <p className="mt-3 text-sm text-red-300">{editError}</p> : null}
                  <div className="mt-4 flex gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={function () { saveEdit(s); }}
                      className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:opacity-50"
                    >
                      Save and approve
                    </button>
                    <button
                      type="button"
                      onClick={function () { setEditingId(null); }}
                      className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition hover:bg-white/5"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </AppShell>
  );
}

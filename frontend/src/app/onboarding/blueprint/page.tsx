"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import {
  acceptAllBlueprint,
  approveBlueprintItem,
  buildBlueprintView,
  editBlueprintItem,
  fetchLatestBlueprint,
  generateBlueprint,
  isPending,
  kpiSummary,
  rejectBlueprintItem,
  shownTitle,
} from "@/lib/blueprint";
import type {
  AcceptAllResult,
  BlueprintItem,
  ChartNode,
  ExistingDepartment,
  ExistingPosition,
  ObjectiveGroup,
} from "@/lib/blueprint";

const ONBOARDING_STEPS = [
  "Business DNA",
  "AI Structure",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

// The backend drafts the blueprint in the background, normally in well under a
// minute. Look every 4 seconds, for up to about 2 minutes, then offer a retry.
const POLL_EVERY_MS = 4000;
const MAX_POLLS = 30;

interface Editing {
  id: string;
  text: string;
}

// The departments and positions the company already has. Only used for labels and
// extra boxes in the chart, so a failure just means "none" rather than an error.
async function fetchExisting(): Promise<{ departments: ExistingDepartment[]; positions: ExistingPosition[] } | null> {
  try {
    const [deptRes, posRes] = await Promise.all([
      apiFetch<{ data: ExistingDepartment[] }>("/departments?limit=100", { method: "GET" }),
      apiFetch<{ data: ExistingPosition[] }>("/positions?limit=100", { method: "GET" }),
    ]);
    return { departments: deptRes.data, positions: posRes.data };
  } catch {
    return null;
  }
}

export default function BlueprintPage() {
  const router = useRouter();
  const [items, setItems] = useState<BlueprintItem[]>([]);
  const [existingDepartments, setExistingDepartments] = useState<ExistingDepartment[]>([]);
  const [existingPositions, setExistingPositions] = useState<ExistingPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [waiting, setWaiting] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [pollRound, setPollRound] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [skipped, setSkipped] = useState<AcceptAllResult["skipped"]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [acceptingAll, setAcceptingAll] = useState(false);
  const [generating, setGenerating] = useState(false);

  // What the company already has. The chart draws existing positions too, and the
  // tidy-ups ("rename Hr to Human Resources") need the current names.
  async function loadExisting() {
    const existing = await fetchExisting();
    if (existing) {
      setExistingDepartments(existing.departments);
      setExistingPositions(existing.positions);
    }
  }

  useEffect(function () {
    let cancelled = false;
    fetchExisting().then(function (existing) {
      if (cancelled || !existing) return;
      setExistingDepartments(existing.departments);
      setExistingPositions(existing.positions);
    });
    return function () {
      cancelled = true;
    };
  }, []);

  // Look for the blueprint; while there is none yet, keep looking.
  useEffect(
    function () {
      let cancelled = false;
      let polls = 0;
      let timer: ReturnType<typeof setTimeout> | null = null;

      async function check() {
        try {
          const list = await fetchLatestBlueprint();
          if (cancelled) return;
          setLoadError("");
          setItems(list);
          if (list.length === 0 && polls < MAX_POLLS) {
            polls += 1;
            setWaiting(true);
            timer = setTimeout(check, POLL_EVERY_MS);
            return;
          }
          setWaiting(false);
          setTimedOut(list.length === 0);
          setLoading(false);
        } catch (err) {
          if (cancelled) return;
          setWaiting(false);
          setLoading(false);
          if (err instanceof ApiError && err.status === 403) {
            setForbidden(true);
          } else {
            setLoadError(err instanceof ApiError ? err.message : "Couldn't load your suggested structure.");
          }
        }
      }

      check();
      return function () {
        cancelled = true;
        if (timer) clearTimeout(timer);
      };
    },
    [pollRound]
  );

  async function refresh() {
    try {
      setItems(await fetchLatestBlueprint());
      // Approving creates real departments and positions, so re-read those too.
      await loadExisting();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't refresh the list.");
    }
  }

  async function runAction(item: BlueprintItem, action: () => Promise<unknown>, failMessage: string) {
    setActionError("");
    setNotice("");
    setBusyId(item.id);
    try {
      await action();
    } catch (err) {
      if (err instanceof ApiError && err.code === "BLUEPRINT_ITEM_ALREADY_REVIEWED") {
        setActionError("Someone already reviewed that one. The list has been refreshed.");
      } else {
        // For BLUEPRINT_PARENT_REJECTED the backend's message names the rejected parent.
        setActionError(err instanceof ApiError ? err.message : failMessage);
      }
    } finally {
      // Approving a position also adds its department and boss, so always re-read.
      await refresh();
      setBusyId(null);
    }
  }

  function approve(item: BlueprintItem) {
    runAction(item, function () { return approveBlueprintItem(item.id); }, "Couldn't add that suggestion.");
  }

  function reject(item: BlueprintItem) {
    runAction(item, function () { return rejectBlueprintItem(item.id); }, "Couldn't skip that suggestion.");
  }

  async function saveEdit() {
    if (!editing) return;
    const text = editing.text.trim();
    const item = items.find(function (i) { return i.id === editing.id; });
    if (!item || text === "") return;
    setEditing(null);
    await runAction(item, function () { return editBlueprintItem(item.id, text); }, "Couldn't save your change.");
  }

  async function handleAcceptAll() {
    setActionError("");
    setNotice("");
    setSkipped([]);
    setAcceptingAll(true);
    try {
      const result = await acceptAllBlueprint();
      setNotice(result.accepted + (result.accepted === 1 ? " suggestion added." : " suggestions added."));
      setSkipped(result.skipped);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add the suggestions.");
    } finally {
      await refresh();
      setAcceptingAll(false);
    }
  }

  async function handleGenerateAgain() {
    setActionError("");
    setGenerating(true);
    try {
      const result = await generateBlueprint();
      if (result.status === "already_pending") {
        setNotice("You still have suggestions waiting for review.");
        await refresh();
      } else {
        setItems([]);
        setTimedOut(false);
        setLoading(true);
        setPollRound(pollRound + 1);
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't start a new draft.");
    } finally {
      setGenerating(false);
    }
  }

  const view = buildBlueprintView(items, existingDepartments, existingPositions);
  const pendingCount = items.filter(isPending).length;
  const showContent = !loading && !forbidden && items.length > 0;

  // The functions below return markup; they are NOT components, on purpose. A
  // component defined inside this one would be rebuilt on every keystroke and the
  // edit box would lose focus after each letter.

  function renderActions(item: BlueprintItem) {
    const busy = busyId === item.id || acceptingAll;
    if (item.status === "approved" || item.status === "edited") {
      return <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-300">Added</span>;
    }
    if (item.status === "rejected") {
      return <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-medium text-gray-400">Skipped</span>;
    }
    return (
      <div className="flex flex-shrink-0 items-center justify-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={function () { approve(item); }}
          className="rounded-full bg-indigo-500 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
        >
          {busy ? "…" : "Add"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={function () { setEditing({ id: item.id, text: item.title }); }}
          className="rounded-full border border-white/15 px-3 py-1 text-xs font-medium text-gray-300 hover:border-white/30 disabled:opacity-50"
        >
          Edit
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={function () { reject(item); }}
          className="rounded-full border border-white/15 px-3 py-1 text-xs font-medium text-gray-400 hover:border-red-400/50 hover:text-red-300 disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    );
  }

  // The little box used to type a new wording for an item.
  function renderEditBox(item: BlueprintItem) {
    if (!editing) return null;
    return (
      <div className="space-y-2">
        <input
          autoFocus
          type="text"
          value={editing.text}
          maxLength={300}
          onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
            setEditing({ id: item.id, text: e.target.value });
          }}
          onKeyDown={function (e: React.KeyboardEvent<HTMLInputElement>) {
            if (e.key === "Enter") saveEdit();
            if (e.key === "Escape") setEditing(null);
          }}
          className="w-full rounded-lg border border-white/10 bg-[#111726] px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
        />
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={saveEdit}
            className="rounded-full bg-indigo-500 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-600"
          >
            Save &amp; add
          </button>
          <button
            type="button"
            onClick={function () { setEditing(null); }}
            className="text-xs text-gray-400 hover:text-gray-200"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // One row of text with its actions: used for objectives, key results and tidy-ups.
  function renderLine(props: { item: BlueprintItem; text?: string; note?: string | null; small?: boolean }) {
    const item = props.item;
    const isEditing = editing !== null && editing.id === item.id;
    const dimmed = item.status === "rejected";
    return (
      <div
        key={item.id}
        className="flex items-start justify-between gap-3 rounded-lg border border-white/5 bg-[#0a0e1a] px-3 py-2.5"
      >
        <div className="min-w-0 flex-1">
          {isEditing ? (
            renderEditBox(item)
          ) : (
            <p className={(props.small ? "text-sm " : "text-sm font-medium ") + (dimmed ? "text-gray-500 line-through" : "text-white")}>
              {props.text || shownTitle(item)}
            </p>
          )}
          {props.note ? <p className="mt-0.5 text-xs text-indigo-300/80">{props.note}</p> : null}
          {!isEditing && !props.small && item.rationale ? (
            <p className="mt-0.5 text-xs text-gray-500">{item.rationale}</p>
          ) : null}
        </div>
        {isEditing ? null : renderActions(item)}
      </div>
    );
  }

  function renderObjectives(list: ObjectiveGroup[]) {
    return (
      <div className="space-y-3">
        {list.map(function (group) {
          return (
            <div key={group.objective.id} className="space-y-1.5">
              {renderLine({ item: group.objective })}
              {group.keyResults.map(function (kr) {
                return (
                  <div key={kr.id} className="flex items-start gap-2">
                    <span className="ml-5 mt-3.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-500" />
                    <div className="flex-1">{renderLine({ item: kr, small: true })}</div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  }

  // One box of the organization chart.
  function renderChartBox(node: ChartNode) {
    if (node.virtual) {
      return (
        <div className="inline-block rounded-full border border-white/20 bg-[#111726] px-5 py-2 text-sm font-semibold text-gray-200">
          {node.title}
        </div>
      );
    }
    const item = node.item;
    const isEditing = item !== null && editing !== null && editing.id === item.id;
    return (
      <div
        className="inline-block w-48 rounded-xl border border-white/10 bg-[#0a0e1a] px-3 pb-3 pt-2.5 text-left shadow-lg"
        style={{ borderTop: "3px solid " + node.color }}
      >
        {item && isEditing ? (
          renderEditBox(item)
        ) : (
          <div className="text-center">
            <p className="text-sm font-semibold leading-snug text-white">{node.title}</p>
            {node.departmentName ? (
              <p className="mt-1 flex items-center justify-center gap-1.5 text-xs text-gray-400">
                <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ backgroundColor: node.color }} />
                {node.departmentName}
              </p>
            ) : null}
            <div className="mt-2.5">
              {item ? (
                renderActions(item)
              ) : (
                <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-gray-400">Already in your company</span>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderChartNode(node: ChartNode) {
    return (
      <li key={node.key}>
        {renderChartBox(node)}
        {node.children.length > 0 ? <ul>{node.children.map(renderChartNode)}</ul> : null}
      </li>
    );
  }

  // "Weight 60% · Target 95 % · Higher is better", plus the key result it measures.
  function kpiNote(kpi: BlueprintItem): string {
    const keyResult = items.find(function (i) {
      return i.kind === "key_result" && i.ref !== null && i.ref === kpi.key_result_ref;
    });
    return kpiSummary(kpi) + (keyResult ? " · Measures: " + shownTitle(keyResult) : "");
  }

  function cleanupText(item: BlueprintItem): string {
    if (item.kind === "rename_department") {
      const current = existingDepartments.find(function (d) { return d.id === item.department_id; });
      return "Rename “" + (current ? current.name : "department") + "” to “" + shownTitle(item) + "”";
    }
    if (item.kind === "rename_position") {
      const current = existingPositions.find(function (p) { return p.id === item.position_id; });
      return "Rename “" + (current ? current.title : "position") + "” to “" + shownTitle(item) + "”";
    }
    return item.title;
  }

  const card = "rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-2xl";
  const sectionLabel = "mb-3 text-xs uppercase tracking-wide text-gray-500";

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

            if (i < 1) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else if (i === 1) {
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
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Your suggested structure</h1>
          <p className="mt-2 text-gray-400">
            From your Business DNA, our AI drafted your objectives, your departments, your organization chart
            (who reports to whom) and your KPIs. Add what fits, edit the wording, or skip anything. You can
            change all of it later.
          </p>
        </div>

        <div className="mx-auto max-w-3xl">
          {loadError ? (
            <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{loadError}</div>
          ) : null}
          {actionError ? (
            <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{actionError}</div>
          ) : null}
          {notice ? (
            <div className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</div>
          ) : null}
          {skipped.length > 0 ? (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              <p className="font-medium">
                {skipped.length} {skipped.length === 1 ? "suggestion" : "suggestions"} couldn&apos;t be added. Review {skipped.length === 1 ? "it" : "them"} one by one:
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs">
                {skipped.map(function (s) {
                  return (
                    <li key={s.id}>
                      {s.title}: {s.reason}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {forbidden ? (
            <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-center text-sm text-gray-300">
              Only an HR administrator or executive can review the suggested structure. You can carry on with
              the next step.
            </div>
          ) : null}

          {loading || waiting ? (
            <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-10 text-center">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
              <p className="mt-4 text-sm font-medium text-white">Drafting your structure from your Business DNA…</p>
              <p className="mt-1 text-xs text-gray-500">This usually takes under a minute. You can wait here.</p>
            </div>
          ) : null}

          {!loading && !waiting && !forbidden && items.length === 0 && timedOut ? (
            <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-center">
              <p className="text-sm font-medium text-white">Nothing has arrived yet.</p>
              <p className="mt-1 text-xs text-gray-500">
                Make sure your Business DNA has your industry or what you sell, then try again. Or set things up by hand on the next steps.
              </p>
              <button
                type="button"
                onClick={handleGenerateAgain}
                disabled={generating}
                className="mt-4 rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
              >
                {generating ? "Starting…" : "Try again"}
              </button>
            </div>
          ) : null}
        </div>

        {showContent ? (
          <div className="mt-8 space-y-6">
            <div className="mx-auto flex max-w-3xl items-center justify-between rounded-xl border border-white/10 bg-[#0d1220]/80 px-5 py-4">
              <p className="text-sm text-gray-300">
                {pendingCount === 0
                  ? "All reviewed. Nothing is waiting."
                  : pendingCount + (pendingCount === 1 ? " suggestion is" : " suggestions are") + " waiting for you."}
              </p>
              <button
                type="button"
                onClick={handleAcceptAll}
                disabled={pendingCount === 0 || acceptingAll}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-40"
              >
                {acceptingAll ? "Adding…" : "Accept all"}
              </button>
            </div>

            {/* Objectives */}
            {view.objectiveSections.length > 0 ? (
              <div className={card + " space-y-6"}>
                <p className="text-xs uppercase tracking-wide text-gray-500">Objectives and key results</p>
                {view.objectiveSections.map(function (section) {
                  return (
                    <div key={section.title}>
                      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-200">
                        {section.color ? (
                          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: section.color }} />
                        ) : null}
                        {section.title}
                      </p>
                      {renderObjectives(section.objectives)}
                    </div>
                  );
                })}
              </div>
            ) : null}

            {/* Departments */}
            {view.departments.length > 0 ? (
              <div className={card}>
                <p className={sectionLabel}>Departments</p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {view.departments.map(function (d) {
                    const item = d.item;
                    const isEditing = item !== null && editing !== null && editing.id === item.id;
                    return (
                      <div
                        key={d.key}
                        className="rounded-xl border border-white/10 bg-[#0a0e1a] p-3"
                        style={{ borderLeft: "4px solid " + d.color }}
                      >
                        {item && isEditing ? (
                          renderEditBox(item)
                        ) : (
                          <div>
                            <p className={"text-sm font-semibold " + (item && item.status === "rejected" ? "text-gray-500 line-through" : "text-white")}>
                              {d.name}
                            </p>
                            {item && item.rationale ? <p className="mt-0.5 text-xs text-gray-500">{item.rationale}</p> : null}
                            <div className="mt-2">
                              {item ? (
                                renderActions(item)
                              ) : (
                                <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-gray-400">Already in your company</span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* The organization chart */}
            <div className={card}>
              <p className={sectionLabel}>Organization chart</p>
              {view.chart ? (
                <div className="overflow-x-auto pb-2 [color-scheme:dark]">
                  <div className="org-tree mx-auto w-max min-w-full">
                    <ul>{renderChartNode(view.chart)}</ul>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  No roles to show yet. Add roles later in Organization structure.
                </p>
              )}
              <p className="mt-3 text-xs text-gray-500">
                Each box is a role; the line above it goes to who it reports to. Colours match the departments
                above. A skipped role leaves the roles under it without a boss.
              </p>
            </div>

            {/* KPIs */}
            {view.kpiSections.length > 0 ? (
              <div className={card + " space-y-6"}>
                <p className="text-xs uppercase tracking-wide text-gray-500">KPIs</p>
                {view.kpiSections.map(function (section) {
                  return (
                    <div key={section.title}>
                      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-200">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: section.color }} />
                        {section.title}
                      </p>
                      <div className="space-y-1.5">
                        {section.kpis.map(function (kpi) {
                          return renderLine({ item: kpi, note: kpiNote(kpi) });
                        })}
                      </div>
                    </div>
                  );
                })}
                <p className="text-xs text-gray-500">
                  Weights are each KPI&apos;s share of its department&apos;s score. Targets are a starting point:
                  you can change them on the KPIs step.
                </p>
              </div>
            ) : null}

            {/* Tidy-ups of what the company already has */}
            {view.cleanups.length > 0 ? (
              <div className={card + " space-y-2"}>
                <p className="text-xs uppercase tracking-wide text-gray-500">Tidy-ups for what you already have</p>
                {view.cleanups.map(function (item) {
                  return renderLine({
                    item: item,
                    text: cleanupText(item),
                    note: item.kind === "review_note" ? "A note for you. Adding it just marks it as seen." : null,
                  });
                })}
              </div>
            ) : null}

            <div className="text-center">
              <button
                type="button"
                onClick={handleGenerateAgain}
                disabled={generating || pendingCount > 0}
                title={pendingCount > 0 ? "Review the current suggestions first" : undefined}
                className="text-xs text-gray-500 hover:text-gray-300 disabled:opacity-40"
              >
                {generating ? "Starting…" : "Draft a new set of suggestions"}
              </button>
            </div>
          </div>
        ) : null}

        <div className="mx-auto mt-8 flex max-w-3xl items-center justify-between border-t border-white/10 pt-6">
          <button
            type="button"
            onClick={function () { router.push("/onboarding/business-dna"); }}
            className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Go Back
          </button>
          <button
            type="button"
            onClick={function () { router.push("/onboarding/org-setup"); }}
            className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
          >
            Continue
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

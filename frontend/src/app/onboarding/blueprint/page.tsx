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
  directionText,
  formatMoney,
  isPending,
  kpiAnnualReturn,
  rejectBlueprintItem,
  trimNumber,
  shownTitle,
} from "@/lib/blueprint";
import type {
  AcceptAllResult,
  BlueprintItem,
  ChartNode,
  DepartmentChartNode,
  ExistingDepartment,
  ExistingPosition,
  ObjectiveGroup,
} from "@/lib/blueprint";
import Logo from "@/components/Logo";

const ONBOARDING_STEPS = ["Business DNA", "OS Structure", "Invite Team"];

// The backend drafts the blueprint in the background, normally in well under a
// minute. Look every 4 seconds, for up to about 2 minutes, then offer a retry.
const POLL_EVERY_MS = 4000;
const MAX_POLLS = 30;

interface Editing {
  id: string;
  text: string;
}

// The capital investment from the Business DNA (naira), or null when none was entered
// or the caller may not read it. Used to turn each department's percentage into money.
async function fetchCapital(): Promise<number | null> {
  try {
    const dna = await apiFetch<{ capital_investment_amount: string | number | null }>("/business-dna", { method: "GET" });
    const amount = dna.capital_investment_amount;
    if (amount === null || amount === undefined || amount === "") return null;
    const n = Number(amount);
    return n > 0 ? n : null;
  } catch {
    return null;
  }
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
  const [capital, setCapital] = useState<number | null>(null);
  const [chartMode, setChartMode] = useState<"departments" | "roles">("departments");
  const [openDepartment, setOpenDepartment] = useState<string | null>(null);

  useEffect(function () {
    let cancelled = false;
    fetchCapital().then(function (amount) {
      if (!cancelled) setCapital(amount);
    });
    return function () {
      cancelled = true;
    };
  }, []);

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

  const view = buildBlueprintView(items, existingDepartments, existingPositions, capital);
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
            {node.isCritical ? (
              <div className="mt-1.5 rounded-md bg-amber-500/10 px-2 py-1">
                <p className="text-xs font-semibold text-amber-300">★ Critical role</p>
                {node.criticalLabel ? <p className="text-[11px] leading-tight text-amber-200/80">{node.criticalLabel}</p> : null}
              </div>
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

  // One KPI as a card that says what it is: why it exists, its share of the department's
  // score, the target, which way is good, the key result it measures, and what it is
  // expected to return (its weight's share of the department's yearly return).
  function renderKpi(kpi: BlueprintItem, departmentName: string, departmentReturn: number | null) {
    const isEditing = editing !== null && editing.id === kpi.id;
    const keyResult = items.find(function (i) {
      return i.kind === "key_result" && i.ref !== null && i.ref === kpi.key_result_ref;
    });
    const target =
      kpi.kpi_target_value !== null
        ? trimNumber(kpi.kpi_target_value) + (kpi.kpi_unit ? " " + kpi.kpi_unit : "")
        : "Not set";
    const kpiReturn = kpiAnnualReturn(departmentReturn, kpi.kpi_weight);
    const fact = "text-sm text-gray-200";
    const label = "text-[11px] uppercase tracking-wide text-gray-500";
    return (
      <div key={kpi.id} className="rounded-lg border border-white/5 bg-[#0a0e1a] p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {isEditing ? (
              renderEditBox(kpi)
            ) : (
              <p className={"text-sm font-semibold " + (kpi.status === "rejected" ? "text-gray-500 line-through" : "text-white")}>
                {shownTitle(kpi)}
              </p>
            )}
            {!isEditing && kpi.rationale ? <p className="mt-0.5 text-xs text-gray-500">{kpi.rationale}</p> : null}
          </div>
          {isEditing ? null : renderActions(kpi)}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className={label}>Share of score</p>
            <p className={fact}>
              {kpi.kpi_weight !== null ? trimNumber(kpi.kpi_weight) + "%" : "-"}
              <span className="text-xs text-gray-500"> of {departmentName}</span>
            </p>
          </div>
          <div>
            <p className={label}>Target</p>
            <p className={fact}>{target}</p>
          </div>
          <div>
            <p className={label}>What is good</p>
            <p className="text-xs text-gray-300">{directionText(kpi)}</p>
          </div>
          <div>
            <p className={label}>Expected contribution</p>
            {kpiReturn !== null ? (
              <p className={fact}>
                {formatMoney(kpiReturn)}
                <span className="text-xs text-gray-500"> a year</span>
              </p>
            ) : (
              <p className="text-xs text-gray-500">Shown once a capital amount and a share are set</p>
            )}
          </div>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {keyResult ? "Measures the key result: " + shownTitle(keyResult) : "Not linked to a key result"}
        </p>
      </div>
    );
  }

  // One department on the department chart, with its share of the capital, revenue target
  // and estimated profit. Clicking it opens its panel below the chart.
  function renderDepartmentBox(node: DepartmentChartNode) {
    if (node.virtual || node.card === null) {
      return (
        <div className="inline-block rounded-full border border-white/20 bg-[#111726] px-5 py-2 text-sm font-semibold text-gray-200">
          Company{view.capital !== null ? " · " + formatMoney(view.capital) + " capital" : ""}
        </div>
      );
    }
    const d = node.card;
    const selected = openDepartment === d.key;
    return (
      <button
        type="button"
        onClick={function () { setOpenDepartment(selected ? null : d.key); }}
        className={
          "inline-block w-56 rounded-xl border bg-[#0a0e1a] px-3 pb-3 pt-2.5 text-left shadow-lg transition hover:border-indigo-400/60 " +
          (selected ? "border-indigo-400" : "border-white/10")
        }
        style={{ borderTop: "3px solid " + d.color }}
      >
        <p className="text-sm font-semibold leading-snug text-white">{d.name}</p>
        {d.isCritical ? <p className="mt-0.5 text-xs font-semibold text-amber-300">★ Critical department</p> : null}
        {d.sharePct !== null ? (
          <div className="mt-2 space-y-0.5">
            <p className="text-xs text-gray-400">{trimNumber(d.sharePct)}% of capital</p>
            {d.annualReturn !== null ? (
              <p className="text-sm font-semibold text-white">
                {formatMoney(d.annualReturn)}
                <span className="text-xs font-normal text-gray-500"> revenue target a year</span>
              </p>
            ) : null}
            {d.annualProfit !== null ? (
              <p className="text-xs text-emerald-300">Est. profit {formatMoney(d.annualProfit)}</p>
            ) : null}
          </div>
        ) : (
          <p className="mt-2 text-xs text-gray-600">No share of the capital</p>
        )}
        <p className="mt-2 text-[11px] text-gray-500">
          {d.roles.length} {d.roles.length === 1 ? "role" : "roles"} · click to open
        </p>
      </button>
    );
  }

  function renderDepartmentChartNode(node: DepartmentChartNode) {
    return (
      <li key={node.key}>
        {renderDepartmentBox(node)}
        {node.children.length > 0 ? <ul>{node.children.map(renderDepartmentChartNode)}</ul> : null}
      </li>
    );
  }

  // The panel for the clicked department: the money, then its roles, then its KPIs.
  function renderDepartmentPanel() {
    const d = view.departments.find(function (x) { return x.key === openDepartment; });
    if (!d) return null;
    const kpis = view.kpiSections.find(function (s) { return s.title === d.name; });
    const tile = "rounded-lg border border-white/5 bg-[#0a0e1a] p-3";
    const label = "text-[11px] uppercase tracking-wide text-gray-500";
    return (
      <div className="mt-4 rounded-xl border border-indigo-400/30 bg-[#0a0e1a] p-4" style={{ borderLeft: "4px solid " + d.color }}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-base font-semibold text-white">{d.name}</p>
            {d.isCritical ? <p className="text-xs font-semibold text-amber-300">★ Critical department</p> : null}
          </div>
          <div className="flex items-center gap-3">
            {d.item ? renderActions(d.item) : null}
            <button type="button" onClick={function () { setOpenDepartment(null); }} className="text-xs text-gray-400 hover:text-gray-200">
              Close
            </button>
          </div>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className={tile}>
            <p className={label}>Share of capital</p>
            <p className="text-sm text-white">{d.sharePct !== null ? trimNumber(d.sharePct) + "%" : "None"}</p>
          </div>
          <div className={tile}>
            <p className={label}>Revenue target</p>
            {d.annualReturn !== null ? (
              <p className="text-sm text-white">
                {formatMoney(d.annualReturn)} <span className="text-xs text-gray-500">a year</span>
                <span className="block text-xs text-gray-400">{formatMoney(d.annualReturn / 4)} each quarter</span>
              </p>
            ) : (
              <p className="text-xs text-gray-500">Shown once a capital amount is set</p>
            )}
          </div>
          <div className={tile}>
            <p className={label}>Estimated profit</p>
            {d.annualProfit !== null && d.marginPct !== null ? (
              <p className="text-sm text-emerald-300">
                {formatMoney(d.annualProfit)} <span className="text-xs text-gray-500">a year</span>
                <span className="block text-xs text-gray-400">at a {trimNumber(d.marginPct)}% margin (an estimate)</span>
              </p>
            ) : (
              <p className="text-xs text-gray-500">Not available</p>
            )}
          </div>
          <div className={tile}>
            <p className={label}>Roles</p>
            <p className="text-sm text-white">{d.roles.length}</p>
          </div>
        </div>

        <p className={"mt-4 " + label}>Roles in this department</p>
        {d.roles.length === 0 ? (
          <p className="mt-1 text-sm text-gray-500">No roles yet.</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {d.roles.map(function (role) {
              return (
                <li key={role.node.key} style={{ marginLeft: role.depth * 18 }} className="flex flex-wrap items-center gap-2 text-sm text-gray-200">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: d.color }} />
                  {role.node.title}
                  {role.node.isCritical ? (
                    <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300">
                      ★ {role.node.criticalLabel || "Critical role"}
                    </span>
                  ) : null}
                  {role.node.item === null ? <span className="text-[11px] text-gray-500">already in your company</span> : null}
                </li>
              );
            })}
          </ul>
        )}

        {kpis ? (
          <div>
            <p className={"mt-4 " + label}>KPIs</p>
            <ul className="mt-1 space-y-1">
              {kpis.kpis.map(function (k) {
                return (
                  <li key={k.id} className="text-sm text-gray-200">
                    {shownTitle(k)}
                    <span className="text-xs text-gray-500"> · {k.kpi_weight !== null ? trimNumber(k.kpi_weight) + "% of score" : ""}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    );
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
          <Logo size={36} textClassName="text-base font-bold" />
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
          <h1 className="text-3xl font-bold sm:text-4xl">OS Structure</h1>
          <p className="mt-2 text-gray-400">
            Based on your Business DNA, our Elevare OS has drafted your business objectives, organization
            structure, departments and how your capital is shared between them, and your KPIs. Add what fits,
            edit the wording, or skip anything.
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
                <p className={sectionLabel}>Capital and departments</p>
                <div className="mb-4 rounded-lg border border-white/5 bg-[#0a0e1a] p-3 text-sm">
                  {view.capital !== null ? (
                    <p className="text-gray-200">
                      Your capital investment is <span className="font-semibold text-white">{formatMoney(view.capital)}</span>.
                      Each critical department is given a share of it as the return it is expected to bring back in a year.
                    </p>
                  ) : (
                    <p className="text-amber-200">
                      No capital investment amount was entered, so only percentages are shown. Add the amount in{" "}
                      <button
                        type="button"
                        onClick={function () { router.push("/onboarding/business-dna"); }}
                        className="underline hover:text-amber-100"
                      >
                        Business DNA
                      </button>{" "}
                      to see the naira figures.
                    </p>
                  )}
                  <p className="mt-1 text-xs text-gray-500">
                    Your capital is shared between your critical departments. If you skip a department, its share
                    passes to the others, so all of it stays allocated
                    {view.totalSharePct > 0 ? " (" + trimNumber(Math.round(view.totalSharePct)) + "% in total)" : ""}.
                  </p>
                </div>
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
                            {d.isCritical ? (
                              <p className="mt-2 inline-block rounded bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-300">
                                ★ Critical department
                              </p>
                            ) : null}
                            {d.sharePct !== null ? (
                              <div className="mt-2 space-y-0.5">
                                <p className="text-xs text-gray-500">Revenue target</p>
                                <p className="text-sm text-white">
                                  {trimNumber(d.sharePct)}% of capital
                                  {d.annualReturn !== null ? <span className="font-semibold"> = {formatMoney(d.annualReturn)} a year</span> : null}
                                </p>
                                {d.annualReturn !== null ? (
                                  <p className="text-xs text-gray-400">{formatMoney(d.annualReturn / 4)} each quarter</p>
                                ) : null}
                                {d.annualProfit !== null && d.marginPct !== null ? (
                                  <p className="text-xs text-gray-400">
                                    Estimated profit {formatMoney(d.annualProfit)} a year ({trimNumber(d.marginPct)}% margin)
                                  </p>
                                ) : null}
                              </div>
                            ) : null}
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

            {/* The organization chart: departments with their money, or the roles */}
            <div className={card}>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-wide text-gray-500">Organization chart</p>
                <div className="flex rounded-lg border border-white/10 p-0.5 text-xs">
                  {(["departments", "roles"] as const).map(function (mode) {
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={function () { setChartMode(mode); }}
                        className={
                          "rounded-md px-3 py-1.5 font-medium " +
                          (chartMode === mode ? "bg-indigo-500 text-white" : "text-gray-400 hover:text-gray-200")
                        }
                      >
                        {mode === "departments" ? "By department" : "By role"}
                      </button>
                    );
                  })}
                </div>
              </div>

              {chartMode === "departments" ? (
                view.departmentChart ? (
                  <div>
                    <div className="overflow-x-auto pb-2 [color-scheme:dark]">
                      <div className="org-tree mx-auto w-max min-w-full">
                        <ul>{renderDepartmentChartNode(view.departmentChart)}</ul>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-gray-500">Click a department to see its roles, revenue target and profit.</p>
                    {renderDepartmentPanel()}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No departments to show yet.</p>
                )
              ) : view.chart ? (
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
                {chartMode === "roles"
                  ? "Each box is a role; the line above it goes to who it reports to. Colours match the departments. A skipped role leaves the roles under it without a boss."
                  : "Each box is a department; the line above it goes to the department it reports into. Colours match the roles view."}
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
                      {section.departmentAnnualReturn !== null ? (
                        <p className="mb-2 text-xs text-gray-400">
                          {section.title} is expected to return {formatMoney(section.departmentAnnualReturn)} a year. Each KPI
                          below carries its share of that.
                        </p>
                      ) : null}
                      <div className="space-y-2">
                        {section.kpis.map(function (kpi) {
                          return renderKpi(kpi, section.title, section.departmentAnnualReturn);
                        })}
                      </div>
                    </div>
                  );
                })}
                <p className="text-xs text-gray-500">
                  A KPI&apos;s share of score is how much it counts toward its department&apos;s score (a department&apos;s
                  KPIs add up to 100%). Targets are a starting point: you can change any of these later in KPIs.
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
            onClick={function () { router.push("/onboarding/invite-team"); }}
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
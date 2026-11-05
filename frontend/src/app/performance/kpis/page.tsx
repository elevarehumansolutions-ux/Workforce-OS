"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import AppShell from "@/components/AppShell";
import { errorMessage, isHr, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import {
  createKpi,
  deleteKpi,
  loadDepartmentReturn,
  loadKpisOfDepartment,
  loadLatestScore,
  loadTaskProgress,
  recordResult,
  updateKpi,
  weightTotal,
} from "@/lib/kpis";
import type { DepartmentReturn, KpiForm, KpiFull } from "@/lib/kpis";
import { formatMoney } from "@/lib/blueprint";

const INPUT = "w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-white outline-none focus:border-indigo-400";
const BUTTON = "rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-50";
const GHOST = "rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/5";

const EMPTY_FORM: KpiForm = { name: "", weight: "", target: "", unit: "", isInverse: false, trackingMode: "manual" };

function formFromKpi(k: KpiFull): KpiForm {
  return {
    name: k.name,
    weight: String(Number(k.weight)),
    target: k.target_value === null ? "" : String(Number(k.target_value)),
    unit: k.unit === null ? "" : k.unit,
    isInverse: k.is_inverse,
    trackingMode: k.tracking_mode,
  };
}

// ---- the add / edit form (same fields for both)

function KpiFormFields(props: {
  initial: KpiForm;
  submitLabel: string;
  onSubmit: (form: KpiForm) => Promise<void>;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState<KpiForm>(props.initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.name.trim() === "") {
      setError("Give the KPI a name.");
      return;
    }
    const weight = Number(form.weight);
    if (form.weight === "" || isNaN(weight) || weight <= 0 || weight > 100) {
      setError("The weight must be a number between 1 and 100.");
      return;
    }
    if (form.target.trim() !== "" && isNaN(Number(form.target))) {
      setError("The target must be a number.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await props.onSubmit(form);
      setForm(props.initial);
    } catch (err) {
      // Includes the server's "weights must not exceed 100%" message.
      setError(errorMessage(err, "Could not save the KPI."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <input className={INPUT} placeholder="KPI name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className={INPUT} placeholder="Weight (% of department)" value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} />
        <input className={INPUT} placeholder="Target (optional)" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} />
        <input className={INPUT} placeholder="Unit, e.g. deals (optional)" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
        <select className={INPUT} value={form.trackingMode} onChange={(e) => setForm({ ...form, trackingMode: e.target.value as "manual" | "task_count" })}>
          <option value="manual">Result typed in by HR or an executive</option>
          <option value="task_count">Counted from completed tasks</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input type="checkbox" checked={form.isInverse} onChange={(e) => setForm({ ...form, isInverse: e.target.checked })} />
          Lower is better (e.g. complaints)
        </label>
      </div>
      {error ? <p className="text-xs text-red-300">{error}</p> : null}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className={BUTTON}>{props.submitLabel}</button>
        {props.onCancel ? <button type="button" onClick={props.onCancel} className={GHOST}>Cancel</button> : null}
      </div>
    </form>
  );
}

// ---- where the KPI stands now: counted tasks, or the last typed-in result

function KpiStanding(props: { kpi: KpiFull; reloadKey: number }) {
  const k = props.kpi;
  const unit = k.unit ? " " + k.unit : "";

  const progress = useLoad(
    "progress|" + k.id + "|" + props.reloadKey,
    function () {
      if (k.tracking_mode !== "task_count") return Promise.resolve(null);
      return loadTaskProgress(k.id);
    },
    "Could not load progress."
  );
  const latest = useLoad(
    "latest|" + k.id + "|" + props.reloadKey,
    function () {
      if (k.tracking_mode !== "manual") return Promise.resolve(null);
      return loadLatestScore(k.id);
    },
    "Could not load the latest result."
  );

  if (k.tracking_mode === "task_count") {
    if (!progress.data) return <p className="text-xs text-gray-500">{progress.error || "Loading…"}</p>;
    return (
      <p className="text-xs text-gray-300">
        {progress.data.completed_tasks} tasks completed this quarter
        {progress.data.score_percentage !== null ? " (" + Number(progress.data.score_percentage).toFixed(0) + "% of target)" : ""}
      </p>
    );
  }
  if (!latest.data) return <p className="text-xs text-gray-500">{latest.error || (latest.loading ? "Loading…" : "No result recorded yet.")}</p>;
  return (
    <p className="text-xs text-gray-300">
      Latest result: {Number(latest.data.actual_value)}{unit}
      {latest.data.score_percentage !== null ? " (" + Number(latest.data.score_percentage).toFixed(0) + "% of target)" : ""}
    </p>
  );
}

// ---- type in this quarter's result (manual KPIs; HR or executive)

function RecordResult(props: { kpi: KpiFull; onSaved: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (value.trim() === "" || isNaN(Number(value))) {
      setError("Type a number.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await recordResult(props.kpi.id, props.kpi.department_id, value.trim());
      setValue("");
      props.onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the result."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="mt-2 flex flex-wrap items-center gap-2">
      <input className={INPUT + " w-40"} placeholder="This quarter's result" value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="submit" disabled={busy} className={GHOST}>Save result</button>
      {error ? <span className="text-xs text-red-300">{error}</span> : null}
    </form>
  );
}

// ---- delete a KPI: the weights of the KPIs that stay must still total 100

function DeleteKpiPanel(props: { kpi: KpiFull; siblings: KpiFull[]; onDone: () => void; onCancel: () => void }) {
  // Only KPIs in the same weight group (same location) take part.
  const staying = props.siblings.filter(function (s) {
    return s.id !== props.kpi.id && s.location_id === props.kpi.location_id;
  });
  const startWeights: Record<string, string> = {};
  for (const s of staying) {
    startWeights[s.id] = String(Number(s.weight));
  }
  const [weights, setWeights] = useState<Record<string, string>>(startWeights);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  let total = 0;
  for (const s of staying) {
    total = total + Number(weights[s.id]);
  }
  // Round to avoid 99.99999 from decimal typing.
  const totalIsHundred = staying.length > 0 && Math.round(total * 100) === 10000;

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await deleteKpi(props.kpi.department_id, props.kpi.location_id, staying, weights);
      props.onDone();
    } catch (err) {
      setError(errorMessage(err, "Could not delete the KPI."));
    } finally {
      setBusy(false);
    }
  }

  if (staying.length === 0) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        <p>A department&apos;s KPI weights must total 100%, so the last KPI can&apos;t be deleted. Add the replacement first, then delete this one.</p>
        <button onClick={props.onCancel} className={GHOST + " mt-3"}>Close</button>
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4">
      <p className="text-sm text-red-100">
        Delete <strong>{props.kpi.name}</strong>? Its past scores stay on record. Share its weight among the others so they total 100%:
      </p>
      {staying.map(function (s) {
        return (
          <div key={s.id} className="flex items-center gap-3">
            <span className="flex-1 text-sm text-gray-200">{s.name}</span>
            <input
              className={INPUT + " w-24"}
              value={weights[s.id]}
              onChange={(e) => setWeights({ ...weights, [s.id]: e.target.value })}
            />
            <span className="text-xs text-gray-400">%</span>
          </div>
        );
      })}
      <p className={"text-sm " + (totalIsHundred ? "text-emerald-300" : "text-amber-300")}>Total: {total}% {totalIsHundred ? "" : "(must be exactly 100)"}</p>
      {error ? <p className="text-xs text-red-300">{error}</p> : null}
      <div className="flex gap-2">
        <button onClick={confirm} disabled={!totalIsHundred || busy} className="rounded-lg bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-40">
          Delete KPI
        </button>
        <button onClick={props.onCancel} className={GHOST}>Cancel</button>
      </div>
    </div>
  );
}

// ---- one KPI row

function KpiRow(props: {
  kpi: KpiFull;
  siblings: KpiFull[];
  // The department's expected yearly return, or null when not known.
  departmentReturn: number | null;
  canEdit: boolean;
  canRecord: boolean;
  reloadKey: number;
  onChanged: () => void;
}) {
  const k = props.kpi;
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (deleting) {
    return (
      <DeleteKpiPanel
        kpi={k}
        siblings={props.siblings}
        onDone={function () {
          setDeleting(false);
          props.onChanged();
        }}
        onCancel={() => setDeleting(false)}
      />
    );
  }

  if (editing) {
    return (
      <div className="rounded-xl border border-indigo-500/30 bg-[#0d1220]/80 p-4">
        <KpiFormFields
          initial={formFromKpi(k)}
          submitLabel="Save changes"
          onSubmit={async function (form) {
            await updateKpi(k.id, form);
            setEditing(false);
            props.onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }

  const target = k.target_value !== null ? Number(k.target_value) + (k.unit ? " " + k.unit : "") : "Not set";
  const kpiReturn = props.departmentReturn !== null ? (props.departmentReturn * Number(k.weight)) / 100 : null;
  const label = "text-[11px] uppercase tracking-wide text-gray-500";
  return (
    <div className="rounded-xl border border-white/10 bg-[#0d1220]/80 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{k.name}</p>
          {k.description ? <p className="mt-0.5 text-xs text-gray-400">{k.description}</p> : null}
        </div>
        {props.canEdit ? (
          <div className="flex gap-2">
            <button onClick={() => setEditing(true)} className={GHOST}>Edit</button>
            <button onClick={() => setDeleting(true)} className={GHOST + " text-red-300"}>Delete</button>
          </div>
        ) : null}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <p className={label}>Share of score</p>
          <p className="text-sm text-gray-200">{Number(k.weight)}%</p>
        </div>
        <div>
          <p className={label}>Target</p>
          <p className="text-sm text-gray-200">{target}</p>
        </div>
        <div>
          <p className={label}>What is good</p>
          <p className="text-xs text-gray-300">
            {k.is_inverse ? "A lower result is better (for example fewer days, fewer complaints)" : "A higher result is better"}
          </p>
        </div>
        <div>
          <p className={label}>Expected contribution</p>
          {kpiReturn !== null ? (
            <p className="text-sm text-gray-200">
              {formatMoney(kpiReturn)}
              <span className="text-xs text-gray-500"> a year</span>
            </p>
          ) : (
            <p className="text-xs text-gray-500">Shown once the department has a capital share</p>
          )}
        </div>
        <div>
          <p className={label}>How it is measured</p>
          <p className="text-xs text-gray-300">
            {k.tracking_mode === "task_count" ? "Counted from completed tasks" : "Result typed in each quarter"}
          </p>
        </div>
      </div>
      <div className="mt-3">
        <KpiStanding kpi={k} reloadKey={props.reloadKey} />
      </div>
      {props.canRecord && k.tracking_mode === "manual" ? <RecordResult kpi={k} onSaved={props.onChanged} /> : null}
    </div>
  );
}

// ---- the page

function departmentChoices(ctx: CallerContext) {
  return ctx.departments;
}

export default function KpisPage() {
  const [chosen, setChosen] = useState("");
  const [reloads, setReloads] = useState(0);
  const [adding, setAdding] = useState(false);
  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const ctx = caller.data;

  // Default to the caller's own department, else the first one.
  let departmentId = chosen;
  if (departmentId === "" && ctx) {
    if (ctx.employeeDepartmentId) departmentId = ctx.employeeDepartmentId;
    else if (ctx.departments.length > 0) departmentId = ctx.departments[0].id;
  }

  const kpis = useLoad<KpiFull[]>(
    "kpis|" + departmentId + "|" + reloads,
    function () {
      if (departmentId === "") return Promise.resolve([]);
      return loadKpisOfDepartment(departmentId);
    },
    "Could not load the KPIs."
  );

  const departmentReturn = useLoad<DepartmentReturn | null>(
    "return|" + departmentId,
    function () {
      if (departmentId === "") return Promise.resolve(null);
      return loadDepartmentReturn(departmentId);
    },
    "Could not load the department's expected return."
  );
  const annualReturn = departmentReturn.data ? departmentReturn.data.annualReturn : null;

  const canEdit = ctx ? isHr(ctx) : false;
  const canRecord = ctx ? isHr(ctx) || ctx.role === "business_executive" : false;
  const list = kpis.data ? kpis.data : [];
  const total = weightTotal(list);

  function reload() {
    setReloads(reloads + 1);
  }

  return (
    <AppShell
      activeLabel="KPIs"
      title="KPIs"
      breadcrumb="Dashboard > Performance > KPIs"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
    >
      <div className="flex flex-wrap items-center gap-3">
        <select className={INPUT + " w-64"} value={departmentId} onChange={(e) => setChosen(e.target.value)}>
          {ctx
            ? departmentChoices(ctx).map(function (d) {
                return <option key={d.id} value={d.id}>{d.name}</option>;
              })
            : null}
        </select>
        <p className="text-sm text-gray-400">
          Weights used: {total} of 100%{total < 100 && list.length > 0 ? " (" + (100 - total) + "% still free)" : ""}
        </p>
        {canEdit && departmentId !== "" ? (
          <button onClick={() => setAdding(!adding)} className={BUTTON + " ml-auto"}>{adding ? "Close" : "+ Add KPI"}</button>
        ) : null}
      </div>

      {departmentReturn.data ? (
        <div className="rounded-xl border border-white/10 bg-[#0d1220]/80 p-4 text-sm">
          {departmentReturn.data.sharePct === null ? (
            <p className="text-gray-400">
              This department has no share of the capital investment yet, so no expected return is set.
            </p>
          ) : (
            <p className="text-gray-200">
              Revenue target:{" "}
              <span className="font-semibold text-white">{Number(departmentReturn.data.sharePct)}% of capital</span>
              {annualReturn !== null ? (
                <span>
                  {" "}= <span className="font-semibold text-white">{formatMoney(annualReturn)}</span> a year (
                  {formatMoney(annualReturn / 4)} each quarter)
                  {departmentReturn.data.annualProfit !== null && departmentReturn.data.marginPct !== null ? (
                    <span>
                      , with an estimated profit of{" "}
                      <span className="font-semibold text-emerald-300">{formatMoney(departmentReturn.data.annualProfit)}</span> (
                      {Number(departmentReturn.data.marginPct)}% margin)
                    </span>
                  ) : null}
                  . Each KPI below carries its weight&apos;s share of it.
                </span>
              ) : (
                <span className="text-gray-400"> (the naira amount shows once a capital investment is set in Business DNA)</span>
              )}
            </p>
          )}
        </div>
      ) : null}

      {adding ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <KpiFormFields
            initial={EMPTY_FORM}
            submitLabel="Add KPI"
            onSubmit={async function (form) {
              await createKpi(departmentId, form);
              setAdding(false);
              reload();
            }}
          />
        </div>
      ) : null}

      {kpis.loading ? <p className="text-sm text-gray-400">Loading KPIs…</p> : null}
      {kpis.error ? <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{kpis.error}</p> : null}
      {kpis.data && list.length === 0 ? (
        <p className="rounded-xl border border-white/10 p-6 text-center text-sm text-gray-400">This department has no KPIs yet.</p>
      ) : null}

      <div className="space-y-3">
        {list.map(function (k) {
          return <KpiRow key={k.id + reloads} kpi={k} siblings={list} departmentReturn={annualReturn} canEdit={canEdit} canRecord={canRecord} reloadKey={reloads} onChanged={reload} />;
        })}
      </div>
    </AppShell>
  );
}

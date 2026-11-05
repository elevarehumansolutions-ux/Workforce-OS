"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import AppShell from "@/components/AppShell";
import { departmentName, errorMessage, isHr, loadCaller, roleLabel } from "@/lib/tasks";
import type { CallerContext } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import {
  addKeyResult,
  addObjective,
  deleteKeyResult,
  deleteObjective,
  editKeyResult,
  loadObjectives,
  renameObjective,
} from "@/lib/strategy";
import type { KeyResult, Objective } from "@/lib/strategy";

const INPUT = "w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-white outline-none focus:border-indigo-400";
const BUTTON = "rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-50";
const GHOST = "rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/5";

// ---- "Delete?" with a confirm step; shows the server's reason if it refuses

function DeleteControl(props: { what: string; onDelete: () => Promise<void>; onDone: () => void }) {
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await props.onDelete();
      props.onDone();
    } catch (err) {
      setError(errorMessage(err, "Could not delete."));
    } finally {
      setBusy(false);
    }
  }

  if (!asking) {
    return <button onClick={() => setAsking(true)} className={GHOST + " text-red-300"}>Delete</button>;
  }
  return (
    <div className="space-y-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3">
      <p className="text-xs text-red-100">Delete this {props.what}?</p>
      {error ? <p className="text-xs text-red-300">{error}</p> : null}
      <div className="flex gap-2">
        <button onClick={confirm} disabled={busy} className="rounded-lg bg-red-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-50">
          Yes, delete
        </button>
        <button onClick={() => { setAsking(false); setError(""); }} className={GHOST}>Keep it</button>
      </div>
    </div>
  );
}

// ---- one key result: shows its text and date, HR can edit it in place

function KeyResultRow(props: { keyResult: KeyResult; canEdit: boolean; onChanged: () => void }) {
  const kr = props.keyResult;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(kr.description);
  const [date, setDate] = useState(kr.target_date ? kr.target_date : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (text.trim() === "") {
      setError("A key result needs a description.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await editKeyResult(kr.id, text.trim(), date === "" ? null : date);
      setEditing(false);
      props.onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not save the key result."));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <form onSubmit={save} className="space-y-2 rounded-lg bg-white/5 p-3">
        <input className={INPUT} value={text} onChange={(e) => setText(e.target.value)} />
        <input type="date" className={INPUT} value={date} onChange={(e) => setDate(e.target.value)} />
        {error ? <p className="text-xs text-red-300">{error}</p> : null}
        <div className="flex gap-2">
          <button type="submit" disabled={busy} className={BUTTON}>Save</button>
          <button type="button" onClick={() => setEditing(false)} className={GHOST}>Cancel</button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex items-start justify-between gap-3 rounded-lg bg-white/5 px-3 py-2">
      <div>
        <p className="text-sm text-gray-200">{kr.description}</p>
        {kr.target_date ? <p className="text-xs text-gray-500">Target date: {kr.target_date}</p> : null}
      </div>
      {props.canEdit ? (
        <div className="flex items-start gap-2">
          <button onClick={() => setEditing(true)} className={GHOST}>Edit</button>
          <DeleteControl what="key result" onDelete={() => deleteKeyResult(kr.id)} onDone={props.onChanged} />
        </div>
      ) : null}
    </div>
  );
}

// ---- one objective with its key results

function ObjectiveCard(props: { objective: Objective; canEdit: boolean; onChanged: () => void }) {
  const o = props.objective;
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(o.title);
  const [adding, setAdding] = useState(false);
  const [newText, setNewText] = useState("");
  const [newDate, setNewDate] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function saveTitle(e: FormEvent) {
    e.preventDefault();
    if (title.trim() === "") {
      setError("An objective needs a title.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await renameObjective(o.id, title.trim());
      setRenaming(false);
      props.onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not save the title."));
    } finally {
      setBusy(false);
    }
  }

  async function saveNewKeyResult(e: FormEvent) {
    e.preventDefault();
    if (newText.trim() === "") {
      setError("A key result needs a description.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await addKeyResult(o.id, newText.trim(), newDate === "" ? null : newDate);
      setNewText("");
      setNewDate("");
      setAdding(false);
      props.onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not add the key result."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
      {renaming ? (
        <form onSubmit={saveTitle} className="flex flex-wrap gap-2">
          <input className={INPUT + " flex-1"} value={title} onChange={(e) => setTitle(e.target.value)} />
          <button type="submit" disabled={busy} className={BUTTON}>Save</button>
          <button type="button" onClick={() => setRenaming(false)} className={GHOST}>Cancel</button>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-white">{o.title}</h3>
          {props.canEdit ? (
            <div className="flex items-start gap-2">
              <button onClick={() => setRenaming(true)} className={GHOST}>Rename</button>
              <DeleteControl what="objective and all its key results" onDelete={() => deleteObjective(o.id)} onDone={props.onChanged} />
            </div>
          ) : null}
        </div>
      )}

      <div className="mt-3 space-y-2">
        {o.keyResults.length === 0 ? <p className="text-sm text-gray-500">No key results yet.</p> : null}
        {o.keyResults.map(function (kr) {
          return <KeyResultRow key={kr.id} keyResult={kr} canEdit={props.canEdit} onChanged={props.onChanged} />;
        })}
      </div>

      {props.canEdit ? (
        adding ? (
          <form onSubmit={saveNewKeyResult} className="mt-3 space-y-2">
            <input className={INPUT} placeholder="What result will show this objective is met?" value={newText} onChange={(e) => setNewText(e.target.value)} />
            <input type="date" className={INPUT} value={newDate} onChange={(e) => setNewDate(e.target.value)} />
            <div className="flex gap-2">
              <button type="submit" disabled={busy} className={BUTTON}>Add key result</button>
              <button type="button" onClick={() => setAdding(false)} className={GHOST}>Cancel</button>
            </div>
          </form>
        ) : (
          <button onClick={() => setAdding(true)} className={GHOST + " mt-3"}>+ Add key result</button>
        )
      ) : null}
      {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
    </div>
  );
}

// ---- HR only: add a new objective

function AddObjectiveForm(props: { ctx: CallerContext; onAdded: () => void }) {
  const [title, setTitle] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (title.trim() === "") {
      setError("Give the objective a title.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await addObjective(title.trim(), departmentId === "" ? null : departmentId);
      setTitle("");
      props.onAdded();
    } catch (err) {
      setError(errorMessage(err, "Could not add the objective."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-wrap items-start gap-2 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
      <input className={INPUT + " min-w-[16rem] flex-1"} placeholder="New objective" value={title} onChange={(e) => setTitle(e.target.value)} />
      <select className={INPUT + " w-56"} value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
        <option value="">Company-wide</option>
        {props.ctx.departments.map(function (d) {
          return <option key={d.id} value={d.id}>{d.name}</option>;
        })}
      </select>
      <button type="submit" disabled={busy} className={BUTTON}>Add objective</button>
      {error ? <p className="w-full text-xs text-red-300">{error}</p> : null}
    </form>
  );
}

// ---- the page

export default function StrategyPage() {
  const [reloads, setReloads] = useState(0);
  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const list = useLoad<Objective[]>("okrs|" + reloads, loadObjectives, "Could not load the objectives.");

  const ctx = caller.data;
  const canEdit = ctx ? isHr(ctx) : false;

  function reload() {
    setReloads(reloads + 1);
  }

  // Company-wide objectives first, then one group per department.
  const companyWide: Objective[] = [];
  const byDepartment: { id: string; items: Objective[] }[] = [];
  if (list.data) {
    for (const o of list.data) {
      if (o.department_id === null) {
        companyWide.push(o);
        continue;
      }
      let group = byDepartment.find((g) => g.id === o.department_id);
      if (!group) {
        group = { id: o.department_id, items: [] };
        byDepartment.push(group);
      }
      group.items.push(o);
    }
  }

  function renderGroup(heading: string, items: Objective[]) {
    return (
      <section key={heading} className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">{heading}</h2>
        {items.map(function (o) {
          return <ObjectiveCard key={o.id + o.title} objective={o} canEdit={canEdit} onChanged={reload} />;
        })}
      </section>
    );
  }

  return (
    <AppShell
      activeLabel="Strategy"
      title="Strategy: objectives and key results"
      breadcrumb="Dashboard > Strategy"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
    >
      {ctx && canEdit ? <AddObjectiveForm ctx={ctx} onAdded={reload} /> : null}

      {list.loading ? <p className="text-sm text-gray-400">Loading objectives…</p> : null}
      {list.error ? <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{list.error}</p> : null}
      {list.data && list.data.length === 0 ? (
        <p className="rounded-xl border border-white/10 p-6 text-center text-sm text-gray-400">
          No objectives yet.{canEdit ? " Add the first one above." : " HR will add them."}
        </p>
      ) : null}

      {companyWide.length > 0 ? renderGroup("Company-wide", companyWide) : null}
      {ctx
        ? byDepartment.map(function (g) {
            return renderGroup(departmentName(ctx, g.id), g.items);
          })
        : null}
    </AppShell>
  );
}

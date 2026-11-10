"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { errorMessage } from "@/lib/tasks";
import { approveBlueprintItem } from "@/lib/blueprint";
import { addKeyResult, addObjective, loadObjectives } from "@/lib/strategy";
import type { Objective } from "@/lib/strategy";
import { useLoad } from "@/lib/useLoad";

// "Your own objectives": objectives and key results the company writes itself, next to the ones
// suggested in the plan. They are saved straight away (no approve step: you wrote them). The
// objectives that came from the plan are left out here, because the plan already shows them.
export default function OwnObjectives(props: {
  // Departments an objective can belong to. One with a `pendingItemId` is only SUGGESTED in the
  // plan so far (not a real department yet): choosing it adds that department first.
  departments: { id: string; name: string; pendingItemId?: string }[];
  // Ids of the real objectives that came from the plan, so they are not listed twice.
  planObjectiveIds: string[];
  // Called after a suggested department was added, so the plan can reload.
  onDepartmentAdded: () => void;
}) {
  const [reloads, setReloads] = useState(0);
  const [title, setTitle] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The objective that currently has its "add a key result" form open.
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [krText, setKrText] = useState("");
  const [krDate, setKrDate] = useState("");

  const objectives = useLoad<Objective[]>("own-objectives|" + reloads, loadObjectives, "Couldn't load your objectives.");
  const own = (objectives.data || []).filter(function (o) {
    return props.planObjectiveIds.indexOf(o.id) === -1;
  });

  function scopeOf(o: Objective): string {
    if (o.department_id === null) return "Company-wide";
    const d = props.departments.find(function (x) { return x.id === o.department_id; });
    return d ? d.name : "Department";
  }

  async function saveObjective(e: FormEvent) {
    e.preventDefault();
    if (title.trim() === "") {
      setError("Give the objective a title.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let realDepartmentId: string | null = departmentId === "" ? null : departmentId;
      const chosen = props.departments.find(function (d) { return d.id === departmentId; });
      if (chosen && chosen.pendingItemId) {
        // The department is only suggested so far: add it, then use the real one.
        const added = await approveBlueprintItem(chosen.pendingItemId);
        if (!added.created_entity_id) {
          setError("Couldn't add that department first. Try adding it from the Departments section.");
          return;
        }
        realDepartmentId = added.created_entity_id;
        props.onDepartmentAdded();
      }
      await addObjective(title.trim(), realDepartmentId);
      setTitle("");
      setReloads(reloads + 1);
    } catch (err) {
      setError(errorMessage(err, "Couldn't add the objective."));
    } finally {
      setBusy(false);
    }
  }

  async function saveKeyResult(e: FormEvent, objectiveId: string) {
    e.preventDefault();
    if (krText.trim() === "") {
      setError("Describe the key result: what result will show the objective is met?");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await addKeyResult(objectiveId, krText.trim(), krDate === "" ? null : krDate);
      setKrText("");
      setKrDate("");
      setAddingTo(null);
      setReloads(reloads + 1);
    } catch (err) {
      setError(errorMessage(err, "Couldn't add the key result."));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-white outline-none focus:border-indigo-400";

  return (
    <section className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-2xl">
      <p className="text-xs uppercase tracking-wide text-gray-500">Your own objectives</p>
      <p className="mt-1 text-sm text-gray-400">
        Write objectives and key results of your own, in addition to the ones above. They are saved as soon as you add them.
      </p>

      {error ? <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p> : null}
      {objectives.error ? <p className="mt-3 text-sm text-red-300">{objectives.error}</p> : null}

      {own.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {own.map(function (o) {
            const open = addingTo === o.id;
            return (
              <li key={o.id} className="rounded-lg border border-white/5 bg-[#0a0e1a] p-3">
                <p className="text-sm font-medium text-white">{o.title}</p>
                <p className="text-xs text-gray-500">{scopeOf(o)}</p>
                {o.keyResults.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {o.keyResults.map(function (kr) {
                      return (
                        <li key={kr.id} className="flex items-start gap-2 text-sm text-gray-300">
                          <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-500" />
                          <span>
                            {kr.description}
                            {kr.target_date ? <span className="text-xs text-gray-500"> · by {kr.target_date}</span> : null}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs text-gray-600">No key results yet.</p>
                )}

                {open ? (
                  <form onSubmit={function (e) { saveKeyResult(e, o.id); }} className="mt-3 space-y-2">
                    <input
                      className={input}
                      placeholder="Key result: what result shows this is met? e.g. 95% of deliveries on time"
                      value={krText}
                      onChange={function (e) { setKrText(e.target.value); }}
                    />
                    <input
                      type="date"
                      className={input + " [color-scheme:dark] sm:w-56"}
                      value={krDate}
                      onChange={function (e) { setKrDate(e.target.value); }}
                    />
                    <div className="flex gap-2">
                      <button type="submit" disabled={busy} className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50">
                        {busy ? "Adding…" : "Add key result"}
                      </button>
                      <button type="button" onClick={function () { setAddingTo(null); }} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-gray-300 hover:bg-white/5">
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={function () { setError(""); setAddingTo(o.id); }}
                    className="mt-2 text-xs font-medium text-indigo-400 hover:text-indigo-300"
                  >
                    + Add a key result
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}

      <form onSubmit={saveObjective} className="mt-4 flex flex-wrap items-start gap-2">
        <input
          className={input + " min-w-[16rem] flex-1"}
          placeholder="New objective, e.g. Win three new enterprise clients"
          value={title}
          onChange={function (e) { setTitle(e.target.value); }}
        />
        <select className={input + " w-56"} value={departmentId} onChange={function (e) { setDepartmentId(e.target.value); }}>
          <option value="">Company-wide</option>
          {props.departments.map(function (d) {
            return (
              <option key={d.id} value={d.id}>
                {d.pendingItemId ? d.name + " (suggested, will be added)" : d.name}
              </option>
            );
          })}
        </select>
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-50">
          {busy ? "Adding…" : "+ Add objective"}
        </button>
      </form>
    </section>
  );
}

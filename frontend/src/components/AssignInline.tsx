"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import PersonSelect from "@/components/PersonSelect";
import { activeEmployees, errorMessage, localInputToIso } from "@/lib/tasks";
import type { CallerContext, Task } from "@/lib/tasks";

interface AssignInlineProps {
  task: Task;
  ctx: CallerContext;
  // Called after the task was handed over, so the list can refresh.
  onAssigned: () => void;
}

// Hands an unassigned task to someone straight from the list: pick a person and press Assign.
// The server wants a deadline in the future with every assignment, so the task's own deadline is kept
// when it is still ahead; a deadline field only appears when there is none or it has passed.
export default function AssignInline({ task, ctx, onAssigned }: AssignInlineProps) {
  const [personId, setPersonId] = useState("");
  const [dueLocal, setDueLocal] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // "Now" is read once when the row appears (reading the clock while rendering is not allowed).
  const [openedAt] = useState(function () {
    return Date.now();
  });
  const deadlineStillAhead = task.due_at !== null && new Date(task.due_at).getTime() > openedAt;

  async function assign() {
    if (!personId) {
      setError("Choose who should do this task.");
      return;
    }
    let dueIso: string | null = null;
    if (deadlineStillAhead) {
      dueIso = task.due_at;
    } else {
      dueIso = localInputToIso(dueLocal);
      if (dueIso === null) {
        setError("Choose a deadline for this task.");
        return;
      }
    }
    setSaving(true);
    setError("");
    try {
      await apiFetch("/tasks/" + task.id + "/reassign", {
        method: "POST",
        body: { assigned_to_employee_id: personId, due_at: dueIso },
      });
      onAssigned();
    } catch (err) {
      setError(errorMessage(err, "Couldn't assign this task. Check your connection and try again."));
      setSaving(false);
    }
  }

  const fieldClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500";

  return (
    <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-white/10 pt-3">
      <div className="min-w-[14rem] flex-1">
        <label className="mb-1 block text-xs text-gray-500">Assign to</label>
        <PersonSelect
          people={activeEmployees(ctx)}
          positions={ctx.positions}
          departments={ctx.departments}
          value={personId}
          onChange={setPersonId}
          emptyLabel="Choose a person"
          className={fieldClass + " w-full"}
        />
      </div>
      {deadlineStillAhead ? null : (
        <div>
          <label className="mb-1 block text-xs text-gray-500">Deadline (required)</label>
          <input
            type="datetime-local"
            value={dueLocal}
            onChange={function (e) {
              setDueLocal(e.target.value);
            }}
            className={fieldClass}
          />
        </div>
      )}
      <button
        type="button"
        disabled={saving}
        onClick={assign}
        className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {saving ? "Assigning…" : "Assign"}
      </button>
      {error ? <p className="w-full text-xs text-red-300">{error}</p> : null}
      {deadlineStillAhead ? (
        <p className="w-full text-xs text-gray-500">The task keeps its deadline. The person is told straight away.</p>
      ) : null}
    </div>
  );
}

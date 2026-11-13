"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { fetchHistory, redoChange, undoChange } from "@/lib/blueprint";
import type { HistoryEntry } from "@/lib/blueprint";
import { formatDateTime } from "@/lib/tasks";

// The change history of the plan review (onboarding only): the latest change with Undo and Redo
// buttons always in view, and the last 20 changes one click away. The page passes a number that
// goes up after every change, so this list is read again, and a function to call after an undo
// or redo so the plan itself is read again too.
interface Props {
  reloadKey: number;
  onChanged: () => void | Promise<void>;
}

export default function PlanChanges(props: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(
    function () {
      let cancelled = false;
      fetchHistory()
        .then(function (list) {
          if (!cancelled) setEntries(list);
        })
        .catch(function () {
          // No history to show (for example this person may not review the plan): show nothing.
        });
      return function () {
        cancelled = true;
      };
    },
    [props.reloadKey]
  );

  async function run(action: () => Promise<HistoryEntry[]>) {
    setBusy(true);
    setError("");
    try {
      setEntries(await action());
      await props.onChanged();
    } catch (err) {
      // A 409 carries the reason in words ("Undo 'Added role X' first.").
      setError(err instanceof ApiError ? err.message : "Couldn't do that. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  if (entries.length === 0) return null;

  // "Undo last change" takes back the newest change that is still in place.
  const newestDone = entries.find(function (e) { return e.state === "done"; });
  const nextToRedo = entries.find(function (e) { return e.can_redo; });
  const latest = entries[0];

  const smallButton =
    "rounded-full border border-indigo-400/60 px-3 py-1 text-xs font-medium text-indigo-200 hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className="mt-4 rounded-xl border border-white/10 bg-[#0d1220]/80 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="min-w-0 text-sm text-gray-300">
          <span className="text-gray-500">{latest.state === "undone" ? "Undone: " : "Last change: "}</span>
          <span className="text-white">{latest.label}</span>
        </p>
        <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy || !newestDone}
            title={newestDone && !newestDone.can_undo && newestDone.reason ? newestDone.reason : undefined}
            onClick={function () { if (newestDone) run(function () { return undoChange(newestDone.id); }); }}
            className={smallButton}
          >
            Undo last change
          </button>
          {nextToRedo ? (
            <button
              type="button"
              disabled={busy}
              onClick={function () { run(function () { return redoChange(nextToRedo.id); }); }}
              className={smallButton}
            >
              Redo
            </button>
          ) : null}
          <button
            type="button"
            onClick={function () { setOpen(!open); }}
            className="text-xs font-medium text-gray-400 underline hover:text-gray-200"
          >
            {open ? "Hide changes" : "All changes (" + entries.length + ")"}
          </button>
        </div>
      </div>

      {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
      {newestDone && !newestDone.can_undo && newestDone.reason && !error ? (
        <p className="mt-2 text-xs text-gray-500">{newestDone.reason}</p>
      ) : null}

      {open ? (
        <ul className="mt-3 divide-y divide-white/5 border-t border-white/10">
          {entries.map(function (entry) {
            const undone = entry.state !== "done";
            return (
              <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className={"text-sm " + (undone ? "text-gray-500 line-through" : "text-gray-200")}>{entry.label}</p>
                  <p className="text-xs text-gray-600">
                    {formatDateTime(entry.created_at)}
                    {entry.state === "undone" ? " · undone" : ""}
                    {entry.state === "already_undone" ? " · undone from its card" : ""}
                    {entry.reason && entry.state !== "already_undone" ? " · " + entry.reason : ""}
                  </p>
                </div>
                {entry.can_undo ? (
                  <button type="button" disabled={busy} onClick={function () { run(function () { return undoChange(entry.id); }); }} className={smallButton}>
                    Undo
                  </button>
                ) : null}
                {entry.can_redo ? (
                  <button type="button" disabled={busy} onClick={function () { run(function () { return redoChange(entry.id); }); }} className={smallButton}>
                    Redo
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

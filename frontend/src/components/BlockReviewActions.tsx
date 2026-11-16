"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import ExtensionPicker from "@/components/ExtensionPicker";
import { effectiveDeadline, errorMessage, formatDateTime, formatDuration } from "@/lib/tasks";

interface BlockLike {
  id: string;
  blocked_at: string;
  unblocked_at: string | null;
  // What the person said they would need, if they said.
  estimated_seconds: number | null;
}

interface BlockReviewActionsProps {
  // Any block of the task that is waiting: the decision covers every waiting block of that task.
  block: BlockLike;
  taskDueAt: string | null;
  // Extra time already given on the task, to show the new deadline with the time about to be given.
  taskApprovedSeconds: number;
  // How many blocks of this task are waiting (to explain that one decision covers them all).
  waitingCount: number;
  // Called after a decision (or after finding out it was already made), so the screen can refresh.
  onDecided: () => void;
}

// Where the reviewer's box starts: what the person said they would need, otherwise the time the block has
// lasted so far, rounded up to a quarter of an hour (at least 15 minutes). The reviewer changes it freely.
function suggestedMinutes(block: BlockLike): number {
  if (block.estimated_seconds) return Math.max(1, Math.round(block.estimated_seconds / 60));
  const end = block.unblocked_at ? new Date(block.unblocked_at).getTime() : Date.now();
  const lived = Math.max(0, (end - new Date(block.blocked_at).getTime()) / 60000);
  return Math.max(15, Math.ceil(lived / 15) * 15);
}

// Approve (and choose the extra time) or reject a block that is waiting for a decision. Used on the task page and
// on the Blocks to review screen, so both work the same way.
export default function BlockReviewActions({ block, taskDueAt, taskApprovedSeconds, waitingCount, onDecided }: BlockReviewActionsProps) {
  const [open, setOpen] = useState(false);
  const [minutes, setMinutes] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function decide(decision: "approve" | "reject") {
    setError("");
    setBusy(true);
    try {
      // Approving takes the extra time the reviewer chose; rejecting takes nothing.
      const body = decision === "approve" ? { extension_minutes: minutes } : undefined;
      await apiFetch("/task-blocks/" + block.id + "/" + decision, { method: "POST", body: body });
      setOpen(false);
      onDecided();
    } catch (err) {
      if (err instanceof ApiError && err.code === "TASK_BLOCK_NOT_FOUND") {
        setError("That block wasn't found, or you may not review it.");
      } else if (err instanceof ApiError && err.code === "TASK_BLOCK_ALREADY_REVIEWED") {
        setError("This block has already been decided. The screen has been refreshed.");
        onDecided();
      } else {
        setError(errorMessage(err, "Couldn't save your decision. Check your connection and try again."));
      }
    } finally {
      setBusy(false);
    }
  }

  const currentDeadline = effectiveDeadline(taskDueAt, taskApprovedSeconds);
  const newDeadline = effectiveDeadline(taskDueAt, taskApprovedSeconds, minutes * 60);

  return (
    <div>
      {waitingCount > 1 ? (
        <p className="mb-3 text-xs text-amber-300">
          This task has {waitingCount} blocks waiting. Your decision covers all of them, and the extra time is given once.
        </p>
      ) : null}
      {error ? <p className="mb-3 text-sm text-red-300">{error}</p> : null}

      {open ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <p className="text-sm font-medium text-gray-100">How much extra time does this task get?</p>
          <p className="mt-1 text-xs text-gray-400">You decide, and it does not depend on how long the person stays blocked.</p>
          <div className="mt-3">
            <ExtensionPicker defaultMinutes={minutes} onChange={setMinutes} disabled={busy} />
          </div>
          {taskDueAt && newDeadline ? (
            <p className="mt-3 text-xs text-gray-300">
              {minutes > 0 ? (
                <>
                  New deadline: <span className="font-medium text-white">{formatDateTime(newDeadline.toISOString())}</span> (now{" "}
                  {formatDateTime(currentDeadline ? currentDeadline.toISOString() : null)})
                </>
              ) : (
                "Enter a whole number of minutes, hours or days (at least 1 minute, at most 30 days)."
              )}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy || minutes < 1 || minutes > 43200}
              onClick={function () {
                decide("approve");
              }}
              className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {minutes >= 1 ? "Approve and give " + formatDuration(minutes * 60) : "Approve"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={function () {
                setOpen(false);
              }}
              className="rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/5"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={function () {
              setMinutes(suggestedMinutes(block));
              setOpen(true);
            }}
            className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
          >
            Approve…
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={function () {
              decide("reject");
            }}
            className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

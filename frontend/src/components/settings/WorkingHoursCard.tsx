"use client";

import { useState } from "react";
import WorkingHoursFields from "@/components/WorkingHoursFields";
import { ApiError } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { describeWorkingHours, fetchWorkingHours, saveWorkingHours, workingHoursProblem } from "@/lib/workingHours";
import type { WorkingHours } from "@/lib/workingHours";

// The company's working week, in Settings. Everyone can read it; only HR administrators can change it.
export default function WorkingHoursCard({ canEdit }: { canEdit: boolean }) {
  const [reload, setReload] = useState(0);
  const state = useLoad<WorkingHours>("working-hours|" + reload, fetchWorkingHours, "Couldn't load the working hours.");
  // What the person has changed on screen but not saved yet; null means "show what is saved".
  const [edited, setEdited] = useState<{ start_hour: number; end_hour: number; work_days: number[] } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const week = edited ? edited : state.data ? state.data : null;

  async function save() {
    if (!edited) return;
    const problem = workingHoursProblem(edited);
    if (problem) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await saveWorkingHours(edited);
      setEdited(null);
      setSaved(true);
      setReload(reload + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the working hours. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-10 border-t border-white/10 pt-6">
      <h4 className="text-sm font-semibold text-white">Working hours</h4>
      <p className="mt-1 max-w-xl text-xs text-gray-400">
        Deadlines on workflow steps count only these hours and days, and a step of &quot;1 day&quot; is one full
        working day here. A change applies to deadlines worked out from now on; tasks that already have a deadline
        keep it. Public holidays and lunch or break times are not skipped (not built yet).
      </p>

      {state.error ? <p className="mt-3 text-xs text-red-300">{state.error}</p> : null}

      {week ? (
        <div className="mt-4 max-w-xl space-y-4">
          <WorkingHoursFields value={week} disabled={!canEdit || saving} onChange={setEdited} />
          <p className="text-xs text-gray-500">Now: {describeWorkingHours(week)}</p>
          {error ? <p className="text-xs text-red-300">{error}</p> : null}
          {saved ? <p className="text-xs text-emerald-300">Saved.</p> : null}
          {canEdit ? (
            <button
              type="button"
              disabled={saving || !edited}
              onClick={save}
              className="rounded-lg bg-indigo-500 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save working hours"}
            </button>
          ) : (
            <p className="text-xs text-gray-500">Only an HR administrator can change this.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

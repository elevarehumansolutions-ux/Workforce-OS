"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { FISCAL_YEAR_WARNING, saveFiscalYear } from "@/lib/fiscalYear";
import { MONTH_NAMES, SETTINGS_INPUT_CLASS, loadMe, monthName } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

// The month the financial year starts in, in Settings. Everyone sees it; only HR administrators change it.
// It loads its own value (not the page's copy of "me"), so it is right after a save and a tab switch.
export default function FiscalYearCard({ canEdit }: { canEdit: boolean }) {
  const [reload, setReload] = useState(0);
  const state = useLoad<number>(
    "fiscal-year|" + reload,
    function () {
      return loadMe().then(function (me) {
        return me.organization ? me.organization.fiscal_year_start_month : 1;
      });
    },
    "Couldn't load the financial year."
  );
  // The month the person picked but has not saved; null means "show what is saved".
  const [picked, setPicked] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const savedMonth = state.data;
  const shownMonth = picked !== null ? picked : savedMonth;

  async function save() {
    if (picked === null) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await saveFiscalYear(picked);
      setPicked(null);
      setSaved(true);
      setReload(reload + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the financial year. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-10 border-t border-white/10 pt-6">
      <h4 className="text-sm font-semibold text-white">Financial year</h4>
      <p className="mt-1 max-w-xl text-xs text-gray-400">{FISCAL_YEAR_WARNING}</p>

      {state.error ? <p className="mt-3 text-xs text-red-300">{state.error}</p> : null}

      {shownMonth !== null ? (
        <div className="mt-4 max-w-xl space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">Financial year starts in</label>
            <select
              value={shownMonth}
              disabled={!canEdit || saving}
              onChange={function (e) {
                const month = Number(e.target.value);
                setPicked(month === savedMonth ? null : month);
                setSaved(false);
              }}
              className={SETTINGS_INPUT_CLASS}
            >
              {MONTH_NAMES.map(function (name, index) {
                return (
                  <option key={name} value={index + 1}>
                    {name}
                  </option>
                );
              })}
            </select>
          </div>
          {savedMonth !== null ? <p className="text-xs text-gray-500">Now: {monthName(savedMonth)}</p> : null}
          {error ? <p className="text-xs text-red-300">{error}</p> : null}
          {saved ? <p className="text-xs text-emerald-300">Saved.</p> : null}
          {canEdit ? (
            <button
              type="button"
              disabled={saving || picked === null}
              onClick={save}
              className="rounded-lg bg-indigo-500 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save financial year"}
            </button>
          ) : (
            <p className="text-xs text-gray-500">Only an HR administrator can change this.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

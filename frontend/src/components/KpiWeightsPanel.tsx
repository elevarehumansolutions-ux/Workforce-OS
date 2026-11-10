"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loadKpisOfDepartment, updateKpiWeight, weightTotal } from "@/lib/kpis";
import { useLoad } from "@/lib/useLoad";
import { keepOnlyNumber } from "@/lib/numberInput";
import { errorMessage } from "@/lib/tasks";

// Shows the KPIs a department ALREADY has (added from the plan, or created by hand), with
// how much of its 100% they use, and lets the weight of each be changed right here.
// Without it, KPIs created on the KPIs screen were invisible in the wizard, and nothing said
// why a suggested KPI could not fit.
export default function KpiWeightsPanel(props: {
  departmentId: string;
  departmentName: string;
  // What the suggested KPIs still waiting for this department add up to, in percent.
  waitingTotal: number;
  // Change this number to make the panel load again (for example after something was added).
  reloadKey: number;
}) {
  const router = useRouter();
  const [version, setVersion] = useState(0);
  // What the owner has typed in each box, by KPI id. A box that was never touched is not here.
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loaded = useLoad(
    "weights|" + props.departmentId + "|" + props.reloadKey + "|" + version,
    function () { return loadKpisOfDepartment(props.departmentId); },
    "Could not load this department's KPIs."
  );

  if (loaded.error) return <p className="mb-2 text-xs text-red-300">{loaded.error}</p>;
  if (!loaded.data || loaded.data.length === 0) return null;
  const kpis = loaded.data;

  // Round to 2 places so typing 33.3 three times does not show 99.89999.
  const used = Math.round(weightTotal(kpis) * 100) / 100;
  const free = Math.round((100 - used) * 100) / 100;
  const overflow = props.waitingTotal > free;

  async function save(kpiId: string) {
    setSavingId(kpiId);
    setError("");
    try {
      await updateKpiWeight(kpiId, typed[kpiId]);
      const rest = { ...typed };
      delete rest[kpiId];
      setTyped(rest);
      setVersion(version + 1);
    } catch (err) {
      // Includes the server's "weights must not exceed 100%" message.
      setError(errorMessage(err, "Could not save that weight."));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="mb-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-3">
      <p className="text-xs font-semibold text-gray-200">
        Already in {props.departmentName}: {used}% of the 100% is used, {free}% is free
      </p>
      <div className="mt-2 space-y-1.5">
        {kpis.map(function (k) {
          const shown = typed[k.id] !== undefined ? typed[k.id] : String(Number(k.weight));
          const changed = typed[k.id] !== undefined && typed[k.id] !== String(Number(k.weight));
          return (
            <div key={k.id} className="flex items-center gap-2">
              <span className="flex-1 text-xs text-gray-300">{k.name}</span>
              <input
                className="w-20 rounded-lg border border-white/10 bg-[#111726] px-2 py-1 text-xs text-white outline-none focus:border-indigo-500"
                inputMode="decimal"
                value={shown}
                onChange={function (e) { setTyped({ ...typed, [k.id]: keepOnlyNumber(e.target.value) }); }}
              />
              <span className="text-xs text-gray-500">%</span>
              {changed ? (
                <button
                  type="button"
                  disabled={savingId === k.id || typed[k.id] === ""}
                  onClick={function () { save(k.id); }}
                  className="rounded-full bg-indigo-500 px-3 py-0.5 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
                >
                  {savingId === k.id ? "…" : "Save"}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
      {overflow ? (
        <p className="mt-2 text-xs text-amber-300">
          The suggestions below add up to {Math.round(props.waitingTotal * 100) / 100}%, but only {free}% is free. When you
          add them they are scaled down to fit. Lower a weight above if you want to give them more room.
        </p>
      ) : null}
      {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        onClick={function () { router.push("/performance/kpis"); }}
        className="mt-2 text-xs font-medium text-indigo-400 hover:text-indigo-300"
      >
        Delete or edit these on the KPIs screen
      </button>
    </div>
  );
}

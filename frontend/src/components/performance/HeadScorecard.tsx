"use client";

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { departmentPath, scoreClasses, scoreText } from "@/lib/performance";
import type { DepartmentPerformance, Period } from "@/lib/performance";

// A head usually hands the work to their people, so their own card can be empty even when the
// department is doing well or badly. This is the head's real scorecard: the department they head.
function OneDepartment(props: { departmentId: string; departmentName: string; period: Period }) {
  const load = useLoad<DepartmentPerformance>(
    "head|" + props.departmentId + "|" + props.period.start + "|" + props.period.end,
    function () {
      return apiFetch<DepartmentPerformance>(departmentPath(props.departmentId, props.period, 1), { method: "GET" });
    },
    "Could not load your department's results."
  );
  const data = load.data;

  return (
    <div className="mt-6 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-5">
      <p className="text-xs uppercase tracking-wide text-indigo-200">You head {props.departmentName}</p>
      <p className="mt-1 text-sm text-gray-300">
        When you hand work to your people it counts on their cards, not yours, so your scorecard is your department&apos;s results.
      </p>

      {load.loading ? <p className="mt-3 text-sm text-gray-400">Loading…</p> : null}
      {load.error ? <p className="mt-3 text-sm text-red-300">{load.error}</p> : null}

      {data ? (
        <div className="mt-3 flex flex-wrap items-end gap-8">
          <div>
            <p className="text-xs text-gray-500">Did it hit its goals?</p>
            <p className={"text-3xl font-bold " + scoreClasses(data.kpi_results_score)}>
              {data.kpi_results_score === null ? "—" : scoreText(data.kpi_results_score)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Do people deliver on time?</p>
            <p className={"text-3xl font-bold " + scoreClasses(data.punctuality_score)}>
              {data.punctuality_score === null ? "—" : scoreText(data.punctuality_score)}
            </p>
          </div>
          <Link href="/performance/department" className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
            Open {props.departmentName} performance
          </Link>
        </div>
      ) : null}
    </div>
  );
}

export default function HeadScorecard(props: { departments: { id: string; name: string }[]; period: Period }) {
  return (
    <div>
      {props.departments.map(function (d) {
        return <OneDepartment key={d.id} departmentId={d.id} departmentName={d.name} period={props.period} />;
      })}
    </div>
  );
}

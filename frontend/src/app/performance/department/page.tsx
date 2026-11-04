"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { CURRENT_QUARTER, departmentPath, departmentsICanOpen, scoreClasses, scoreText } from "@/lib/performance";
import type { DepartmentPerformance, Period } from "@/lib/performance";

export default function DepartmentPerformancePage() {
  const [chosenId, setChosenId] = useState("");
  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const ctx = caller.data;

  const options = ctx ? departmentsICanOpen(ctx) : [];
  // Until the person picks one, show the first department they may open.
  const departmentId = chosenId !== "" ? chosenId : options.length > 0 ? options[0].id : "";

  return (
    <AppShell
      activeLabel="Performance"
      title="Department performance"
      breadcrumb="Dashboard > Performance > Department"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/performance" className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
          My performance
        </Link>
      }
    >
      {caller.error ? (
        <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{caller.error}</p>
      ) : null}

      {ctx && options.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-300">
          Department performance is for HR, executives, and the heads and managers of a department. You can see your own
          score on <Link href="/performance" className="text-indigo-300 hover:underline">My performance</Link>.
        </div>
      ) : null}

      {ctx && options.length > 0 ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
          <select
            value={departmentId}
            onChange={function (e) {
              setChosenId(e.target.value);
            }}
            className="mb-5 rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white"
          >
            {options.map(function (d) {
              return (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              );
            })}
          </select>
          {/* key: choosing another department starts a fresh screen (page 1, current quarter). */}
          <DepartmentBody key={departmentId} departmentId={departmentId} />
        </div>
      ) : null}
    </AppShell>
  );
}

function DepartmentBody(props: { departmentId: string }) {
  const [period, setPeriod] = useState<Period>(CURRENT_QUARTER);
  const [page, setPage] = useState(1);

  const load = useLoad<DepartmentPerformance>(
    props.departmentId + "|" + period.start + "|" + period.end + "|" + page,
    function () {
      return apiFetch<DepartmentPerformance>(departmentPath(props.departmentId, period, page), { method: "GET" });
    },
    "Could not load this department."
  );
  const data = load.data;

  function changePeriod(next: Period) {
    setPeriod(next);
    setPage(1);
  }

  return (
    <div>
      <PeriodBar
        shownStart={data ? data.period_start : null}
        shownEnd={data ? data.period_end : null}
        asked={period}
        isFinal={data ? data.is_final : false}
        onChange={changePeriod}
      />

      {load.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}

      {!load.loading && load.status === 404 ? (
        <p className="mt-6 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-gray-300">
          This department isn&apos;t available to you.
        </p>
      ) : null}

      {!load.loading && load.error && load.status !== 404 ? (
        <p className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{load.error}</p>
      ) : null}

      {data ? (
        <div className="mt-6">
          <h2 className="text-lg font-semibold text-white">{data.department_name}</h2>

          {/* Two different questions, so two numbers; they are never blended into one. */}
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <p className="text-xs uppercase tracking-wide text-gray-500">Did it hit its goals?</p>
              <p className={"mt-2 text-4xl font-bold " + scoreClasses(data.kpi_results_score)}>
                {data.kpi_results_score === null ? "—" : scoreText(data.kpi_results_score)}
              </p>
              {data.kpi_results_score === null ? (
                <p className="mt-2 text-sm text-gray-400">No data yet. {data.kpi_results_no_data_reason}</p>
              ) : (
                <p className="mt-2 text-sm text-gray-400">
                  KPI results against target, {data.kpis_counted} of {data.kpis_expected} KPIs counted. Above 100 means
                  the team beat its target.
                </p>
              )}
            </div>

            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <p className="text-xs uppercase tracking-wide text-gray-500">Do people deliver on time?</p>
              <p className={"mt-2 text-4xl font-bold " + scoreClasses(data.punctuality_score)}>
                {data.punctuality_score === null ? "—" : scoreText(data.punctuality_score)}
              </p>
              {data.punctuality_score === null ? (
                <p className="mt-2 text-sm text-gray-400">No data yet. {data.punctuality_no_data_reason}</p>
              ) : (
                <p className="mt-2 text-sm text-gray-400">
                  {data.punctuality_on_time} on time, {data.punctuality_late} late, {data.punctuality_not_done} not done
                  (all the department&apos;s tasks, including ones nobody holds).
                </p>
              )}
            </div>
          </div>

          <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">People</h3>
          {data.people.length === 0 ? (
            <p className="mt-3 text-sm text-gray-400">No people to show on this page.</p>
          ) : (
            <table className="mt-3 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Overall score</th>
                  <th className="py-2 font-medium">KPIs counted</th>
                </tr>
              </thead>
              <tbody>
                {data.people.map(function (person) {
                  return (
                    <tr key={person.employee_id} className="border-b border-white/5">
                      <td className="py-3 pr-4">
                        <Link href={"/performance/person/" + person.employee_id} className="text-white hover:text-indigo-300 hover:underline">
                          {person.employee_name}
                        </Link>
                      </td>
                      <td className={"py-3 pr-4 font-semibold " + scoreClasses(person.overall_score)}>
                        {scoreText(person.overall_score)}
                      </td>
                      <td className="py-3 text-gray-400">
                        {person.kpis_counted} of {person.kpis_expected}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {data.people_pagination.total_pages > 1 ? (
            <div className="mt-4 flex items-center gap-3 text-sm text-gray-400">
              <button
                type="button"
                disabled={!data.people_pagination.has_previous}
                onClick={function () {
                  setPage(page - 1);
                }}
                className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span>
                Page {data.people_pagination.page} of {data.people_pagination.total_pages}
              </span>
              <button
                type="button"
                disabled={!data.people_pagination.has_next}
                onClick={function () {
                  setPage(page + 1);
                }}
                className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { CURRENT_QUARTER, companyPath, scoreClasses, scoreText } from "@/lib/performance";
import type { CompanyPerformance, CompanyTrendPoint, Period } from "@/lib/performance";

function quarterLabel(startIso: string): string {
  return new Date(startIso + "T00:00:00Z").toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

// A bar for each saved quarter, as tall as its score (capped at the box so a score
// above 100 does not overflow). A quarter with no data shows "No data", never an empty bar read as 0.
function TrendBars(props: { points: CompanyTrendPoint[] }) {
  return (
    <div className="mt-3 grid grid-cols-4 gap-4">
      {props.points.map(function (point) {
        const hasScore = point.headline_score !== null;
        const height = hasScore ? Math.min(100, Math.max(4, Number(point.headline_score))) : 0;
        return (
          <div key={point.period_start} className="text-center">
            <div className="flex h-28 items-end justify-center rounded-lg bg-white/5">
              {hasScore ? (
                <div className="w-1/2 rounded-t bg-indigo-500" style={{ height: height + "%" }} />
              ) : (
                <span className="mb-10 text-xs text-gray-500">No data</span>
              )}
            </div>
            <p className={"mt-2 text-sm font-semibold " + scoreClasses(point.headline_score)}>
              {hasScore ? scoreText(point.headline_score) : "—"}
            </p>
            <p className="text-xs text-gray-500">{quarterLabel(point.period_start)}</p>
          </div>
        );
      })}
    </div>
  );
}

export default function CompanyPerformancePage() {
  const [period, setPeriod] = useState<Period>(CURRENT_QUARTER);

  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const load = useLoad<CompanyPerformance>(
    "company|" + period.start + "|" + period.end,
    function () {
      return apiFetch<CompanyPerformance>(companyPath(period), { method: "GET" });
    },
    "Could not load the company performance."
  );

  const ctx = caller.data;
  const data = load.data;

  return (
    <AppShell
      activeLabel="Performance"
      title="Company performance"
      breadcrumb="Dashboard > Performance > Company"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/performance" className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
          My performance
        </Link>
      }
    >
      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <PeriodBar
          shownStart={data ? data.period_start : null}
          shownEnd={data ? data.period_end : null}
          asked={period}
          isFinal={data ? data.is_final : false}
          onChange={setPeriod}
        />

        {load.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}

        {!load.loading && load.status === 404 ? (
          <p className="mt-6 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-gray-300">
            Company performance is for HR administrators and executives. Heads and managers can open their department
            from <Link href="/performance" className="text-indigo-300 hover:underline">My performance</Link>.
          </p>
        ) : null}

        {!load.loading && load.error && load.status !== 404 ? (
          <p className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{load.error}</p>
        ) : null}

        {data ? (
          <div className="mt-6">
            {/* Two different questions, so two numbers; they are never blended into one. */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/5 p-5">
                <p className="text-xs uppercase tracking-wide text-gray-500">Company Performance Score</p>
                <p className={"mt-2 text-5xl font-bold " + scoreClasses(data.headline_score)}>
                  {data.headline_score === null ? "—" : scoreText(data.headline_score)}
                </p>
                {data.headline_score === null ? (
                  <p className="mt-2 text-sm text-gray-400">No data yet. {data.headline_no_data_reason}</p>
                ) : (
                  <p className="mt-2 text-sm text-gray-400">
                    {data.departments_counted} of {data.departments_expected} departments counted.{" "}
                    {data.headline_is_plain_average
                      ? "No department has a revenue share yet, so this is a plain average."
                      : "Each department counts in proportion to its revenue share; a department with no share or no result is left out."}
                  </p>
                )}
              </div>

              <div className="rounded-xl border border-white/10 bg-white/5 p-5">
                <p className="text-xs uppercase tracking-wide text-gray-500">Company punctuality</p>
                <p className={"mt-2 text-5xl font-bold " + scoreClasses(data.punctuality_score)}>
                  {data.punctuality_score === null ? "—" : scoreText(data.punctuality_score)}
                </p>
                {data.punctuality_score === null ? (
                  <p className="mt-2 text-sm text-gray-400">No data yet. {data.punctuality_no_data_reason}</p>
                ) : (
                  <p className="mt-2 text-sm text-gray-400">
                    {data.punctuality_on_time} on time, {data.punctuality_late} late, {data.punctuality_not_done} not done,
                    across every department&apos;s tasks.
                  </p>
                )}
              </div>
            </div>

            <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">Last four quarters</h3>
            <TrendBars points={data.trend} />

            <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">Departments</h3>
            {data.departments.length === 0 ? (
              <p className="mt-3 text-sm text-gray-400">No department has been scored for this period yet.</p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                      <th className="py-2 pr-4 font-medium">Department</th>
                      <th className="py-2 pr-4 font-medium">Revenue share</th>
                      <th className="py-2 pr-4 font-medium">Goals</th>
                      <th className="py-2 pr-4 font-medium">Punctuality</th>
                      <th className="py-2 font-medium">In the headline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.departments.map(function (d) {
                      return (
                        <tr key={d.department_id} className="border-b border-white/5">
                          <td className="py-3 pr-4 text-white">{d.department_name}</td>
                          <td className="py-3 pr-4 text-gray-400">
                            {d.revenue_share === null ? "Not set" : scoreText(d.revenue_share) + "%"}
                          </td>
                          <td className={"py-3 pr-4 font-semibold " + scoreClasses(d.kpi_results_score)}>
                            {scoreText(d.kpi_results_score)}
                            {d.kpi_results_score !== null ? (
                              <span className="ml-2 text-xs font-normal text-gray-500">
                                {d.kpis_counted} of {d.kpis_expected} KPIs
                              </span>
                            ) : null}
                          </td>
                          <td className={"py-3 pr-4 font-semibold " + scoreClasses(d.punctuality_score)}>
                            {scoreText(d.punctuality_score)}
                          </td>
                          <td className="py-3 text-gray-400">{d.counted_in_headline ? "Yes" : "Left out"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

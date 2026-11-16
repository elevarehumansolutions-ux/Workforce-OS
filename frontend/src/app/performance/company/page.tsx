"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import {
  CURRENT_QUARTER,
  companyPath,
  customRangePath,
  executiveSummaryPath,
  mostImprovedPath,
  periodLabel,
  scoreClasses,
  scoreText,
} from "@/lib/performance";
import ChartCard from "@/components/charts/ChartCard";
import BarList, { BarTable } from "@/components/charts/BarList";
import type { BarRow } from "@/components/charts/BarList";
import TrendLines from "@/components/charts/TrendLines";
import type {
  CompanyDepartmentLine,
  CompanyPerformance,
  CompanyTrendPoint,
  CustomRange,
  ExecutiveSummary,
  MostImproved,
  MostImprovedEntry,
  Period,
} from "@/lib/performance";

function quarterLabel(startIso: string): string {
  return new Date(startIso + "T00:00:00Z").toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function numberOrNull(score: string | null): number | null {
  if (score === null) {
    return null;
  }
  return Number(score);
}

// The last four quarters as two lines: the headline score and punctuality. A quarter with no data
// leaves a gap in the line (never a drop to 0).
function TrendChart(props: { points: CompanyTrendPoint[] }) {
  const labels = props.points.map(function (point) {
    return quarterLabel(point.period_start);
  });
  const headline = props.points.map(function (point) {
    return numberOrNull(point.headline_score);
  });
  const punctuality = props.points.map(function (point) {
    return numberOrNull(point.punctuality_score);
  });

  const table = (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
          <th className="py-2 pr-4 font-medium">Quarter</th>
          <th className="py-2 pr-4 font-medium">Company score</th>
          <th className="py-2 font-medium">Punctuality</th>
        </tr>
      </thead>
      <tbody>
        {props.points.map(function (point, i) {
          return (
            <tr key={point.period_start} className="border-b border-white/5">
              <td className="py-2 pr-4 text-white">{labels[i]}</td>
              <td className="py-2 pr-4 text-gray-300">{scoreText(point.headline_score)}</td>
              <td className="py-2 text-gray-300">{scoreText(point.punctuality_score)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <ChartCard
      title="Last four quarters"
      subtitle="Two different questions, so two lines: did departments hit their goals, and did people deliver on time."
      chart={
        <TrendLines
          labels={labels}
          series={[
            { name: "Company score (goals)", colour: "#3987e5", values: headline },
            { name: "Punctuality", colour: "#d95926", values: punctuality },
          ]}
        />
      }
      table={table}
    />
  );
}

// Every department on one scale, one chart for goals and one for punctuality. They are never
// blended into one bar, for the same reason the headline numbers are never blended.
function DepartmentCharts(props: { departments: CompanyDepartmentLine[] }) {
  const goalRows: BarRow[] = props.departments.map(function (d) {
    return {
      label: d.department_name,
      value: numberOrNull(d.kpi_results_score),
      note: d.kpi_results_score !== null ? d.kpis_counted + " of " + d.kpis_expected + " KPIs" : undefined,
    };
  });
  const punctualityRows: BarRow[] = props.departments.map(function (d) {
    return { label: d.department_name, value: numberOrNull(d.punctuality_score) };
  });

  return (
    <div className="mt-3 grid gap-4 md:grid-cols-2">
      <ChartCard
        title="Goals by department"
        subtitle="KPI results against target. The line marks 100, the target."
        chart={<BarList rows={goalRows} />}
        table={<BarTable rows={goalRows} valueHeading="Goals score" />}
      />
      <ChartCard
        title="Punctuality by department"
        subtitle="Share of tasks finished on time (late counts half)."
        chart={<BarList rows={punctualityRows} />}
        table={<BarTable rows={punctualityRows} valueHeading="Punctuality" />}
      />
    </div>
  );
}

// The short written summary. It never names a person; every number in it was checked by the server.
function SummaryBox(props: { period: Period }) {
  const load = useLoad<ExecutiveSummary>(
    "summary|" + props.period.start + "|" + props.period.end,
    function () {
      return apiFetch<ExecutiveSummary>(executiveSummaryPath(props.period), { method: "GET" });
    },
    "Could not load the summary."
  );
  const data = load.data;

  return (
    <div className="mb-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-indigo-200">Summary</p>
        {data && data.summary_text !== null ? (
          <p className="text-xs text-indigo-200/70">
            {data.is_final ? "Final for this quarter" : "Updated weekly, so far this quarter"}
            {data.source === "plain" ? " · facts only" : ""}
          </p>
        ) : null}
      </div>
      {load.loading ? <p className="mt-2 text-sm text-gray-400">Loading…</p> : null}
      {load.error ? <p className="mt-2 text-sm text-red-300">{load.error}</p> : null}
      {data && data.summary_text !== null ? <p className="mt-2 text-sm leading-relaxed text-white">{data.summary_text}</p> : null}
      {data && data.summary_text === null ? <p className="mt-2 text-sm text-gray-300">{data.no_data_reason}</p> : null}
    </div>
  );
}

function ImprovedList(props: { title: string; entries: MostImprovedEntry[] }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <p className="text-xs uppercase tracking-wide text-gray-500">{props.title}</p>
      {props.entries.length === 0 ? (
        <p className="mt-3 text-sm text-gray-400">Nobody qualifies yet.</p>
      ) : (
        <ol className="mt-3 space-y-3">
          {props.entries.map(function (entry) {
            return (
              <li key={entry.id}>
                <p className="text-sm font-medium text-white">
                  {entry.name} <span className="text-emerald-300">+{scoreText(entry.change_in_points)} points</span>
                </p>
                <p className="text-xs text-gray-500">
                  {scoreText(entry.previous_score)} to {scoreText(entry.current_score)}, on {entry.previous_tasks} tasks
                  before and {entry.current_tasks} now
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

// Recognition, not a verdict: the three biggest gains in points since the quarter before,
// each with how it was earned, and only for people and teams with enough tasks in both quarters.
function MostImprovedSection(props: { period: Period }) {
  const load = useLoad<MostImproved>(
    "improved|" + props.period.start + "|" + props.period.end,
    function () {
      return apiFetch<MostImproved>(mostImprovedPath(props.period), { method: "GET" });
    },
    "Could not load Most Improved."
  );
  const data = load.data;

  return (
    <div>
      <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">Most improved</h3>
      {load.loading ? <p className="mt-3 text-sm text-gray-400">Loading…</p> : null}
      {load.error ? <p className="mt-3 text-sm text-red-300">{load.error}</p> : null}
      {data ? (
        <div>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <ImprovedList title="People" entries={data.people} />
            <ImprovedList title="Departments (team punctuality)" entries={data.departments} />
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Gain in points since the quarter before. Listed only with at least {data.min_valid_tasks} valid tasks in both
            quarters, so a lucky few tasks do not win.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function CustomRangeResult(props: { first: string; last: string }) {
  const load = useLoad<CustomRange>(
    "range|" + props.first + "|" + props.last,
    function () {
      return apiFetch<CustomRange>(customRangePath(props.first, props.last), { method: "GET" });
    },
    "Could not work out this range."
  );
  const data = load.data;

  return (
    <div className="mt-4">
      {load.loading ? <p className="text-sm text-gray-400">Working it out…</p> : null}
      {load.error ? <p className="text-sm text-red-300">{load.error}</p> : null}
      {data ? (
        <div>
          {/* The label comes from the server on purpose: this is not an official quarterly figure. */}
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">{data.label}</p>
          <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-5">
            <p className="text-xs uppercase tracking-wide text-gray-500">
              Company punctuality, {periodLabel(data.period_start, data.period_end)}
            </p>
            <p className={"mt-2 text-4xl font-bold " + scoreClasses(data.punctuality_score)}>
              {data.punctuality_score === null ? "—" : scoreText(data.punctuality_score)}
            </p>
            <p className="mt-2 text-sm text-gray-400">
              {data.punctuality_score === null
                ? "No data yet. " + data.punctuality_no_data_reason
                : data.punctuality_on_time + " on time, " + data.punctuality_late + " late, " + data.punctuality_not_done + " not done."}
            </p>
          </div>
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                <th className="py-2 pr-4 font-medium">Department</th>
                <th className="py-2 pr-4 font-medium">Punctuality</th>
                <th className="py-2 font-medium">On time / late / not done</th>
              </tr>
            </thead>
            <tbody>
              {data.departments.map(function (d) {
                return (
                  <tr key={d.department_id} className="border-b border-white/5">
                    <td className="py-3 pr-4 text-white">{d.department_name}</td>
                    <td className={"py-3 pr-4 font-semibold " + scoreClasses(d.punctuality_score)}>
                      {scoreText(d.punctuality_score)}
                    </td>
                    <td className="py-3 text-gray-400">
                      {d.punctuality_on_time} / {d.punctuality_late} / {d.punctuality_not_done}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

// Any window of up to 12 months, worked out live. Goals (KPI results) are only recorded per quarter,
// so a custom window shows punctuality only.
function CustomRangeSection() {
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [applied, setApplied] = useState<{ first: string; last: string } | null>(null);
  const [message, setMessage] = useState("");

  function apply() {
    if (first === "" || last === "") {
      setMessage("Pick both dates.");
      return;
    }
    if (last < first) {
      setMessage("The end date cannot be before the start date.");
      return;
    }
    const days = (new Date(last).getTime() - new Date(first).getTime()) / 86400000;
    if (days > 365) {
      setMessage("A custom range can cover at most 12 months.");
      return;
    }
    setMessage("");
    setApplied({ first: first, last: last });
  }

  const inputClass = "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white";

  return (
    <div>
      <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">Custom date range</h3>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-xs text-gray-500">
          From
          <input
            type="date"
            value={first}
            onChange={function (e) {
              setFirst(e.target.value);
            }}
            className={inputClass + " mt-1 block"}
          />
        </label>
        <label className="text-xs text-gray-500">
          To
          <input
            type="date"
            value={last}
            onChange={function (e) {
              setLast(e.target.value);
            }}
            className={inputClass + " mt-1 block"}
          />
        </label>
        <button type="button" onClick={apply} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
          Show
        </button>
      </div>
      {message ? <p className="mt-2 text-sm text-red-300">{message}</p> : null}
      {applied ? <CustomRangeResult first={applied.first} last={applied.last} /> : null}
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
            <SummaryBox period={period} />

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

            <div className="mt-6">
              <TrendChart points={data.trend} />
            </div>

            <h3 className="mt-8 text-sm font-semibold uppercase tracking-wide text-gray-400">Departments</h3>
            {data.departments.length > 0 ? <DepartmentCharts departments={data.departments} /> : null}
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

            <MostImprovedSection period={period} />

            <CustomRangeSection />
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

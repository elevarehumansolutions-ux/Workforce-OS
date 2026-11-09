"use client";

import Link from "next/link";
import { formatMoney } from "@/lib/blueprint";
import { loadValueSummary, valueStatusClasses, valueStatusLabel } from "@/lib/workflow";
import type { ValueSummary } from "@/lib/workflow";
import { useLoad } from "@/lib/useLoad";

// The money view of the company's jobs: what is at risk right now, what has been lost, and
// what is secured. A job's figure is counted once however many of its tasks are late. The
// server only sends the cases the viewer may already see, so an employee sees their own.
export default function ValueAtRiskCard() {
  const summary = useLoad<ValueSummary>("value-summary", loadValueSummary, "Couldn't load the value of your jobs.");
  const data = summary.data;

  const tile = "rounded-lg border border-white/5 bg-[#0a0e1a] p-3";
  const label = "text-[11px] uppercase tracking-wide text-gray-500";

  return (
    <section className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-white">Value of your jobs</h2>
          <p className="text-xs text-gray-500">
            What each job is worth to you. A late task puts its job&apos;s figure at risk; a cancelled or overdue job loses it.
          </p>
        </div>
        <Link href="/workflow/tracker" className="text-xs font-medium text-indigo-400 hover:text-indigo-300">
          See all jobs
        </Link>
      </div>

      {summary.loading ? <div className="mt-4 h-20 animate-pulse rounded-lg bg-white/5" /> : null}
      {summary.error ? <p className="mt-4 text-sm text-red-300">{summary.error}</p> : null}

      {data ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className={tile + " border-amber-500/20"}>
              <p className={label}>At risk now</p>
              <p className="text-lg font-semibold text-amber-300">{formatMoney(Number(data.at_risk_total))}</p>
              <p className="text-xs text-gray-500">
                {data.cases_at_risk} {data.cases_at_risk === 1 ? "job" : "jobs"}
              </p>
            </div>
            <div className={tile + " border-red-500/20"}>
              <p className={label}>Lost</p>
              <p className="text-lg font-semibold text-red-300">{formatMoney(Number(data.lost_total))}</p>
              <p className="text-xs text-gray-500">
                {data.cases_lost} {data.cases_lost === 1 ? "job" : "jobs"}
              </p>
            </div>
            <div className={tile}>
              <p className={label}>On track</p>
              <p className="text-lg font-semibold text-white">{formatMoney(Number(data.on_track_total))}</p>
            </div>
            <div className={tile}>
              <p className={label}>Secured</p>
              <p className="text-lg font-semibold text-emerald-300">{formatMoney(Number(data.secured_total))}</p>
            </div>
          </div>

          {data.cases.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing is at risk or lost. Jobs without a figure are not counted here.</p>
          ) : (
            <ul className="space-y-2">
              {data.cases.slice(0, 6).map(function (c) {
                return (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/5 bg-[#0a0e1a] px-3 py-2.5">
                    <div className="min-w-0">
                      <Link href={"/workflow/case-detail?id=" + c.id} className="text-sm font-medium text-white hover:text-indigo-300">
                        {c.subject}
                      </Link>
                      {c.overdue_tasks.length > 0 ? (
                        <p className="text-xs text-gray-500">
                          {c.overdue_tasks.length} overdue {c.overdue_tasks.length === 1 ? "task" : "tasks"}, for example “{c.overdue_tasks[0].title}”
                        </p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-200">{formatMoney(Number(c.client_value))}</span>
                      <span className={"rounded px-2 py-0.5 text-xs font-medium " + valueStatusClasses(c.value_status)}>
                        {valueStatusLabel(c.value_status)}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {data.cases_without_deadline > 0 ? (
            <p className="text-xs text-amber-200/80">
              {data.cases_without_deadline} running {data.cases_without_deadline === 1 ? "job has" : "jobs have"} no final deadline, so
              {data.cases_without_deadline === 1 ? " its figure" : " their figures"} can show as at risk but not be counted as lost on time.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

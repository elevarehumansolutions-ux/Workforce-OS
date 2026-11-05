"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { CURRENT_QUARTER, departmentsICanOpen, leaderboardPath, scoreClasses, scoreText } from "@/lib/performance";
import type { Leaderboard, Period } from "@/lib/performance";

export default function LeaderboardPage() {
  const [period, setPeriod] = useState<Period>(CURRENT_QUARTER);
  const [departmentId, setDepartmentId] = useState("");
  const [page, setPage] = useState(1);

  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const board = useLoad<Leaderboard>(
    departmentId + "|" + period.start + "|" + period.end + "|" + page,
    function () {
      return apiFetch<Leaderboard>(leaderboardPath(departmentId, period, page), { method: "GET" });
    },
    "Could not load the leaderboard."
  );

  const ctx = caller.data;
  const data = board.data;

  function changePeriod(next: Period) {
    setPeriod(next);
    setPage(1);
  }

  return (
    <AppShell
      activeLabel="Performance"
      title="Leaderboard"
      breadcrumb="Dashboard > Performance > Leaderboard"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={
        <Link href="/performance" className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
          My performance
        </Link>
      }
    >
      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <PeriodBar
            shownStart={data ? data.period_start : null}
            shownEnd={data ? data.period_end : null}
            asked={period}
            isFinal={data ? data.is_final : false}
            onChange={changePeriod}
          />
          {ctx ? (
            <select
              value={departmentId}
              onChange={function (e) {
                setDepartmentId(e.target.value);
                setPage(1);
              }}
              className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white"
            >
              <option value="">All departments I can see</option>
              {departmentsICanOpen(ctx).map(function (d) {
                return (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                );
              })}
            </select>
          ) : null}
        </div>

        {board.loading ? <p className="mt-6 text-sm text-gray-400">Loading the leaderboard…</p> : null}

        {!board.loading && board.status === 404 ? (
          <p className="mt-6 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-gray-300">
            The leaderboard is for HR, executives, and the heads and managers of a department. You can see your own score
            on <Link href="/performance" className="text-indigo-300 hover:underline">My performance</Link>.
          </p>
        ) : null}

        {!board.loading && board.error && board.status !== 404 ? (
          <p className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{board.error}</p>
        ) : null}

        {data && data.entries.length === 0 ? (
          <p className="mt-6 text-sm text-gray-400">
            No one has a score in this period yet. Scores appear once tasks linked to a KPI have passed their deadlines.
          </p>
        ) : null}

        {data && data.entries.length > 0 ? (
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-4 font-medium">Rank</th>
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Department</th>
                  <th className="py-2 pr-4 font-medium">Score</th>
                  <th className="py-2 pr-4 font-medium">Based on</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map(function (entry) {
                  return (
                    <tr key={entry.employee_id} className="border-b border-white/5">
                      <td className="py-3 pr-4 text-gray-300">{entry.rank}</td>
                      <td className="py-3 pr-4">
                        <Link href={"/performance/person/" + entry.employee_id} className="text-white hover:text-indigo-300 hover:underline">
                          {entry.employee_name}
                        </Link>
                      </td>
                      <td className="py-3 pr-4 text-gray-400">{entry.department_name}</td>
                      <td className={"py-3 pr-4 font-semibold " + scoreClasses(entry.overall_score)}>
                        {scoreText(entry.overall_score)}
                      </td>
                      <td className="py-3 pr-4 text-gray-400">
                        {entry.valid_tasks} {entry.valid_tasks === 1 ? "task" : "tasks"}, {entry.kpis_counted} of{" "}
                        {entry.kpis_expected} KPIs
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {data && data.pagination.total_pages > 1 ? (
          <div className="mt-4 flex items-center gap-3 text-sm text-gray-400">
            <button
              type="button"
              disabled={!data.pagination.has_previous}
              onClick={function () {
                setPage(page - 1);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <span>
              Page {data.pagination.page} of {data.pagination.total_pages}
            </span>
            <button
              type="button"
              disabled={!data.pagination.has_next}
              onClick={function () {
                setPage(page + 1);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        ) : null}

        <p className="mt-6 text-xs text-gray-500">
          A high score on only a few tasks is shown next to the number of tasks it rests on, so scores are read with
          their context. People with no scored tasks are not listed.
        </p>
      </div>
    </AppShell>
  );
}

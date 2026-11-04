"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import PersonCard from "@/components/performance/PersonCard";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { CURRENT_QUARTER, canSeeRankedList, departmentsICanOpen, personPath } from "@/lib/performance";
import type { Period, PersonPerformance } from "@/lib/performance";

export default function MyPerformancePage() {
  const [period, setPeriod] = useState<Period>(CURRENT_QUARTER);

  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const card = useLoad<PersonPerformance>(
    "me|" + period.start + "|" + period.end,
    function () {
      return apiFetch<PersonPerformance>(personPath("me", period), { method: "GET" });
    },
    "Could not load your performance."
  );

  const ctx = caller.data;
  const data = card.data;

  const actions = ctx ? (
    <div className="flex items-center gap-2">
      {departmentsICanOpen(ctx).length > 0 ? (
        <Link href="/performance/department" className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
          Department view
        </Link>
      ) : null}
      {canSeeRankedList(ctx) ? (
        <Link href="/performance/leaderboard" className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600">
          Leaderboard
        </Link>
      ) : null}
    </div>
  ) : undefined;

  return (
    <AppShell
      activeLabel="Performance"
      title="My performance"
      breadcrumb="Dashboard > Performance"
      userName={ctx ? ctx.userName : undefined}
      userRole={ctx ? roleLabel(ctx.role) : undefined}
      actions={actions}
    >
      <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
        <PeriodBar
          shownStart={data ? data.period_start : null}
          shownEnd={data ? data.period_end : null}
          asked={period}
          isFinal={data ? data.is_final : false}
          onChange={setPeriod}
        />

        {card.loading ? <p className="mt-6 text-sm text-gray-400">Loading your performance…</p> : null}

        {!card.loading && card.status === 404 ? (
          <div className="mt-6 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-6 text-center">
            <p className="text-base font-semibold">No personal score to show</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-gray-400">
              Your login isn&apos;t linked to an employee record, so there are no tasks to score. People with an
              organization-wide role can open a department or the leaderboard instead.
            </p>
          </div>
        ) : null}

        {!card.loading && card.error && card.status !== 404 ? (
          <p className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{card.error}</p>
        ) : null}

        {data ? <PersonCard data={data} /> : null}
      </div>
    </AppShell>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import AppShell from "@/components/AppShell";
import PeriodBar from "@/components/performance/PeriodBar";
import PersonCard from "@/components/performance/PersonCard";
import { loadCaller, roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { CURRENT_QUARTER, personPath } from "@/lib/performance";
import type { Period, PersonPerformance } from "@/lib/performance";

export default function PersonPerformancePage() {
  const params = useParams<{ id: string }>();
  const employeeId = params.id;
  const [period, setPeriod] = useState<Period>(CURRENT_QUARTER);

  const caller = useLoad("caller", loadCaller, "Could not load your details.");
  const card = useLoad<PersonPerformance>(
    employeeId + "|" + period.start + "|" + period.end,
    function () {
      return apiFetch<PersonPerformance>(personPath(employeeId, period), { method: "GET" });
    },
    "Could not load this person's performance."
  );

  const ctx = caller.data;
  const data = card.data;

  return (
    <AppShell
      activeLabel="Performance"
      title={data ? data.employee_name : "Performance"}
      breadcrumb="Dashboard > Performance > Person"
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

        {card.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}

        {!card.loading && card.status === 404 ? (
          <p className="mt-6 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-gray-300">
            This person&apos;s performance isn&apos;t available to you. You can see your own score, and the people of a
            department you head or manage.
          </p>
        ) : null}

        {!card.loading && card.error && card.status !== 404 ? (
          <p className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{card.error}</p>
        ) : null}

        {data ? <PersonCard data={data} /> : null}
      </div>
    </AppShell>
  );
}

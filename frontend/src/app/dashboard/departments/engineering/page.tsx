"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface Employee {
  id: string;
  name: string;
  role: string;
  attendancePercent: number;
  kpiScore: number;
  kpiChange: number;
}

const PERIOD_OPTIONS = ["Q1 2026", "Q2 2026", "Q3 2026", "Q4 2026", "Custom range"];

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

const EMPLOYEES: Employee[] = [
  { id: makeId(), name: "Emeka Nwankwo", role: "Senior Engineer", attendancePercent: 96.2, kpiScore: 91, kpiChange: 4 },
  { id: makeId(), name: "Aisha Bello", role: "Staff Engineer", attendancePercent: 98.1, kpiScore: 88, kpiChange: 2 },
  { id: makeId(), name: "Tunde Balogun", role: "Engineering Manager", attendancePercent: 94.8, kpiScore: 85, kpiChange: 9 },
  { id: makeId(), name: "Funke Adeyemi", role: "Software Engineer", attendancePercent: 93.5, kpiScore: 82, kpiChange: -1 },
  { id: makeId(), name: "Chidi Okonkwo", role: "DevOps Engineer", attendancePercent: 91.0, kpiScore: 79, kpiChange: 1 },
  { id: makeId(), name: "Blessing Eze", role: "QA Lead", attendancePercent: 95.3, kpiScore: 76, kpiChange: 3 },
  { id: makeId(), name: "Yusuf Ibrahim", role: "Junior Engineer", attendancePercent: 88.2, kpiScore: 71, kpiChange: 6 },
];

function scoreBarColor(score: number) {
  if (score >= 85) {
    return "bg-emerald-500";
  }
  if (score >= 75) {
    return "bg-indigo-500";
  }
  return "bg-amber-500";
}

export default function DepartmentDrilldownPage() {
  const router = useRouter();
  const [period, setPeriod] = useState("Q3 2026");
  const [showCustomRange, setShowCustomRange] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  function handlePeriodChange(value: string) {
    setPeriod(value);
    setShowCustomRange(value === "Custom range");
  }

  const leaderboard = [...EMPLOYEES].sort(function (a: Employee, b: Employee) {
    return b.kpiScore - a.kpiScore;
  });

  const mostImproved = [...EMPLOYEES].sort(function (a: Employee, b: Employee) {
    return b.kpiChange - a.kpiChange;
  })[0];

  const avgKpi = Math.round(
    EMPLOYEES.reduce(function (sum: number, e: Employee) {
      return sum + e.kpiScore;
    }, 0) / EMPLOYEES.length
  );

  const avgAttendance = (
    EMPLOYEES.reduce(function (sum: number, e: Employee) {
      return sum + e.attendancePercent;
    }, 0) / EMPLOYEES.length
  ).toFixed(1);

  const companyPerformanceScore = 84;

  return (
    <div className="min-h-screen w-full bg-[#05070f] px-8 py-8 text-white">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs text-gray-500">
            <button
              type="button"
              onClick={function () {
                router.push("/dashboard/executive-overview");
              }}
              className="hover:underline"
            >
              Executive Overview
            </button>{" "}
            <span className="text-indigo-400">&gt; Engineering</span>
          </p>
          <h1 className="mt-1 text-2xl font-bold">Engineering Department</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={period}
            onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
              handlePeriodChange(e.target.value);
            }}
            className="rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
          >
            {PERIOD_OPTIONS.map(function (opt) {
              return (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              );
            })}
          </select>
          <button
            type="button"
            onClick={function () {
              router.push("/notifications");
            }}
            className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-[#0d1220] text-gray-300 hover:bg-white/5"
            aria-label="Notifications"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
              3
            </span>
          </button>
          <span className="rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-400">
            WOS MVP Ready
          </span>
        </div>
      </div>

      {showCustomRange && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-[#0d1220]/80 p-4">
          <label className="text-sm text-gray-400">
            From{" "}
            <input
              type="date"
              value={startDate}
              onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                setStartDate(e.target.value);
              }}
              className="ml-2 rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
            />
          </label>
          <label className="text-sm text-gray-400">
            To{" "}
            <input
              type="date"
              value={endDate}
              onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                setEndDate(e.target.value);
              }}
              className="ml-2 rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
            />
          </label>
        </div>
      )}

      {/* Stat cards */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-indigo-500/40 bg-gradient-to-br from-indigo-500/20 to-transparent p-5">
          <p className="text-xs uppercase tracking-wide text-indigo-300">Company Performance Score</p>
          <p className="mt-2 text-4xl font-bold">{companyPerformanceScore}</p>
          <p className="mt-1 text-xs text-gray-400">Composite score across attendance, KPIs, and delivery</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <p className="text-xs uppercase tracking-wide text-gray-500">Engineering Headcount</p>
          <p className="mt-2 text-2xl font-bold">{EMPLOYEES.length}</p>
          <p className="mt-1 flex items-center gap-1 text-xs text-emerald-400">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
            +4 active full-time developers
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <p className="text-xs uppercase tracking-wide text-gray-500">Attendance Rate</p>
          <p className="mt-2 text-2xl font-bold">{avgAttendance}%</p>
          <p className="mt-1 text-xs text-gray-500">Calculated on active schedules</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <p className="text-xs uppercase tracking-wide text-gray-500">Avg KPI Score</p>
          <p className="mt-2 text-2xl font-bold">{avgKpi}%</p>
          <p className="mt-1 text-xs text-emerald-400">Target met</p>
        </div>
      </div>

      {/* AI executive summary */}
      <div className="mt-6 rounded-2xl border border-indigo-500/30 bg-[#0d1220]/80 p-5">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-300">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l1.9 5.8L20 9.5l-5.8 1.9L12 17l-1.9-5.8L4 9.5l5.8-1.9L12 2z" />
            </svg>
          </span>
          <p className="text-sm font-semibold text-indigo-300">AI Executive Summary</p>
        </div>
        <p className="mt-2 text-sm text-gray-300">
          Engineering is tracking above target this {period.toLowerCase()}, with an average KPI score of{" "}
          {avgKpi}% and attendance holding steady at {avgAttendance}%. {mostImproved.name} posted the
          largest quarter-over-quarter improvement at +{mostImproved.kpiChange} points, while overall
          delivery pace remains consistent with the previous cycle. No critical vacancy risks were
          identified in this department for the selected period.
        </p>
      </div>

      {/* Most improved callout */}
      <div className="mt-6 flex items-center gap-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
        <span className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </span>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-emerald-400">Most Improved</p>
          <p className="text-sm font-semibold">
            {mostImproved.name} <span className="text-gray-400">&middot; {mostImproved.role}</span>
          </p>
          <p className="text-xs text-gray-500">
            KPI score up {mostImproved.kpiChange} points versus last period
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
        {/* Employee performance breakdown */}
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <h2 className="text-base font-semibold">Employee Performance Breakdown</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[500px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="pb-2 pr-4 font-medium">Employee Name</th>
                  <th className="pb-2 pr-4 font-medium">Role</th>
                  <th className="pb-2 pr-4 font-medium">Attendance %</th>
                  <th className="pb-2 font-medium">KPI Score / Status</th>
                </tr>
              </thead>
              <tbody>
                {EMPLOYEES.map(function (emp: Employee) {
                  return (
                    <tr key={emp.id} className="border-b border-white/5">
                      <td className="py-3 pr-4 font-medium">{emp.name}</td>
                      <td className="py-3 pr-4 text-gray-400">{emp.role}</td>
                      <td className="py-3 pr-4 text-gray-400">{emp.attendancePercent}%</td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <span className="w-8 text-xs font-semibold">{emp.kpiScore}%</span>
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
                            <div
                              className={"h-full rounded-full " + scoreBarColor(emp.kpiScore)}
                              style={{ width: emp.kpiScore + "%" }}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Employee leaderboard */}
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5">
          <h2 className="text-base font-semibold">Employee Leaderboard</h2>
          <div className="mt-4 space-y-2">
            {leaderboard.map(function (emp: Employee, index: number) {
              return (
                <div
                  key={emp.id}
                  className="flex items-center gap-3 rounded-lg border border-white/5 bg-[#0a0e1a] px-3 py-2.5"
                >
                  <span
                    className={
                      "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold " +
                      (index === 0
                        ? "bg-amber-500/20 text-amber-300"
                        : index === 1
                        ? "bg-gray-400/20 text-gray-300"
                        : index === 2
                        ? "bg-orange-700/20 text-orange-300"
                        : "bg-white/5 text-gray-500")
                    }
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{emp.name}</p>
                    <p className="truncate text-xs text-gray-500">{emp.role}</p>
                  </div>
                  <span className="flex-shrink-0 text-sm font-semibold text-indigo-300">
                    {emp.kpiScore}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

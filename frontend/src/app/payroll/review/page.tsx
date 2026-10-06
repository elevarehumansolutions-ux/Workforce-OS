"use client";

import { useRouter } from "next/navigation";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
  { label: "Team Management", href: "/team-management" },
  { label: "Attendance", href: "/attendance" },
  { label: "Leave Management", href: "/leave" },
  { label: "Workflow", href: "/workflow/templates" },
  { label: "Tasks", href: "/tasks" },
  { label: "Payroll", href: "/payroll" },
  { label: "Reports", href: "/reports" },
  { label: "Settings", href: "/settings" },
];

function SidebarNav(activeLabel: string) {
  return (
    <nav className="flex flex-col gap-1 px-3">
      {SIDEBAR_ITEMS.map(function (item) {
        const isActive = item.label === activeLabel;
        let linkClass = "rounded-lg px-3 py-2.5 text-sm transition ";
        if (isActive) {
          linkClass = linkClass + "bg-indigo-500/15 text-indigo-300 font-medium";
        } else {
          linkClass = linkClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
        }
        return (
          <a key={item.label} href={item.href} className={linkClass}>
            {item.label}
          </a>
        );
      })}
    </nav>
  );
}

function SidebarShell(activeLabel: string) {
  return (
    <aside className="hidden w-64 flex-col justify-between border-r border-white/10 bg-[#0a0e1a] py-6 lg:flex">
      <div>
        <div className="mb-8 flex items-center gap-3 px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500">
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
              <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
            </svg>
          </div>
          <span className="text-base font-bold text-white">Elevare</span>
        </div>
        {SidebarNav(activeLabel)}
      </div>
      <div className="flex items-center gap-3 border-t border-white/10 px-6 pt-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          NA
        </div>
        <div>
          <p className="text-sm font-medium text-white">Ngozi Adeyemi</p>
          <p className="text-xs text-gray-500">Engineering Manager</p>
        </div>
      </div>
    </aside>
  );
}

interface BreakdownRow {
  id: string;
  initials: string;
  name: string;
  hoursWorked: string;
  attendanceAdj: string;
  kpiScore: string;
  kpiBonus: string;
  deductions: string;
  netPay: string;
}

const ROWS: BreakdownRow[] = [
  { id: "1", initials: "AO", name: "Adaeze Okonkwo", hoursWorked: "176 hrs", attendanceAdj: "+N32,000", kpiScore: "87/100", kpiBonus: "+N22,500", deductions: "-N67,500", netPay: "N437,000" },
  { id: "2", initials: "TB", name: "Tunde Balogun", hoursWorked: "152 hrs", attendanceAdj: "-N15,200", kpiScore: "92/100", kpiBonus: "+N28,000", deductions: "-N57,000", netPay: "N335,800" },
  { id: "3", initials: "FA", name: "Fatima Abubakar", hoursWorked: "168 hrs", attendanceAdj: "N0", kpiScore: "78/100", kpiBonus: "N0", deductions: "-N48,000", netPay: "N272,000" },
  { id: "4", initials: "EN", name: "Emeka Nwankwo", hoursWorked: "184 hrs", attendanceAdj: "+N41,600", kpiScore: "95/100", kpiBonus: "+N30,000", deductions: "-N78,000", netPay: "N521,600" },
  { id: "5", initials: "KA", name: "Kemi Adebayo", hoursWorked: "172 hrs", attendanceAdj: "+N16,000", kpiScore: "82/100", kpiBonus: "+N12,000", deductions: "-N60,000", netPay: "N368,000" },
  { id: "6", initials: "YI", name: "Yusuf Ibrahim", hoursWorked: "144 hrs", attendanceAdj: "-N28,000", kpiScore: "71/100", kpiBonus: "N0", deductions: "-N52,500", netPay: "N269,500" },
];

export default function ReviewPayrollPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Payroll")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Payroll &gt; Review</p>
            <h1 className="text-xl font-bold text-white">Review Payroll &mdash; August 2026</h1>
          </div>
          <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">
            WOS MVP Ready
          </span>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-5 py-3 text-sm text-indigo-200">
            Pay calculations based on approved attendance records, KPI achievement scores, and processed leave data for August 1-31, 2026.
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Employees</p>
              <p className="mt-2 text-2xl font-bold text-white">264</p>
              <p className="mt-1 text-xs text-gray-500">Active Processing Cycle</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Gross Pay</p>
              <p className="mt-2 text-2xl font-bold text-white">N68.4M</p>
              <p className="mt-1 text-xs text-gray-500">Sum of base + adjustments</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Deductions</p>
              <p className="mt-2 text-2xl font-bold text-red-400">-N10.3M</p>
              <p className="mt-1 text-xs text-gray-500">Calculated tax & contributions</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Net Pay</p>
              <p className="mt-2 text-2xl font-bold text-emerald-400">N58.1M</p>
              <p className="mt-1 text-xs text-gray-500">Total net disbursements</p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-white">Employee Pay Breakdown</h3>
              <p className="text-xs text-gray-500">Showing 6 representative breakdown segments</p>
            </div>

            <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-3 font-medium">Employee</th>
                    <th className="px-4 py-3 font-medium">Hours Worked</th>
                    <th className="px-4 py-3 font-medium">Attendance Adj.</th>
                    <th className="px-4 py-3 font-medium">KPI Score</th>
                    <th className="px-4 py-3 font-medium">KPI Bonus</th>
                    <th className="px-4 py-3 font-medium">Deductions</th>
                    <th className="px-4 py-3 font-medium">Net Pay</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {ROWS.map(function (row) {
                    let adjClass = "text-sm ";
                    if (row.attendanceAdj.indexOf("+") === 0) {
                      adjClass = adjClass + "text-emerald-400";
                    } else if (row.attendanceAdj.indexOf("-") === 0) {
                      adjClass = adjClass + "text-red-400";
                    } else {
                      adjClass = adjClass + "text-gray-500";
                    }
                    let bonusClass = "text-sm ";
                    if (row.kpiBonus.indexOf("+") === 0) {
                      bonusClass = bonusClass + "text-emerald-400";
                    } else {
                      bonusClass = bonusClass + "text-gray-500";
                    }
                    return (
                      <tr key={row.id} className="transition hover:bg-white/5">
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                              {row.initials}
                            </div>
                            <span className="font-medium text-white">{row.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-gray-300">{row.hoursWorked}</td>
                        <td className={adjClass}>{row.attendanceAdj}</td>
                        <td className="px-4 py-4 text-gray-300">{row.kpiScore}</td>
                        <td className={bonusClass}>{row.kpiBonus}</td>
                        <td className="px-4 py-4 text-red-400">{row.deductions}</td>
                        <td className="px-4 py-4 font-medium text-white">{row.netPay}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={() => router.push("/payroll/overview")}
              className="rounded-lg border border-white/10 px-5 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/5"
            >
              Cancel
            </button>
            <div className="text-right">
              <button
                type="button"
                onClick={() => console.log("Approve & process payroll clicked")}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600"
              >
                Approve & Process Payroll
              </button>
              <p className="mt-1 text-xs text-gray-600">This action requires manager approval and cannot be reversed.</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


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

type PayStatus = "Paid" | "Approved" | "Pending";

interface PayCycleRow {
  id: string;
  initials: string;
  name: string;
  department: string;
  basePay: string;
  attendanceAdj: string;
  deductions: string;
  netPay: string;
  status: PayStatus;
}

const ROWS: PayCycleRow[] = [
  { id: "1", initials: "AO", name: "Adaeze Okonkwo", department: "Engineering", basePay: "N450,000", attendanceAdj: "+N32,000", deductions: "-N67,500", netPay: "N414,500", status: "Paid" },
  { id: "2", initials: "TB", name: "Tunde Balogun", department: "Sales", basePay: "N380,000", attendanceAdj: "+N15,200", deductions: "-N57,000", netPay: "N307,800", status: "Paid" },
  { id: "3", initials: "FA", name: "Fatima Abubakar", department: "HR", basePay: "N320,000", attendanceAdj: "N0", deductions: "-N48,000", netPay: "N272,000", status: "Approved" },
  { id: "4", initials: "EN", name: "Emeka Nwankwo", department: "Engineering", basePay: "N520,000", attendanceAdj: "+N41,600", deductions: "-N78,000", netPay: "N483,600", status: "Approved" },
  { id: "5", initials: "KA", name: "Kemi Adebayo", department: "Finance", basePay: "N400,000", attendanceAdj: "+N16,000", deductions: "-N60,000", netPay: "N356,000", status: "Pending" },
  { id: "6", initials: "YI", name: "Yusuf Ibrahim", department: "Operations", basePay: "N350,000", attendanceAdj: "-N28,000", deductions: "-N52,500", netPay: "N269,500", status: "Pending" },
  { id: "7", initials: "AE", name: "Amara Eze", department: "Engineering", basePay: "N420,000", attendanceAdj: "+N33,600", deductions: "-N63,000", netPay: "N390,600", status: "Paid" },
  { id: "8", initials: "OC", name: "Obioma Chukwu", department: "Engineering", basePay: "N380,000", attendanceAdj: "N0", deductions: "-N57,000", netPay: "N323,000", status: "Pending" },
];

function PayStatusBadge(status: PayStatus) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (status === "Paid") {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  } else if (status === "Approved") {
    badgeClass = badgeClass + "bg-indigo-500/15 text-indigo-300";
  } else {
    badgeClass = badgeClass + "bg-amber-500/15 text-amber-300";
  }
  return <span className={badgeClass}>{status}</span>;
}

export default function PayrollOverviewPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Payroll")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Payroll</p>
            <h1 className="text-xl font-bold text-white">Payroll</h1>
          </div>
          <div className="flex items-center gap-4">
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">
                1
              </span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">
              WOS MVP Ready
            </span>
            <button
              type="button"
              onClick={() => router.push("/payroll/review")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Run Payroll
            </button>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Payroll</p>
              <p className="mt-2 text-2xl font-bold text-white">N47.2M</p>
              <p className="mt-1 text-xs text-gray-500">Current Cycle Total</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Employees Paid</p>
              <p className="mt-2 text-2xl font-bold text-white">198 / 264</p>
              <p className="mt-1 text-xs text-gray-500">75% Complete</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Pending Approvals</p>
              <p className="mt-2 text-2xl font-bold text-white">12 Objectives</p>
              <p className="mt-1 text-xs text-red-400">Action Required</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Next Pay Date</p>
              <p className="mt-2 text-2xl font-bold text-white">Sep 1, 2026</p>
              <p className="mt-1 text-xs text-gray-500">Regular Scheduled Cycle</p>
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between">
            <h3 className="text-base font-semibold text-white">August 2026 &mdash; Pay Cycle</h3>
            <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
              Active Processing Cycle
            </span>
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-6 py-3 font-medium">Employee</th>
                  <th className="px-6 py-3 font-medium">Department</th>
                  <th className="px-6 py-3 font-medium">Base Pay</th>
                  <th className="px-6 py-3 font-medium">Attendance Adj.</th>
                  <th className="px-6 py-3 font-medium">Deductions</th>
                  <th className="px-6 py-3 font-medium">Net Pay</th>
                  <th className="px-6 py-3 font-medium">Status</th>
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
                  return (
                    <tr key={row.id} className="transition hover:bg-white/5">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {row.initials}
                          </div>
                          <span className="font-medium text-white">{row.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-300">{row.department}</td>
                      <td className="px-6 py-4 text-gray-300">{row.basePay}</td>
                      <td className={adjClass}>{row.attendanceAdj}</td>
                      <td className="px-6 py-4 text-red-400">{row.deductions}</td>
                      <td className="px-6 py-4 font-medium text-white">{row.netPay}</td>
                      <td className="px-6 py-4">{PayStatusBadge(row.status)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
            <p>Showing 1-8 of 264 employees</p>
            <div className="flex items-center gap-2">
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">Previous</button>
              <button type="button" className="rounded-lg bg-indigo-500 px-3 py-1.5 font-medium text-white">1</button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">2</button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">3</button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">Next</button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


"use client";

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

interface DeptRow {
  id: string;
  department: string;
  headcount: number;
  openPositions: number;
  manager: string;
  progress: number;
}

const DEPARTMENTS: DeptRow[] = [
  { id: "1", department: "Engineering", headcount: 84, openPositions: 3, manager: "A. Okoro", progress: 85 },
  { id: "2", department: "HR", headcount: 18, openPositions: 1, manager: "F. Adeyemi", progress: 90 },
  { id: "3", department: "Sales & Marketing", headcount: 62, openPositions: 4, manager: "T. Balogun", progress: 70 },
  { id: "4", department: "Finance", headcount: 14, openPositions: 0, manager: "K. Alade", progress: 95 },
  { id: "5", department: "Operations", headcount: 72, openPositions: 2, manager: "C. Nwosu", progress: 75 },
  { id: "6", department: "Customer Success", headcount: 34, openPositions: 2, manager: "O. Ibe", progress: 65 },
];

function progressBarColor(progress: number) {
  if (progress >= 85) return "bg-emerald-500";
  return "bg-indigo-500";
}

export default function HrDashboardPage() {
  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Dashboard")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <h1 className="text-xl font-bold text-white">HR Dashboard</h1>
            <p className="text-sm text-gray-500">People Operations &amp; Organizational Health</p>
          </div>
          <div className="flex items-center gap-4">
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">1</span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">WOS MVP Ready</span>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Total Employees</p>
                <span className="text-xs font-medium text-emerald-400">&uarr; +12</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">284</p>
              <p className="mt-1 text-xs text-gray-500">Active headcount across all departments</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Departments</p>
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">5</p>
              <p className="mt-1 text-xs text-gray-500">Engineering &middot; HR &middot; Sales &middot; Finance &middot; Ops</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Open Payroll Approvals</p>
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">Pending</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">12</p>
              <p className="mt-1 text-xs text-gray-500">Awaiting HR review for August cycle</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Critical Roles at Risk</p>
                <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-300">Vacant</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">2</p>
              <p className="mt-1 text-xs text-gray-500">Revenue-critical positions need coverage</p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h3 className="text-base font-semibold text-white">Org Structure &mdash; Departments &amp; Headcount</h3>
            <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-3 font-medium">Department</th>
                    <th className="px-4 py-3 font-medium">Headcount</th>
                    <th className="px-4 py-3 font-medium">Open Positions</th>
                    <th className="px-4 py-3 font-medium">Manager/Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {DEPARTMENTS.map(function (dept) {
                    const barColor = progressBarColor(dept.progress);
                    return (
                      <tr key={dept.id} className="transition hover:bg-white/5">
                        <td className="px-4 py-3 font-medium text-white">{dept.department}</td>
                        <td className="px-4 py-3 text-gray-300">{dept.headcount}</td>
                        <td className="px-4 py-3 text-gray-300">{dept.openPositions}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="w-20 text-gray-300">{dept.manager}</span>
                            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
                              <div className={"h-full rounded-full " + barColor} style={{ width: dept.progress + "%" }} />
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <button type="button" className="mt-3 text-sm font-medium text-indigo-400 hover:text-indigo-300">
              View Organization &rarr;
            </button>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-white">Business DNA</h3>
                <button type="button" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">View / Edit &rarr;</button>
              </div>
              <div className="mt-4">
                <p className="text-xs uppercase tracking-wide text-gray-500">Vision</p>
                <p className="mt-1 text-sm text-gray-300">
                  To become the leading workforce management platform across West Africa, empowering organizations with intelligent, people-first HR technology.
                </p>
              </div>
              <div className="mt-4">
                <p className="text-xs uppercase tracking-wide text-gray-500">Mission</p>
                <p className="mt-1 text-sm text-gray-300">
                  Simplify workforce operations by combining compliance automation, payroll processing, and performance tracking in a single platform designed for African markets.
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-white">Payroll Runs</h3>
                <button type="button" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">View Payroll &rarr;</button>
              </div>
              <p className="mt-4 text-xs text-gray-500">Current Cycle &mdash; August 2026</p>
              <div className="mt-2 flex items-center gap-3">
                <p className="text-2xl font-bold text-white">N47.2M</p>
                <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300">Processing</span>
              </div>
              <p className="mt-2 text-sm text-gray-400">12 approvals pending &middot; 284 employees in cycle</p>
              <p className="mt-4 text-xs text-gray-600">Last completed: July 2026 &mdash; N45.8M disbursed</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

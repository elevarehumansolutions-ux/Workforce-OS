"use client";

import { useRouter } from "next/navigation";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
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

interface ActivityItem {
  id: string;
  icon: "check" | "adjust" | "file";
  title: string;
  detail: string;
  timestamp: string;
}

const ACTIVITY: ActivityItem[] = [
  { id: "1", icon: "check", title: "August 2026 payroll processed", detail: "N47.2M disbursed across 284 employees. Direct deposit completed.", timestamp: "Aug 2026" },
  { id: "2", icon: "adjust", title: "July 2026 salary adjustments approved", detail: "12 merit increases and 3 role-change adjustments applied to July cycle.", timestamp: "Jul 2026" },
  { id: "3", icon: "file", title: "Q2 2026 tax remittance filed", detail: "PAYE, pension, and NHF contributions submitted to FIRS and PenCom.", timestamp: "Jun 2026" },
];

function ActivityIcon(icon: ActivityItem["icon"]) {
  let bgClass = "flex h-8 w-8 shrink-0 items-center justify-center rounded-full ";
  if (icon === "check") {
    bgClass = bgClass + "bg-emerald-500/15 text-emerald-300";
  } else if (icon === "adjust") {
    bgClass = bgClass + "bg-indigo-500/15 text-indigo-300";
  } else {
    bgClass = bgClass + "bg-amber-500/15 text-amber-300";
  }
  return (
    <div className={bgClass}>
      <span className="h-2 w-2 rounded-full bg-current" />
    </div>
  );
}

export default function PayrollHubPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Payroll")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Payroll</p>
            <h1 className="text-xl font-bold text-white">Payroll</h1>
            <p className="text-sm text-gray-500">Manage pay cycles and compensation</p>
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
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <button
              type="button"
              onClick={() => router.push("/payroll/overview")}
              className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40"
            >
              <div className="flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="5" width="20" height="14" rx="2" />
                    <line x1="2" y1="10" x2="22" y2="10" />
                  </svg>
                </div>
                <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">this cycle</span>
              </div>
              <h3 className="mt-4 text-base font-semibold text-white">Payroll Overview</h3>
              <p className="mt-1 text-sm text-gray-500">View current and past pay cycles</p>
              <p className="mt-4 text-2xl font-bold text-white">N47.2M</p>
            </button>

            <button
              type="button"
              onClick={() => router.push("/payroll/review")}
              className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40"
            >
              <div className="flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/15 text-amber-300">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 11l3 3L22 4" />
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                  </svg>
                </div>
                <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300">awaiting review</span>
              </div>
              <h3 className="mt-4 text-base font-semibold text-white">Review & Run Payroll</h3>
              <p className="mt-1 text-sm text-gray-500">Review calculations and approve the current pay run</p>
              <p className="mt-4 text-2xl font-bold text-white">12 pending</p>
            </button>
          </div>

          <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-white">Recent Activity</h3>
              <button type="button" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
                View All Transactions
              </button>
            </div>
            <div className="mt-4 flex flex-col divide-y divide-white/5">
              {ACTIVITY.map(function (item) {
                return (
                  <div key={item.id} className="flex items-start gap-3 py-3">
                    {ActivityIcon(item.icon)}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white">{item.title}</p>
                      <p className="text-xs text-gray-500">{item.detail}</p>
                    </div>
                    <span className="text-xs text-gray-600">{item.timestamp}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


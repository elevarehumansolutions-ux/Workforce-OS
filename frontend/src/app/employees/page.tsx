"use client";

import { useRouter } from "next/navigation";

interface ActivityItem {
  id: string;
  actor: string;
  action: string;
  timestamp: string;
}

const ACTIVITY: ActivityItem[] = [
  { id: "1", actor: "Adewale Alabi", action: "was added to the Engineering department", timestamp: "2 hours ago" },
  { id: "2", actor: "Chioma Nwosu", action: "updated her bank details", timestamp: "5 hours ago" },
  { id: "3", actor: "Tunde Bakare", action: "requested annual leave", timestamp: "1 day ago" },
  { id: "4", actor: "Ifeoma Eze", action: "was promoted to Team Lead", timestamp: "2 days ago" },
];

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

function SidebarNav() {
  return (
    <nav className="flex flex-col gap-1 px-3">
      {SIDEBAR_ITEMS.map(function (item) {
        const isActive = item.label === "Employees";
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

function TopBar() {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
      <div>
        <h1 className="text-xl font-bold text-white">Employees</h1>
        <p className="text-sm text-gray-500">Manage your workforce records and roles</p>
      </div>
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-sm font-semibold text-white">
        EA
      </div>
    </div>
  );
}

export default function EmployeesHubPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      <aside className="hidden w-64 flex-col justify-between border-r border-white/10 bg-[#0a0e1a] py-6 lg:flex">
        <div>
          <div className="mb-8 flex items-center gap-3 px-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500">
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
                <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
              </svg>
            </div>
            <span className="text-base font-bold">Elevare</span>
          </div>
          <SidebarNav />
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

      <div className="flex flex-1 flex-col">
        <TopBar />

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            <button
              type="button"
              onClick={() => router.push("/employees/directory")}
              className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40"
            >
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-white">Employee Directory</h3>
              <p className="mt-1 text-sm text-gray-500">Browse and search all employee records</p>
            </button>

            <button
              type="button"
              onClick={() => router.push("/employees/add")}
              className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40"
            >
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="8.5" cy="7" r="4" />
                  <line x1="20" y1="8" x2="20" y2="14" />
                  <line x1="17" y1="11" x2="23" y2="11" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-white">Add Employee</h3>
              <p className="mt-1 text-sm text-gray-500">Onboard a new team member</p>
            </button>

            <button
              type="button"
              onClick={() => router.push("/employees/critical-roles")}
              className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-left shadow-xl transition hover:border-indigo-500/40"
            >
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/15 text-amber-300">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 9v4" />
                  <path d="M12 17h.01" />
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-white">Critical Roles</h3>
              <p className="mt-1 text-sm text-gray-500">3 roles currently unfilled or at risk</p>
            </button>
          </div>

          <div className="mt-8 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h3 className="mb-4 text-base font-semibold text-white">Recent Activity</h3>
            <div className="flex flex-col divide-y divide-white/5">
              {ACTIVITY.map(function (item) {
                return (
                  <div key={item.id} className="flex items-center justify-between py-3">
                    <p className="text-sm text-gray-300">
                      <span className="font-medium text-white">{item.actor}</span> {item.action}
                    </p>
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


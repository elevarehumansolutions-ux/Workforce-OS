"use client";

import { useState } from "react";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
  { label: "Team Management", href: "/team-management" },
  { label: "Organization Structure", href: "/organization-structure" },
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

function TopBar(breadcrumb: string, title: string) {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
      <div>
        <p className="text-xs text-gray-500">{breadcrumb}</p>
        <h1 className="text-xl font-bold text-white">{title}</h1>
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
  );
}

type LeaveStatus = "Pending" | "Approved" | "Rejected";

interface LeaveRequest {
  id: string;
  initials: string;
  name: string;
  leaveType: string;
  dates: string;
  duration: string;
  reason: string;
  status: LeaveStatus;
}

const REQUESTS: LeaveRequest[] = [
  { id: "1", initials: "EO", name: "Emeka Okafor", leaveType: "Annual", dates: "Aug 24 - Sep 4", duration: "10 Days", reason: "Family Relocat...", status: "Pending" },
  { id: "2", initials: "BA", name: "Bolaji Alabi", leaveType: "Maternity", dates: "Sep 1 - Nov 30", duration: "90 Days", reason: "Maternity Leave", status: "Approved" },
  { id: "3", initials: "CN", name: "Chika Nwosu", leaveType: "Sick", dates: "Aug 20 - Aug 22", duration: "2 Days", reason: "Medical Appoi...", status: "Approved" },
  { id: "4", initials: "IB", name: "Ibrahim Bello", leaveType: "Compassionate", dates: "Aug 21 - Aug 25", duration: "4 Days", reason: "Family Emerge...", status: "Pending" },
  { id: "5", initials: "AY", name: "Adaeze Yusuf", leaveType: "Study", dates: "Oct 1 - Oct 14", duration: "14 Days", reason: "Professional C...", status: "Rejected" },
  { id: "6", initials: "YD", name: "Yusuf Danjuma", leaveType: "Casual", dates: "Aug 28 - Aug 29", duration: "1 Day", reason: "Personal Matt...", status: "Approved" },
];

const TABS = ["All Requests", "Pending", "Approved", "Rejected"];

function LeaveStatusBadge(status: LeaveStatus) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (status === "Pending") {
    badgeClass = badgeClass + "bg-amber-500/15 text-amber-300";
  } else if (status === "Approved") {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  } else {
    badgeClass = badgeClass + "bg-red-500/15 text-red-300";
  }
  return <span className={badgeClass}>{status}</span>;
}

export default function LeaveManagementPage() {
  const [activeTab, setActiveTab] = useState("All Requests");

  const pendingCount = REQUESTS.filter(function (r) {
    return r.status === "Pending";
  }).length;

  const visibleRequests = REQUESTS.filter(function (r) {
    if (activeTab === "All Requests") return true;
    return r.status === activeTab;
  });

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Leave Management")}

      <div className="flex flex-1 flex-col">
        {TopBar("Dashboard > Leave", "Leave Management")}

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Pending Requests</p>
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{pendingCount}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Approved This Month</p>
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">23</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Rejected This Month</p>
                <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">3</p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-2">
              {TABS.map(function (tab) {
                const isActive = tab === activeTab;
                let label = tab;
                if (tab === "Pending") {
                  label = "Pending (" + pendingCount + ")";
                }
                let tabClass = "rounded-lg px-4 py-2 text-sm font-medium transition ";
                if (isActive) {
                  tabClass = tabClass + "bg-indigo-500 text-white";
                } else {
                  tabClass = tabClass + "border border-white/10 text-gray-300 hover:bg-white/5";
                }
                return (
                  <button key={tab} type="button" onClick={() => setActiveTab(tab)} className={tabClass}>
                    {label}
                  </button>
                );
              })}
            </div>
            <input
              type="text"
              placeholder="Search requests..."
              className="w-56 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-6 py-3 font-medium">Employee</th>
                  <th className="px-6 py-3 font-medium">Leave Type</th>
                  <th className="px-6 py-3 font-medium">Dates</th>
                  <th className="px-6 py-3 font-medium">Duration</th>
                  <th className="px-6 py-3 font-medium">Reason</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {visibleRequests.map(function (request) {
                  return (
                    <tr key={request.id} className="transition hover:bg-white/5">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {request.initials}
                          </div>
                          <span className="font-medium text-white">{request.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-300">{request.leaveType}</td>
                      <td className="px-6 py-4 text-gray-300">{request.dates}</td>
                      <td className="px-6 py-4 text-gray-300">{request.duration}</td>
                      <td className="px-6 py-4 text-gray-300">{request.reason}</td>
                      <td className="px-6 py-4">{LeaveStatusBadge(request.status)}</td>
                      <td className="px-6 py-4">
                        {request.status === "Pending" ? (
                          <div className="flex gap-2">
                            <button type="button" className="rounded-lg bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/25">
                              Approve
                            </button>
                            <button type="button" className="rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/25">
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-600">No actions required</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </div>
  );
}


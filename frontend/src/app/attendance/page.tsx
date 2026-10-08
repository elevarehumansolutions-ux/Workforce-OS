"use client";

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

type AttendanceStatus = "Present" | "Late" | "Absent" | "On Leave";

interface AttendanceRecord {
  id: string;
  initials: string;
  name: string;
  department: string;
  checkIn: string;
  checkOut: string;
  totalHours: string;
  status: AttendanceStatus;
}

const RECORDS: AttendanceRecord[] = [
  { id: "1", initials: "CB", name: "Chidi Benson", department: "Engineering", checkIn: "08:12 AM", checkOut: "05:15 PM", totalHours: "9.0 hrs", status: "Present" },
  { id: "2", initials: "FA", name: "Funmi Alao", department: "Marketing", checkIn: "09:45 AM", checkOut: "06:00 PM", totalHours: "8.2 hrs", status: "Late" },
  { id: "3", initials: "AY", name: "Amadi Yusuf", department: "Sales", checkIn: "08:05 AM", checkOut: "05:00 PM", totalHours: "8.9 hrs", status: "Present" },
  { id: "4", initials: "KO", name: "Kelechi Okafor", department: "HR", checkIn: "-", checkOut: "-", totalHours: "0 hrs", status: "Absent" },
  { id: "5", initials: "TB", name: "Tunde Bakogun", department: "Operations", checkIn: "08:30 AM", checkOut: "05:30 PM", totalHours: "9.0 hrs", status: "Present" },
  { id: "6", initials: "EO", name: "Efe Okoye", department: "Engineering", checkIn: "-", checkOut: "-", totalHours: "0 hrs", status: "On Leave" },
  { id: "7", initials: "ZH", name: "Zainab Haruna", department: "Finance", checkIn: "08:15 AM", checkOut: "05:00 PM", totalHours: "8.7 hrs", status: "Present" },
];

function AttendanceBadge(status: AttendanceStatus) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (status === "Present") {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  } else if (status === "Late") {
    badgeClass = badgeClass + "bg-amber-500/15 text-amber-300";
  } else if (status === "Absent") {
    badgeClass = badgeClass + "bg-red-500/15 text-red-300";
  } else {
    badgeClass = badgeClass + "bg-cyan-500/15 text-cyan-300";
  }
  return <span className={badgeClass}>{status}</span>;
}

export default function AttendancePage() {
  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Attendance")}

      <div className="flex flex-1 flex-col">
        {TopBar("Dashboard > Attendance", "Attendance")}

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Present Today</p>
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">234</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Late Arrivals</p>
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">12</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">Absent</p>
                <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">8</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-gray-500">On Leave</p>
                <span className="rounded-full bg-cyan-500/15 px-2 py-0.5 text-[10px] font-medium text-cyan-300">Active</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-white">14</p>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                placeholder="Search employees..."
                className="w-56 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
              <input
                type="text"
                defaultValue="August 20, 2026"
                readOnly
                className="w-40 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2 text-sm text-gray-300 outline-none"
              />
              <select className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500">
                <option>Department: All</option>
              </select>
            </div>
            <button type="button" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition hover:bg-white/5">
              Export CSV
            </button>
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-6 py-3 font-medium">Employee</th>
                  <th className="px-6 py-3 font-medium">Department</th>
                  <th className="px-6 py-3 font-medium">Check-in</th>
                  <th className="px-6 py-3 font-medium">Check-out</th>
                  <th className="px-6 py-3 font-medium">Total Hours</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {RECORDS.map(function (record) {
                  return (
                    <tr key={record.id} className="transition hover:bg-white/5">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {record.initials}
                          </div>
                          <span className="font-medium text-white">{record.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-300">{record.department}</td>
                      <td className="px-6 py-4 text-gray-300">{record.checkIn}</td>
                      <td className="px-6 py-4 text-gray-300">{record.checkOut}</td>
                      <td className="px-6 py-4 text-gray-300">{record.totalHours}</td>
                      <td className="px-6 py-4">{AttendanceBadge(record.status)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
            <p>Showing 1-8 of 234 records</p>
            <div className="flex items-center gap-2">
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">Previous</button>
              <button type="button" className="rounded-lg bg-indigo-500 px-3 py-1.5 font-medium text-white">1</button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">2</button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">Next</button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


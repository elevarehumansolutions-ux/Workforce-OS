"use client";

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

interface HeadcountBar {
  label: string;
  value: number;
}

const HEADCOUNT: HeadcountBar[] = [
  { label: "Engineering", value: 42 },
  { label: "Operations", value: 38 },
  { label: "Sales", value: 35 },
  { label: "Finance", value: 28 },
  { label: "Marketing", value: 24 },
  { label: "HR", value: 20 },
  { label: "Admin", value: 15 },
  { label: "Legal", value: 12 },
];

const ATTENDANCE_TREND: { month: string; value: number }[] = [
  { month: "Mar", value: 91.5 },
  { month: "Apr", value: 92.1 },
  { month: "May", value: 90.8 },
  { month: "Jun", value: 93.0 },
  { month: "Jul", value: 92.4 },
  { month: "Aug", value: 93.5 },
];

interface ReportRow {
  id: string;
  name: string;
  type: "Payroll" | "Attendance" | "Performance";
  generatedBy: string;
  date: string;
}

const REPORTS: ReportRow[] = [
  { id: "1", name: "Q2 Payroll Summary", type: "Payroll", generatedBy: "Ngozi Adeyemi", date: "Aug 18, 2026" },
  { id: "2", name: "August Attendance Audit", type: "Attendance", generatedBy: "Tariq Ibrahim", date: "Aug 15, 2026" },
  { id: "3", name: "Mid-Year Performance Review", type: "Performance", generatedBy: "Chinedu Obi", date: "Aug 12, 2026" },
];

function ReportTypeBadge(type: ReportRow["type"]) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (type === "Payroll") {
    badgeClass = badgeClass + "bg-indigo-500/15 text-indigo-300";
  } else if (type === "Attendance") {
    badgeClass = badgeClass + "bg-cyan-500/15 text-cyan-300";
  } else {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  }
  return <span className={badgeClass}>{type}</span>;
}

function LineChart() {
  const maxVal = 95;
  const minVal = 88;
  const width = 320;
  const height = 120;
  const points = ATTENDANCE_TREND.map(function (point, index) {
    const x = (index / (ATTENDANCE_TREND.length - 1)) * width;
    const y = height - ((point.value - minVal) / (maxVal - minVal)) * height;
    return x + "," + y;
  }).join(" ");

  return (
    <svg width="100%" height={height} viewBox={"0 0 " + width + " " + height} preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="#34d399" strokeWidth="2" />
    </svg>
  );
}

export default function ReportsPage() {
  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Reports")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Reports</p>
            <h1 className="text-xl font-bold text-white">Reports &amp; Analytics</h1>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="text"
              defaultValue="Aug 1 - 20, 2026"
              readOnly
              className="w-40 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2 text-sm text-gray-300 outline-none"
            />
            <button type="button" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition hover:bg-white/5">
              Export PDF
            </button>
            <button type="button" className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-gray-300 transition hover:bg-white/5">
              Export CSV
            </button>
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
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Employees</p>
              <p className="mt-2 text-2xl font-bold text-white">268</p>
              <span className="mt-1 inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">+12 active</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Avg Attendance Rate</p>
              <p className="mt-2 text-2xl font-bold text-white">94.2%</p>
              <span className="mt-1 inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">Healthy</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Open Leave Requests</p>
              <p className="mt-2 text-2xl font-bold text-white">8</p>
              <span className="mt-1 inline-block rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">Action req</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Avg Performance Score</p>
              <p className="mt-2 text-2xl font-bold text-white">4.2/5</p>
              <span className="mt-1 inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">Excellent</span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <h3 className="text-base font-semibold text-white">Department Headcount</h3>
              <div className="mt-6 flex h-40 items-end gap-3">
                {HEADCOUNT.map(function (bar) {
                  const heightPct = (bar.value / 42) * 100;
                  return (
                    <div key={bar.label} className="flex flex-1 flex-col items-center gap-2">
                      <div className="flex w-full items-end justify-center" style={{ height: "140px" }}>
                        <div className="w-full rounded-t-md bg-indigo-500" style={{ height: heightPct + "%" }} />
                      </div>
                      <span className="w-full truncate text-center text-[10px] text-gray-500">{bar.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-white">Monthly Attendance Trend</h3>
                <span className="text-sm font-medium text-emerald-400">Aug 93.5%</span>
              </div>
              <div className="mt-6">
                <LineChart />
                <div className="mt-2 flex justify-between text-[10px] text-gray-500">
                  {ATTENDANCE_TREND.map(function (point) {
                    return <span key={point.month}>{point.month}</span>;
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-6 py-3 font-medium">Report Name</th>
                  <th className="px-6 py-3 font-medium">Type</th>
                  <th className="px-6 py-3 font-medium">Generated By</th>
                  <th className="px-6 py-3 font-medium">Date</th>
                  <th className="px-6 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {REPORTS.map(function (report) {
                  return (
                    <tr key={report.id} className="transition hover:bg-white/5">
                      <td className="px-6 py-4 font-medium text-white">{report.name}</td>
                      <td className="px-6 py-4">{ReportTypeBadge(report.type)}</td>
                      <td className="px-6 py-4 text-gray-300">{report.generatedBy}</td>
                      <td className="px-6 py-4 text-gray-300">{report.date}</td>
                      <td className="px-6 py-4 text-gray-500">
                        <button type="button" aria-label="Download report">&#8681;</button>
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

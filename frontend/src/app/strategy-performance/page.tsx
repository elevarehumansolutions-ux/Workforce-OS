"use client";

const CEO_SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Strategy & Performance", href: "/strategy-performance" },
  { label: "Reports", href: "/reports" },
  { label: "Settings", href: "/settings" },
];

function CeoSidebarNav(activeLabel: string) {
  return (
    <nav className="flex flex-col gap-1 px-3">
      {CEO_SIDEBAR_ITEMS.map(function (item) {
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

function CeoSidebarShell(activeLabel: string) {
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
        {CeoSidebarNav(activeLabel)}
      </div>
      <div className="flex items-center gap-3 border-t border-white/10 px-6 pt-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          AO
        </div>
        <div>
          <p className="text-sm font-medium text-white">Adaeze Okafor</p>
          <p className="text-xs text-gray-500">CEO</p>
        </div>
      </div>
    </aside>
  );
}

interface Okr {
  id: string;
  title: string;
  progress: number;
  bullets: string[];
}

const CORPORATE_OKRS: Okr[] = [
  {
    id: "1",
    title: "Achieve 95% workforce attendance by Q4",
    progress: 72,
    bullets: [
      "Roll out automated localized scheduling engine (90% complete)",
      "Introduce real-time shift swaps in all regional hubs (65% complete)",
      "Introduce compliance rewards framework (65% complete)",
    ],
  },
  {
    id: "2",
    title: "Reduce employee turnover below 3%",
    progress: 58,
    bullets: [
      "Deploy manager alignment surveys monthly (80% complete)",
      "Launch fast-track executive promotion pathways (35% complete)",
    ],
  },
];

const DEPARTMENTAL_OKRS: Okr[] = [
  { id: "1", title: "Complete Core WOS MVP Deployment", progress: 84, bullets: [] },
  { id: "2", title: "Automate HR compliance verification", progress: 45, bullets: [] },
];

type KpiStatus = "On Track" | "Achieved" | "At Risk";

interface DeptKpi {
  id: string;
  metric: string;
  target: string;
  current: string;
  progress: number;
  owner: string;
  status: KpiStatus;
}

const DEPARTMENT_KPIS: DeptKpi[] = [
  { id: "1", metric: "Code Review T...", target: "<6hrs", current: "5.2hrs", progress: 80, owner: "...ngozi A.", status: "On Track" },
  { id: "2", metric: "Sprint Velocity", target: ">40pts", current: "42pts", progress: 100, owner: "...ndi O.", status: "Achieved" },
  { id: "3", metric: "Bug Resolution", target: "<48hrs", current: "54hrs", progress: 65, owner: "...suf I.", status: "At Risk" },
  { id: "4", metric: "Test Coverage", target: ">80%", current: "78%", progress: 78, owner: "...emi A.", status: "On Track" },
  { id: "5", metric: "Deployment Frequ...", target: "Daily", current: "0.8/day", progress: 80, owner: "...nara E.", status: "On Track" },
  { id: "6", metric: "Customer Satis...", target: ">4.5", current: "4.7", progress: 100, owner: "...raka N.", status: "Achieved" },
];

function KpiStatusBadge(status: KpiStatus) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (status === "On Track") {
    badgeClass = badgeClass + "bg-indigo-500/15 text-indigo-300";
  } else if (status === "Achieved") {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  } else {
    badgeClass = badgeClass + "bg-red-500/15 text-red-300";
  }
  return <span className={badgeClass}>{status}</span>;
}

function progressBarColor(progress: number) {
  if (progress >= 85) return "bg-emerald-500";
  if (progress >= 60) return "bg-indigo-500";
  return "bg-amber-500";
}

export default function StrategyPerformancePage() {
  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {CeoSidebarShell("Strategy & Performance")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Strategy &amp; Performance</p>
            <h1 className="text-xl font-bold text-white">Strategy &amp; Performance</h1>
            <p className="text-sm text-gray-500">Corporate Strategy Execution &amp; Active KPI Framework</p>
          </div>
          <div className="flex items-center gap-4">
            <select className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500">
              <option>Engineering</option>
              <option>Sales</option>
              <option>Marketing</option>
            </select>
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
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="flex flex-col gap-4">
              <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                <h3 className="mb-4 text-base font-semibold text-white">Corporate OKRs</h3>
                <div className="flex flex-col gap-5">
                  {CORPORATE_OKRS.map(function (okr) {
                    return (
                      <div key={okr.id}>
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-white">{okr.title}</p>
                          <span className="text-sm font-semibold text-indigo-300">{okr.progress}%</span>
                        </div>
                        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/10">
                          <div className="h-full rounded-full bg-indigo-500" style={{ width: okr.progress + "%" }} />
                        </div>
                        <ul className="mt-2 list-disc pl-5 text-xs text-gray-500">
                          {okr.bullets.map(function (bullet, index) {
                            return <li key={index}>{bullet}</li>;
                          })}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                <h3 className="mb-4 text-base font-semibold text-white">Departmental OKRs (Engineering)</h3>
                <div className="flex flex-col gap-4">
                  {DEPARTMENTAL_OKRS.map(function (okr) {
                    const barColor = progressBarColor(okr.progress);
                    return (
                      <div key={okr.id}>
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-white">{okr.title}</p>
                          <span className="text-sm font-semibold text-gray-300">{okr.progress}%</span>
                        </div>
                        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/10">
                          <div className={"h-full rounded-full " + barColor} style={{ width: okr.progress + "%" }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <button type="button" className="mt-4 w-full rounded-lg border border-white/10 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/5">
                  + Add OKR Objective
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-white">Active Department KPIs</h3>
                <span className="rounded-full bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-300">6 Active</span>
              </div>

              <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-white/10 uppercase tracking-wide text-gray-500">
                      <th className="px-3 py-2 font-medium">KPI Metric</th>
                      <th className="px-3 py-2 font-medium">Target</th>
                      <th className="px-3 py-2 font-medium">Current/Progress</th>
                      <th className="px-3 py-2 font-medium">Owner</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {DEPARTMENT_KPIS.map(function (kpi) {
                      const barColor = progressBarColor(kpi.progress);
                      return (
                        <tr key={kpi.id}>
                          <td className="px-3 py-3 font-medium text-white">{kpi.metric}</td>
                          <td className="px-3 py-3 text-gray-400">{kpi.target}</td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-300">{kpi.current}</span>
                              <div className="h-1.5 w-14 overflow-hidden rounded-full bg-white/10">
                                <div className={"h-full rounded-full " + barColor} style={{ width: kpi.progress + "%" }} />
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-3 text-gray-400">{kpi.owner}</td>
                          <td className="px-3 py-3">{KpiStatusBadge(kpi.status)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <p className="mt-3 text-[11px] text-gray-600">
                Source: &bull; Achieve 95% workforce attendance by Q4 &bull; Reduce employee turnover below 3%
              </p>

              <button type="button" className="mt-4 w-full rounded-lg bg-white/5 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/10">
                + Assign Departmental KPI
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

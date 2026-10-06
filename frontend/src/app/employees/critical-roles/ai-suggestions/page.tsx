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

function TopBar(breadcrumb: string, subtitle: string) {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
      <div>
        <p className="text-xs text-gray-500">
          <span className="mr-1 text-red-400">&#9873;</span>
          {breadcrumb}
        </p>
        <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
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

type CriticalityType = "Operational" | "Revenue" | "Vacancy Risk";
type RiskLevel = "Low" | "Medium" | "High";

interface Suggestion {
  id: string;
  roleTitle: string;
  department: string;
  rationale: string;
  criticalityType: CriticalityType;
  riskLevel: RiskLevel;
}

const SUGGESTIONS: Suggestion[] = [
  { id: "1", roleTitle: "Chief Technology Officer", department: "Engineering", rationale: "Sole engineer overseeing all technical infrastructure", criticalityType: "Operational", riskLevel: "High" },
  { id: "2", roleTitle: "Head of Sales", department: "Sales & Marketing", rationale: "No identified successor in reporting chain", criticalityType: "Revenue", riskLevel: "High" },
  { id: "3", roleTitle: "Lead Cloud Architect", department: "Engineering", rationale: "Sole role with system-wide deployment access", criticalityType: "Operational", riskLevel: "Medium" },
  { id: "4", roleTitle: "Finance Controller", department: "Finance", rationale: "Key signatory on all vendor contracts", criticalityType: "Revenue", riskLevel: "Low" },
  { id: "5", roleTitle: "HR Business Partner", department: "Human Resources", rationale: "Only HR liaison across 3 departments", criticalityType: "Vacancy Risk", riskLevel: "Medium" },
  { id: "6", roleTitle: "DevOps Lead", department: "Engineering", rationale: "Manages critical CI/CD pipeline with no backup", criticalityType: "Operational", riskLevel: "Low" },
];

function CriticalityBadge(type: CriticalityType) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (type === "Operational") {
    badgeClass = badgeClass + "bg-indigo-500/15 text-indigo-300";
  } else if (type === "Revenue") {
    badgeClass = badgeClass + "bg-cyan-500/15 text-cyan-300";
  } else {
    badgeClass = badgeClass + "bg-amber-500/15 text-amber-300";
  }
  return <span className={badgeClass}>{type}</span>;
}

function RiskBadge(risk: RiskLevel) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (risk === "High") {
    badgeClass = badgeClass + "bg-red-500/15 text-red-300";
  } else if (risk === "Medium") {
    badgeClass = badgeClass + "bg-amber-500/15 text-amber-300";
  } else {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  }
  return <span className={badgeClass}>{risk}</span>;
}

export default function CriticalRolesAiSuggestionsPage() {
  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        {TopBar(
          "Employees > Critical Roles > AI Suggestions",
          "Review AI-generated recommendations generated by the Elevare workforce analytics engine"
        )}

        <main className="flex-1 px-8 py-8">
          <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-[#0d1220]/80 px-6 py-4 shadow-xl">
            <div className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="text-sm font-medium text-white">AI Engine Active</span>
              <span className="text-sm text-gray-500">{SUGGESTIONS.length} roles flagged for review</span>
            </div>
            <button
              type="button"
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Approve All
            </button>
          </div>

          <div className="mt-6 flex flex-col gap-4">
            {SUGGESTIONS.map(function (suggestion) {
              return (
                <div key={suggestion.id} className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">
                        {suggestion.roleTitle}
                        <span className="mx-2 text-gray-600">&bull;</span>
                        <span className="font-normal text-gray-400">{suggestion.department}</span>
                        <span className="ml-2 rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-medium text-indigo-300">
                          AI SUGGESTED
                        </span>
                      </p>
                      <p className="mt-1 text-sm text-gray-500">AI Rationale: {suggestion.rationale}</p>
                      <div className="mt-2 flex gap-2">
                        {CriticalityBadge(suggestion.criticalityType)}
                        {RiskBadge(suggestion.riskLevel)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="rounded-lg bg-emerald-500/15 px-3 py-1.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/25"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-white/10 px-3 py-1.5 text-sm font-medium text-gray-300 transition hover:bg-white/5"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="rounded-lg bg-red-500/15 px-3 py-1.5 text-sm font-medium text-red-300 transition hover:bg-red-500/25"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}


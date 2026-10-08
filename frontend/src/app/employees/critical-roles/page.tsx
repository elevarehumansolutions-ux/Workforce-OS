"use client";

import { useRouter } from "next/navigation";

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

interface CriticalRole {
  id: string;
  roleTitle: string;
  department: string;
  currentHolder: string;
  criticalityType: CriticalityType;
  riskLevel: RiskLevel;
  successorIdentified: boolean;
}

const CRITICAL_ROLES: CriticalRole[] = [
  { id: "1", roleTitle: "Chief Technology Officer", department: "Engineering", currentHolder: "Emeka Nwankwo", criticalityType: "Operational", riskLevel: "Medium", successorIdentified: true },
  { id: "2", roleTitle: "Head of Sales", department: "Sales & Marketing", currentHolder: "— (Vacant)", criticalityType: "Revenue", riskLevel: "High", successorIdentified: false },
  { id: "3", roleTitle: "Lead Cloud Architect", department: "Engineering", currentHolder: "Amara Eze", criticalityType: "Operational", riskLevel: "Low", successorIdentified: true },
  { id: "4", roleTitle: "Finance Controller", department: "Finance", currentHolder: "Kemi Adebayo", criticalityType: "Revenue", riskLevel: "Low", successorIdentified: true },
  { id: "5", roleTitle: "HR Business Partner", department: "Human Resources", currentHolder: "Femi Alao", criticalityType: "Vacancy Risk", riskLevel: "Medium", successorIdentified: false },
  { id: "6", roleTitle: "DevOps Lead", department: "Engineering", currentHolder: "Tunde Balogun", criticalityType: "Operational", riskLevel: "Low", successorIdentified: true },
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

export default function CriticalRolesPage() {
  const router = useRouter();

  const totalCount = CRITICAL_ROLES.length;
  const filledCount = CRITICAL_ROLES.filter(function (r) {
    return r.currentHolder !== "— (Vacant)";
  }).length;
  const vacantCount = totalCount - filledCount;

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        {TopBar(
          "Employees > Critical Roles",
          "Revenue-critical, operationally critical, and high-risk vacancy roles across the organization"
        )}

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Total Critical Roles</p>
              <p className="mt-2 text-2xl font-bold text-white">{totalCount}</p>
              <p className="mt-1 text-xs text-gray-500">Across all departments</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Currently Filled</p>
              <p className="mt-2 text-2xl font-bold text-emerald-400">{filledCount}</p>
              <p className="mt-1 text-xs text-gray-500">Active FTEs in role</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Vacant / At Risk</p>
              <p className="mt-2 text-2xl font-bold text-red-400">{vacantCount}</p>
              <p className="mt-1 text-xs text-gray-500">Requires urgent action</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-5 shadow-xl">
              <p className="text-xs uppercase tracking-wide text-gray-500">Avg Tenure in Role</p>
              <p className="mt-2 text-2xl font-bold text-white">2.4 yrs</p>
              <p className="mt-1 text-xs text-gray-500">Stability baseline</p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-white">Critical Roles Registry</h3>
                <button
                  type="button"
                  onClick={() => router.push("/employees/critical-roles/ai-suggestions")}
                  className="mt-1 text-sm font-medium text-indigo-400 hover:text-indigo-300"
                >
                  Review New Suggestions &rarr;
                </button>
              </div>
              <p className="text-xs text-gray-500">Last reviewed during onboarding on Aug 15, 2026</p>
            </div>

            <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-3 font-medium">Role Title</th>
                    <th className="px-4 py-3 font-medium">Department</th>
                    <th className="px-4 py-3 font-medium">Current Holder</th>
                    <th className="px-4 py-3 font-medium">Criticality Type</th>
                    <th className="px-4 py-3 font-medium">Risk Level</th>
                    <th className="px-4 py-3 font-medium">Successor Identified</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {CRITICAL_ROLES.map(function (role) {
                    let successorClass = "text-sm font-medium ";
                    if (role.successorIdentified) {
                      successorClass = successorClass + "text-emerald-400";
                    } else {
                      successorClass = successorClass + "text-red-400";
                    }
                    return (
                      <tr key={role.id} className="transition hover:bg-white/5">
                        <td className="px-4 py-4 font-medium text-white">{role.roleTitle}</td>
                        <td className="px-4 py-4 text-gray-300">{role.department}</td>
                        <td className="px-4 py-4 text-gray-300">{role.currentHolder}</td>
                        <td className="px-4 py-4">{CriticalityBadge(role.criticalityType)}</td>
                        <td className="px-4 py-4">{RiskBadge(role.riskLevel)}</td>
                        <td className="px-4 py-4">
                          <span className={successorClass}>{role.successorIdentified ? "Yes" : "No"}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


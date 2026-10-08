import type { ReactNode } from "react";
import Link from "next/link";

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

interface AppShellProps {
  activeLabel: string;
  title: string;
  breadcrumb?: string;
  // Shown at the bottom of the sidebar once known.
  userName?: string;
  userRole?: string;
  actions?: ReactNode;
  children: ReactNode;
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/);
  let out = "";
  for (const p of parts.slice(0, 2)) {
    out = out + p.charAt(0).toUpperCase();
  }
  return out || "?";
}

export default function AppShell(props: AppShellProps) {
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
            <span className="text-base font-bold text-white">Elevare</span>
          </div>
          <nav className="flex flex-col gap-1 px-3">
            {SIDEBAR_ITEMS.map(function (item) {
              const isActive = item.label === props.activeLabel;
              let linkClass = "rounded-lg px-3 py-2.5 text-sm transition ";
              if (isActive) {
                linkClass = linkClass + "bg-indigo-500/15 text-indigo-300 font-medium";
              } else {
                linkClass = linkClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
              }
              return (
                <Link key={item.label} href={item.href} className={linkClass}>
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        {props.userName ? (
          <div className="flex items-center gap-3 border-t border-white/10 px-6 pt-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
              {initialsOf(props.userName)}
            </div>
            <div>
              <p className="text-sm font-medium text-white">{props.userName}</p>
              {props.userRole ? <p className="text-xs text-gray-500">{props.userRole}</p> : null}
            </div>
          </div>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-8 py-5">
          <div>
            {props.breadcrumb ? <p className="text-xs text-gray-500">{props.breadcrumb}</p> : null}
            <h1 className="text-xl font-bold text-white">{props.title}</h1>
          </div>
          {props.actions ? <div className="flex items-center gap-3">{props.actions}</div> : null}
        </div>
        <main className="flex-1 space-y-6 px-8 py-8">{props.children}</main>
      </div>
    </div>
  );
}

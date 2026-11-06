"use client";

import type { ReactNode } from "react";
import SidebarNav from "@/components/SidebarNav";
import Logo from "@/components/Logo";

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
            <Logo size={36} textClassName="text-base font-bold text-white" />
          </div>
          <SidebarNav activeLabel={props.activeLabel} />
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
"use client";

import type { ReactNode } from "react";
import SidebarNav from "@/components/SidebarNav";
import Logo from "@/components/Logo";
import MobileNav from "@/components/MobileNav";
import UserMenu from "@/components/UserMenu";

interface AppShellProps {
  activeLabel: string;
  title: string;
  breadcrumb?: string;
  // No longer used: the menu at the bottom of the sidebar loads the signed-in person itself.
  // Still accepted so the pages that pass these keep compiling.
  userName?: string;
  userRole?: string;
  actions?: ReactNode;
  children: ReactNode;
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
        <UserMenu />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav activeLabel={props.activeLabel} />
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-4 sm:px-8 sm:py-5">
          <div>
            {props.breadcrumb ? <p className="text-xs text-gray-500">{props.breadcrumb}</p> : null}
            <h1 className="text-xl font-bold text-white">{props.title}</h1>
          </div>
          {props.actions ? <div className="flex items-center gap-3">{props.actions}</div> : null}
        </div>
        <main className="flex-1 space-y-6 px-4 py-6 sm:px-8 sm:py-8">{props.children}</main>
      </div>
    </div>
  );
}
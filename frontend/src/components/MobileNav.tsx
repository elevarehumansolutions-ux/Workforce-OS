"use client";

import { useState } from "react";
import Logo from "@/components/Logo";
import SidebarNav from "@/components/SidebarNav";
import UserMenu from "@/components/UserMenu";
import { useWaitingCount } from "@/lib/waitingCount";

// Below the desktop width the sidebar is hidden, so this bar takes its place: a menu button that
// slides the same menu in from the left. It is not drawn on desktop (lg and wider).
export default function MobileNav(props: { activeLabel: string }) {
  // Each page draws its own shell, so moving to another page starts with the menu closed again.
  const [open, setOpen] = useState(false);
  const waiting = useWaitingCount();

  return (
    <div className="lg:hidden">
      <div className="flex items-center gap-3 border-b border-white/10 bg-[#0a0e1a] px-4 py-3">
        <button
          type="button"
          aria-label="Open menu"
          onClick={function () { setOpen(true); }}
          className="relative rounded-lg border border-white/10 px-3 py-2 text-lg leading-none text-gray-200 hover:bg-white/5"
        >
          ☰
          {/* The menu is closed on a phone, so a dot says that tasks are waiting inside it. */}
          {waiting > 0 ? <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-red-500" aria-label="Tasks waiting" /> : null}
        </button>
        <Logo size={28} textClassName="text-sm font-bold text-white" />
        <span className="ml-auto truncate text-sm text-gray-400">{props.activeLabel}</span>
      </div>

      {open ? (
        <div className="fixed inset-0 z-40 flex">
          <aside className="flex w-72 max-w-[85vw] flex-col justify-between overflow-y-auto border-r border-white/10 bg-[#0a0e1a] py-6 shadow-2xl">
            {/* A click on any link inside closes the menu, even a link to the page you are already on. */}
            <div onClick={function () { setOpen(false); }}>
              <div className="mb-6 flex items-center gap-3 px-6">
                <Logo size={32} textClassName="text-base font-bold text-white" />
              </div>
              <SidebarNav activeLabel={props.activeLabel} />
            </div>
            <UserMenu />
          </aside>
          <button type="button" aria-label="Close menu" className="flex-1 bg-black/60" onClick={function () { setOpen(false); }} />
        </div>
      ) : null}
    </div>
  );
}

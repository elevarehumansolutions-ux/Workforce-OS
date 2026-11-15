"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { loadMe } from "@/lib/settings";
import { itemsForRole } from "@/lib/navigation";

// The role is looked up once and kept, so moving between pages does not
// call /auth/me again just to draw the menu.
let knownRole = "";

// The one sidebar menu for the whole app: AppShell uses it, and so do the few
// older pages that draw their own shell.
export default function SidebarNav(props: { activeLabel: string }) {
  const [role, setRole] = useState(knownRole);

  useEffect(function () {
    if (knownRole !== "") {
      return;
    }
    loadMe()
      .then(function (me) {
        knownRole = me.role;
        setRole(me.role);
      })
      .catch(function () {
        // Not signed in or offline: keep the smallest menu. The page itself
        // reports the real error.
      });
  }, []);

  return (
    <nav className="flex flex-col gap-1 px-3">
      {itemsForRole(role).map(function (item) {
        const isActive = item.label === props.activeLabel;
        let linkClass = "rounded-lg px-3 py-2.5 text-sm transition ";
        if (isActive) {
          linkClass = linkClass + "bg-indigo-500/15 text-indigo-300 font-medium";
        } else {
          linkClass = linkClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
        }
        if (item.soon) {
          // Phase 2 features have no backend yet: shown, but not a link.
          return (
            <span key={item.label} className="flex items-center justify-between rounded-lg px-3 py-2.5 text-sm text-gray-600">
              {item.label}
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-500">Soon</span>
            </span>
          );
        }
        return (
          <Link key={item.label} href={item.href} className={linkClass}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

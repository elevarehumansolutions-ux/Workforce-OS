"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { loadMe } from "@/lib/settings";
import type { MeData } from "@/lib/settings";
import { roleLabel } from "@/lib/tasks";
import { signOut } from "@/lib/session";

// Kept between pages so the name does not flicker in and out on every page change.
let knownMe: MeData | null = null;

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/);
  let out = "";
  for (const p of parts.slice(0, 2)) {
    out = out + p.charAt(0).toUpperCase();
  }
  return out || "?";
}

// The signed-in person at the bottom of the menu: click for "My profile" and "Sign out".
export default function UserMenu() {
  const router = useRouter();
  const [me, setMe] = useState<MeData | null>(knownMe);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(function () {
    if (knownMe !== null) {
      return;
    }
    loadMe()
      .then(function (loaded) {
        knownMe = loaded;
        setMe(loaded);
      })
      .catch(function () {
        // Not signed in or offline: the page itself reports the real error.
      });
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
    knownMe = null;
    router.push("/login");
  }

  if (!me) {
    return null;
  }

  return (
    <div className="relative border-t border-white/10 px-3 pt-4">
      {open ? (
        <>
          {/* Clicking anywhere outside the menu closes it. */}
          <button type="button" aria-label="Close menu" className="fixed inset-0 z-10 cursor-default" onClick={function () { setOpen(false); }} />
          <div className="absolute bottom-full left-3 right-3 z-20 mb-2 rounded-xl border border-white/10 bg-[#0d1220] p-1 shadow-2xl">
            <Link
              href="/profile"
              onClick={function () { setOpen(false); }}
              className="block rounded-lg px-3 py-2 text-sm text-gray-200 hover:bg-white/5"
            >
              My profile
            </Link>
            <button
              type="button"
              disabled={signingOut}
              onClick={handleSignOut}
              className="block w-full rounded-lg px-3 py-2 text-left text-sm text-red-300 hover:bg-white/5 disabled:opacity-60"
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </>
      ) : null}

      <button
        type="button"
        onClick={function () { setOpen(!open); }}
        aria-expanded={open}
        className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-white/5"
      >
        <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          {initialsOf(me.fullName)}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-white">{me.fullName}</span>
          <span className="block truncate text-xs text-gray-500">{roleLabel(me.role)}</span>
        </span>
      </button>
    </div>
  );
}

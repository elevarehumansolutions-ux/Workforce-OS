"use client";

import AppShell from "@/components/AppShell";

interface ComingSoonProps {
  // Must match the sidebar item's label so it shows as the active one.
  activeLabel: string;
  title: string;
  what: string;
}

// For features that are planned (Phase 2) but have no backend yet. It says
// so plainly instead of showing made-up numbers.
export default function ComingSoon(props: ComingSoonProps) {
  return (
    <AppShell activeLabel={props.activeLabel} title={props.title}>
      <div className="mx-auto max-w-xl rounded-2xl border border-white/10 bg-[#0a0e1a] p-10 text-center">
        <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium uppercase tracking-wide text-indigo-300">
          Coming soon
        </span>
        <h2 className="mt-4 text-lg font-semibold text-white">{props.title} is not available yet</h2>
        <p className="mt-2 text-sm text-gray-400">{props.what}</p>
      </div>
    </AppShell>
  );
}

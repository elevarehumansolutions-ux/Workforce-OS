"use client";

import AppShell from "@/components/AppShell";
import SecuritySection from "@/components/settings/SecuritySection";
import { formatDateTime, roleLabel } from "@/lib/tasks";
import { loadMe } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

// "My profile": who you are signed in as, plus changing your password and signing out.
// The password and sign-out part is the same Security section that lives in Settings.
export default function ProfilePage() {
  const state = useLoad(
    "profile-me",
    function () {
      return loadMe();
    },
    "Couldn't load your account. Check your connection and try again."
  );
  const me = state.data;

  return (
    <AppShell activeLabel="" title="My profile" breadcrumb="Dashboard > My profile">
      {state.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {state.error ? (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p>
      ) : null}

      {me ? (
        <>
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <h2 className="text-base font-semibold text-white">{me.fullName}</h2>
            <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-gray-500">Email</dt>
                <dd className="mt-1 text-gray-200">{me.email}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Role</dt>
                <dd className="mt-1 text-gray-200">{roleLabel(me.role)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Company</dt>
                <dd className="mt-1 text-gray-200">{me.organization && me.organization.name ? me.organization.name : "Not set"}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Last signed in</dt>
                <dd className="mt-1 text-gray-200">{me.lastLoginAt ? formatDateTime(me.lastLoginAt) : "Not recorded"}</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            <SecuritySection me={me} />
          </div>
        </>
      ) : null}
    </AppShell>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { roleLabel } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { isHrRole, loadMe } from "@/lib/settings";
import AuditLogSection from "@/components/settings/AuditLogSection";
import CompanyProfileSection from "@/components/settings/CompanyProfileSection";
import DepartmentsSection from "@/components/settings/DepartmentsSection";
import GeneralSection from "@/components/settings/GeneralSection";
import IntegrationsSection from "@/components/settings/IntegrationsSection";
import NotificationsSection from "@/components/settings/NotificationsSection";
import RolesSection from "@/components/settings/RolesSection";
import SecuritySection from "@/components/settings/SecuritySection";

const SECTIONS = [
  "General",
  "Company Profile",
  "Departments",
  "Roles & Permissions",
  "Notifications",
  "Integrations",
  "Security",
  "Audit Log",
];

export default function SettingsPage() {
  const [active, setActive] = useState("General");
  const state = useLoad(
    "settings-me",
    function () {
      return loadMe();
    },
    "Couldn't load your account. Check your connection and try again."
  );
  const me = state.data;

  return (
    <AppShell
      activeLabel="Settings"
      title="System settings"
      breadcrumb="Dashboard > Settings"
      userName={me ? me.fullName : undefined}
      userRole={me ? roleLabel(me.role) : undefined}
    >
      {state.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {state.error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}

      {me ? (
        <div className="flex flex-col gap-6 lg:flex-row">
          <nav className="flex gap-1 overflow-x-auto lg:w-60 lg:flex-shrink-0 lg:flex-col">
            {SECTIONS.map(function (s) {
              const isActive = s === active;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={function () {
                    setActive(s);
                  }}
                  className={
                    "whitespace-nowrap rounded-lg px-4 py-2.5 text-left text-sm " +
                    (isActive ? "bg-indigo-500/15 font-medium text-indigo-300" : "text-gray-400 hover:bg-white/5 hover:text-gray-200")
                  }
                >
                  {s}
                </button>
              );
            })}
            {isHrRole(me.role) ? (
              <Link href="/settings/billing-ai-usage" className="whitespace-nowrap rounded-lg px-4 py-2.5 text-sm text-gray-400 hover:bg-white/5 hover:text-gray-200">
                Billing &amp; AI Usage
              </Link>
            ) : null}
          </nav>

          <div className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
            {active === "General" ? <GeneralSection me={me} /> : null}
            {active === "Company Profile" ? <CompanyProfileSection me={me} /> : null}
            {active === "Departments" ? <DepartmentsSection me={me} /> : null}
            {active === "Roles & Permissions" ? <RolesSection me={me} /> : null}
            {active === "Notifications" ? <NotificationsSection me={me} /> : null}
            {active === "Integrations" ? <IntegrationsSection me={me} /> : null}
            {active === "Security" ? <SecuritySection me={me} /> : null}
            {active === "Audit Log" ? <AuditLogSection me={me} /> : null}
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

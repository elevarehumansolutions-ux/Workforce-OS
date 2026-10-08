"use client";

import { useState } from "react";

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

const SETTINGS_SECTIONS = ["General", "Company Profile", "Departments", "Roles & Permissions", "Notifications", "Integrations", "Security", "Audit Log"];

interface GeneralSettings {
  companyName: string;
  industry: string;
  country: string;
  timezone: string;
  currency: string;
  fiscalYearStart: string;
  dateFormat: string;
}

export default function SystemSettingsPage() {
  const [activeSection, setActiveSection] = useState("General");
  const [settings, setSettings] = useState<GeneralSettings>({
    companyName: "Elevare Technologies Ltd",
    industry: "Technology / SaaS",
    country: "Nigeria",
    timezone: "WAT (UTC+1)",
    currency: "NGN (N)",
    fiscalYearStart: "January",
    dateFormat: "DD/MM/YYYY",
  });

  function updateField(field: keyof GeneralSettings, value: string) {
    setSettings(function (prev) {
      return { ...prev, [field]: value };
    });
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Settings")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Settings</p>
            <h1 className="text-xl font-bold text-white">System Settings</h1>
          </div>
          <div className="flex items-center gap-4">
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">1</span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">WOS MVP Ready</span>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
            <div className="flex flex-col gap-1">
              {SETTINGS_SECTIONS.map(function (section) {
                const isActive = section === activeSection;
                let itemClass = "rounded-lg px-3 py-2.5 text-left text-sm transition ";
                if (isActive) {
                  itemClass = itemClass + "bg-indigo-500 text-white font-medium";
                } else {
                  itemClass = itemClass + "text-gray-400 hover:bg-white/5 hover:text-gray-200";
                }
                return (
                  <button key={section} type="button" onClick={() => setActiveSection(section)} className={itemClass}>
                    {section}
                  </button>
                );
              })}
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              {activeSection === "General" ? (
                <>
                  <h3 className="text-base font-semibold text-white">General Settings</h3>
                  <p className="mt-1 text-sm text-gray-500">Configure primary regional metadata for the Elevare instance.</p>

                  <div className="mt-6 grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Company Name</label>
                      <input
                        type="text"
                        value={settings.companyName}
                        onChange={(e) => updateField("companyName", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Industry</label>
                      <input
                        type="text"
                        value={settings.industry}
                        onChange={(e) => updateField("industry", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Country</label>
                      <input
                        type="text"
                        value={settings.country}
                        onChange={(e) => updateField("country", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Timezone</label>
                      <input
                        type="text"
                        value={settings.timezone}
                        onChange={(e) => updateField("timezone", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Currency</label>
                      <input
                        type="text"
                        value={settings.currency}
                        onChange={(e) => updateField("currency", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Fiscal Year Start</label>
                      <input
                        type="text"
                        value={settings.fiscalYearStart}
                        onChange={(e) => updateField("fiscalYearStart", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Date Format</label>
                      <input
                        type="text"
                        value={settings.dateFormat}
                        onChange={(e) => updateField("dateFormat", e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end border-t border-white/10 pt-6">
                    <button
                      type="button"
                      onClick={() => console.log("Saved settings:", settings)}
                      className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600"
                    >
                      Save Changes
                    </button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-500">{activeSection} content coming soon.</p>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

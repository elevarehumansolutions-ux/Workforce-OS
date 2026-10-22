"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";
import { SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS, isHrRole, monthName, subscriptionClasses, subscriptionLabel } from "@/lib/settings";
import type { SectionProps } from "./types";

interface BusinessDna {
  organization_name: string | null;
  timezone: string;
  industry: string | null;
}

const INDUSTRY_OPTIONS = [
  "Information Technology",
  "Financial Services",
  "Manufacturing",
  "Healthcare",
  "Retail & E-commerce",
  "Agriculture",
  "Logistics & Transportation",
  "Other",
];

interface IntlWithSupportedValuesOf {
  supportedValuesOf?: (key: string) => string[];
}

function timezoneOptions(): string[] {
  const intl = Intl as unknown as IntlWithSupportedValuesOf;
  if (typeof intl.supportedValuesOf === "function") {
    try {
      return intl.supportedValuesOf("timeZone");
    } catch {
      // fall through
    }
  }
  return ["Africa/Lagos", "Africa/Nairobi", "Europe/London", "America/New_York", "Asia/Dubai"];
}

export default function GeneralSection(props: SectionProps) {
  const org = props.me.organization;
  const canEdit = isHrRole(props.me.role);
  const [reloadCounter, setReloadCounter] = useState(0);
  const state = useLoad<BusinessDna>(
    "general|" + reloadCounter,
    function () {
      return apiFetch<BusinessDna>("/business-dna", { method: "GET" });
    },
    "Couldn't load the company settings."
  );

  // Edits are kept as differences from what is saved, so nothing is sent that wasn't changed.
  const [edits, setEdits] = useState<{ name?: string; industry?: string; timezone?: string }>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  // No profile yet is a normal state for a brand-new organization.
  const notSetUp = state.status === 404;
  const dna = state.data;
  const savedName = dna && dna.organization_name ? dna.organization_name : org && org.name ? org.name : "";
  const savedIndustry = dna && dna.industry ? dna.industry : "";
  const savedTimezone = dna ? dna.timezone : "Africa/Lagos";

  const name = edits.name !== undefined ? edits.name : savedName;
  const industry = edits.industry !== undefined ? edits.industry : savedIndustry;
  const timezone = edits.timezone !== undefined ? edits.timezone : savedTimezone;
  const dirty = Object.keys(edits).length > 0;

  const industries = INDUSTRY_OPTIONS.indexOf(industry) === -1 && industry ? [industry].concat(INDUSTRY_OPTIONS) : INDUSTRY_OPTIONS;
  const zones = timezoneOptions();
  const timezones = zones.indexOf(timezone) === -1 ? [timezone].concat(zones) : zones;

  async function save() {
    setError("");
    setSaved(false);
    const body: Record<string, string> = {};
    if (edits.name !== undefined) {
      if (!edits.name.trim()) {
        setError("The company name can't be empty.");
        return;
      }
      body.organization_name = edits.name.trim();
    }
    if (edits.industry !== undefined && edits.industry) body.industry = edits.industry;
    if (edits.timezone !== undefined && edits.timezone) body.timezone = edits.timezone;
    if (Object.keys(body).length === 0) return;
    setSaving(true);
    try {
      await apiFetch("/business-dna", { method: "PUT", body: body });
      setEdits({});
      setSaved(true);
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your changes. Check your connection and try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-white">General settings</h3>
      <p className="mt-1 text-sm text-gray-500">The basics of your organization: its name, industry and where &quot;today&quot; starts and ends.</p>

      {state.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}
      {state.error && !notSetUp ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}
      {notSetUp ? (
        <p className="mt-6 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-gray-400">
          Your company details haven&apos;t been saved yet.
          {canEdit ? " Fill them in below and save." : " An HR administrator needs to fill them in."}
        </p>
      ) : null}

      {!state.loading && (!state.error || notSetUp) ? (
        <>
          {error ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
          {saved ? <p className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">Saved.</p> : null}

          <div className="mt-6 grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
            <div>
              <label className={SETTINGS_LABEL_CLASS}>Company name</label>
              <input
                type="text"
                value={name}
                disabled={!canEdit}
                onChange={function (e) {
                  setEdits({ ...edits, name: e.target.value });
                }}
                className={SETTINGS_INPUT_CLASS}
              />
            </div>
            <div>
              <label className={SETTINGS_LABEL_CLASS}>Industry</label>
              <select
                value={industry}
                disabled={!canEdit}
                onChange={function (e) {
                  setEdits({ ...edits, industry: e.target.value });
                }}
                className={SETTINGS_INPUT_CLASS}
              >
                <option value="">Choose an industry</option>
                {industries.map(function (i) {
                  return (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  );
                })}
              </select>
            </div>
            <div>
              <label className={SETTINGS_LABEL_CLASS}>Timezone</label>
              <select
                value={timezone}
                disabled={!canEdit}
                onChange={function (e) {
                  setEdits({ ...edits, timezone: e.target.value });
                }}
                className={SETTINGS_INPUT_CLASS}
              >
                {timezones.map(function (z) {
                  return (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  );
                })}
              </select>
              <p className="mt-1 text-xs text-gray-500">Decides where midnight falls, for example when unfinished attendance is closed for the day.</p>
            </div>
            <div>
              <label className={SETTINGS_LABEL_CLASS}>Financial year starts in</label>
              <input type="text" value={org ? monthName(org.fiscal_year_start_month) : ""} disabled className={SETTINGS_INPUT_CLASS} />
              <p className="mt-1 text-xs text-gray-500">Quarter-end reviews and KPI periods follow this. It can&apos;t be changed from here yet.</p>
            </div>
          </div>

          {canEdit ? (
            <div className="mt-8 flex justify-end border-t border-white/10 pt-6">
              <button
                type="button"
                disabled={saving || !dirty}
                onClick={save}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          ) : (
            <p className="mt-6 text-xs text-gray-500">Only an HR administrator can change these.</p>
          )}
        </>
      ) : null}

      {org ? (
        <div className="mt-10 border-t border-white/10 pt-6">
          <h4 className="text-sm font-semibold text-white">Subscription</h4>
          <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-gray-500">Status</dt>
              <dd className="mt-1">
                <span className={"rounded px-2 py-0.5 text-xs font-medium " + subscriptionClasses(org.subscription_status)}>
                  {subscriptionLabel(org.subscription_status)}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">{org.subscription_status === "trial" ? "Trial ends" : "Renews or expires"}</dt>
              <dd className="mt-1 text-gray-200">{org.subscription_expires_at ? formatDateTime(org.subscription_expires_at) : "Not set"}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Account created</dt>
              <dd className="mt-1 text-gray-200">{formatDateTime(org.created_at)}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </div>
  );
}

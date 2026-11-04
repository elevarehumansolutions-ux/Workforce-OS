"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS, isHrRole } from "@/lib/settings";
import type { SectionProps } from "./types";

interface CoreValue {
  id: string;
  value: string;
}

interface BusinessDna {
  products_services_description: string | null;
  vision: string | null;
  mission: string | null;
  business_model: string | null;
  performance_philosophy: string | null;
  workforce_rules: string | null;
  revenue_drivers: string | null;
  operational_drivers: string | null;
  customer_value_drivers: string | null;
  capital_investment_amount: string | number | null;
  core_values: CoreValue[];
}

type TextField =
  | "vision"
  | "mission"
  | "products_services_description"
  | "business_model"
  | "performance_philosophy"
  | "workforce_rules"
  | "revenue_drivers"
  | "operational_drivers"
  | "customer_value_drivers";

const TEXT_FIELDS: { field: TextField; label: string; hint: string }[] = [
  { field: "vision", label: "Vision", hint: "Where the company is going." },
  { field: "mission", label: "Mission", hint: "Why the company exists and who it serves." },
  { field: "products_services_description", label: "Products and services", hint: "What the company sells or delivers." },
  { field: "business_model", label: "Business model", hint: "How the company makes money." },
  { field: "revenue_drivers", label: "Revenue drivers", hint: "The things that bring in revenue." },
  { field: "operational_drivers", label: "Operational drivers", hint: "The things that keep the business running well." },
  { field: "customer_value_drivers", label: "Customer value drivers", hint: "What customers value most." },
  { field: "performance_philosophy", label: "Performance philosophy", hint: "How the company thinks about good performance." },
  { field: "workforce_rules", label: "Workforce rules", hint: "House rules that apply to the workforce." },
];

export default function CompanyProfileSection(props: SectionProps) {
  const canEdit = isHrRole(props.me.role);
  const [reloadCounter, setReloadCounter] = useState(0);
  const state = useLoad<BusinessDna>(
    "profile|" + reloadCounter,
    function () {
      return apiFetch<BusinessDna>("/business-dna", { method: "GET" });
    },
    "Couldn't load the company profile."
  );

  const [edits, setEdits] = useState<Partial<Record<TextField | "capital", string>>>({});
  const [newValue, setNewValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [busyValueId, setBusyValueId] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const dna = state.data;
  const notSetUp = state.status === 404;
  const dirty = Object.keys(edits).length > 0;

  function shown(field: TextField): string {
    if (edits[field] !== undefined) return edits[field] as string;
    return dna && dna[field] ? (dna[field] as string) : "";
  }

  function shownCapital(): string {
    if (edits.capital !== undefined) return edits.capital;
    return dna && dna.capital_investment_amount !== null && dna.capital_investment_amount !== undefined ? String(dna.capital_investment_amount) : "";
  }

  async function save() {
    setError("");
    setSaved(false);
    const body: Record<string, unknown> = {};
    for (const f of TEXT_FIELDS) {
      const value = edits[f.field];
      if (value !== undefined) body[f.field] = value.trim() === "" ? null : value.trim();
    }
    if (edits.capital !== undefined) {
      const raw = edits.capital.trim();
      if (raw === "") {
        body.capital_investment_amount = null;
      } else if (!Number.isFinite(Number(raw)) || Number(raw) < 0) {
        setError("The capital investment amount must be a number.");
        return;
      } else {
        body.capital_investment_amount = Number(raw);
      }
    }
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

  async function addValue() {
    const value = newValue.trim();
    if (!value) return;
    setError("");
    setBusyValueId("new");
    try {
      await apiFetch("/business-dna/core-values", { method: "POST", body: { value: value } });
      setNewValue("");
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add that value. Check your connection and try again.");
    } finally {
      setBusyValueId("");
    }
  }

  async function removeValue(id: string) {
    setError("");
    setBusyValueId(id);
    try {
      await apiFetch("/business-dna/core-values/" + id, { method: "DELETE" });
      setReloadCounter(reloadCounter + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove that value. Check your connection and try again.");
    } finally {
      setBusyValueId("");
    }
  }

  const coreValues = dna ? dna.core_values : [];
  const canSeeCapital = dna !== null && dna.capital_investment_amount !== null && dna.capital_investment_amount !== undefined;

  return (
    <div>
      <h3 className="text-base font-semibold text-white">Company profile</h3>
      <p className="mt-1 text-sm text-gray-500">
        What the company does and stands for. This is the &quot;Business DNA&quot; the AI uses to suggest critical roles and KPIs, so the clearer it is, the better the suggestions.
      </p>

      {state.loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}
      {state.error && !notSetUp ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{state.error}</p> : null}
      {notSetUp ? (
        <p className="mt-6 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-gray-400">
          The company profile hasn&apos;t been filled in yet.{canEdit ? " Add the details below and save." : " An HR administrator needs to fill it in."}
        </p>
      ) : null}
      {error ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
      {saved ? <p className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">Saved.</p> : null}

      {!state.loading && (!state.error || notSetUp) ? (
        <>
          <div className="mt-6 space-y-5">
            {TEXT_FIELDS.map(function (f) {
              return (
                <div key={f.field}>
                  <label className={SETTINGS_LABEL_CLASS}>{f.label}</label>
                  <textarea
                    rows={f.field === "vision" || f.field === "mission" ? 3 : 2}
                    value={shown(f.field)}
                    disabled={!canEdit}
                    onChange={function (e) {
                      setEdits({ ...edits, [f.field]: e.target.value });
                    }}
                    className={SETTINGS_INPUT_CLASS}
                  />
                  <p className="mt-1 text-xs text-gray-500">{f.hint}</p>
                </div>
              );
            })}

            {canSeeCapital || edits.capital !== undefined || notSetUp ? (
              <div>
                <label className={SETTINGS_LABEL_CLASS}>Capital investment amount</label>
                <input
                  type="number"
                  min={0}
                  value={shownCapital()}
                  disabled={!canEdit}
                  onChange={function (e) {
                    setEdits({ ...edits, capital: e.target.value });
                  }}
                  className={SETTINGS_INPUT_CLASS}
                />
                <p className="mt-1 text-xs text-gray-500">Only HR administrators and business executives can see this number.</p>
              </div>
            ) : null}
          </div>

          {canEdit ? (
            <div className="mt-6 flex justify-end">
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

          <div className="mt-10 border-t border-white/10 pt-6">
            <h4 className="text-sm font-semibold text-white">Core values</h4>
            <p className="mt-1 text-xs text-gray-500">The principles the company runs on.</p>
            {notSetUp ? (
              <p className="mt-3 text-sm text-gray-500">Save the profile above first, then add core values.</p>
            ) : (
              <>
                <div className="mt-4 flex flex-wrap gap-2">
                  {coreValues.length === 0 ? <p className="text-sm text-gray-500">No core values yet.</p> : null}
                  {coreValues.map(function (v) {
                    return (
                      <span key={v.id} className="flex items-center gap-2 rounded-full bg-indigo-500/15 px-3 py-1.5 text-sm text-indigo-200">
                        {v.value}
                        {canEdit ? (
                          <button
                            type="button"
                            disabled={busyValueId === v.id}
                            onClick={function () {
                              removeValue(v.id);
                            }}
                            aria-label={"Remove " + v.value}
                            className="text-indigo-300 hover:text-white disabled:opacity-50"
                          >
                            ×
                          </button>
                        ) : null}
                      </span>
                    );
                  })}
                </div>
                {canEdit ? (
                  <div className="mt-4 flex max-w-md gap-2">
                    <input
                      type="text"
                      value={newValue}
                      onChange={function (e) {
                        setNewValue(e.target.value);
                      }}
                      onKeyDown={function (e) {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addValue();
                        }
                      }}
                      placeholder="Add a core value"
                      className={SETTINGS_INPUT_CLASS}
                    />
                    <button
                      type="button"
                      disabled={busyValueId === "new" || !newValue.trim()}
                      onClick={addValue}
                      className="rounded-lg border border-indigo-500 px-4 text-sm font-medium text-indigo-300 hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

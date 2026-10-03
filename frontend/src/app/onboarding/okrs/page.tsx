"use client";

import React, { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

interface KeyResult {
  id: string;
  text: string;
}

interface Objective {
  id: string;
  title: string;
  scope: string;
  keyResults: KeyResult[];
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

const SCOPE_OPTIONS = [
  "Corporate",
  "Engineering",
  "Human Resources",
  "Sales & Marketing",
  "Finance",
  "Operations",
];

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function OkrsPage() {
  const router = useRouter();
  const [objectives, setObjectives] = useState<Objective[]>([
    {
      id: makeId(),
      title: "Expand workforce capacity across West Africa by 40 percent",
      scope: "Corporate",
      keyResults: [
        { id: makeId(), text: "Hire 200 new employees across Ghana and Nigeria by Q3" },
        { id: makeId(), text: "Achieve 95 percent workforce attendance rate by Q4" },
      ],
    },
    {
      id: makeId(),
      title: "Improve operational efficiency and reduce manual processes",
      scope: "Corporate",
      keyResults: [
        { id: makeId(), text: "Automate 80 percent of payroll processing by Q2" },
        { id: makeId(), text: "Reduce employee onboarding time from 5 days to 2 days" },
      ],
    },
  ]);

  function updateObjectiveTitle(objId: string, newTitle: string) {
    setObjectives(
      objectives.map(function (obj: Objective) {
        if (obj.id === objId) {
          return { ...obj, title: newTitle };
        }
        return obj;
      })
    );
  }

  function updateObjectiveScope(objId: string, newScope: string) {
    setObjectives(
      objectives.map(function (obj: Objective) {
        if (obj.id === objId) {
          return { ...obj, scope: newScope };
        }
        return obj;
      })
    );
  }

  function updateKeyResult(objId: string, krId: string, newText: string) {
    setObjectives(
      objectives.map(function (obj: Objective) {
        if (obj.id !== objId) {
          return obj;
        }
        return {
          ...obj,
          keyResults: obj.keyResults.map(function (kr: KeyResult) {
            if (kr.id === krId) {
              return { ...kr, text: newText };
            }
            return kr;
          }),
        };
      })
    );
  }

  function addKeyResult(objId: string) {
    setObjectives(
      objectives.map(function (obj: Objective) {
        if (obj.id !== objId) {
          return obj;
        }
        return {
          ...obj,
          keyResults: [...obj.keyResults, { id: makeId(), text: "" }],
        };
      })
    );
  }

  function removeKeyResult(objId: string, krId: string) {
    setObjectives(
      objectives.map(function (obj: Objective) {
        if (obj.id !== objId) {
          return obj;
        }
        return {
          ...obj,
          keyResults: obj.keyResults.filter(function (kr: KeyResult) {
            return kr.id !== krId;
          }),
        };
      })
    );
  }

  function addObjective() {
    setObjectives([
      ...objectives,
      {
        id: makeId(),
        title: "",
        scope: "Corporate",
        keyResults: [{ id: makeId(), text: "" }],
      },
    ]);
  }

  function removeObjective(objId: string) {
    setObjectives(
      objectives.filter(function (obj: Objective) {
        return obj.id !== objId;
      })
    );
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // TODO: replace with a real call to the OKR module endpoint once the
    // backend is ready. Remember: these entries are ADDITIVE mid-quarter,
    // never clear or overwrite existing OKRs on submit.
    console.log("OKRs submitted:", objectives);
    router.push("/onboarding/ai-suggestions");
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="flex items-center justify-between border-b border-white/10 px-8 py-4 sm:px-12">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <circle cx="9" cy="8" r="3" />
              <path d="M2 20c0-3 3-5 7-5s7 2 7 5" />
              <circle cx="17" cy="8" r="2.5" />
              <path d="M22 20c0-2.5-2-4-4.5-4.5" />
            </svg>
          </div>
          <span className="text-base font-bold">Elevare</span>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {ONBOARDING_STEPS.map(function (step, i) {
            let circleClass = "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ";
            let labelClass = "text-sm ";
            let content: string | number = i + 1;

            if (i < 2) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              content = "check";
            } else if (i === 2) {
              circleClass += "bg-indigo-500 text-white";
              labelClass += "font-medium text-indigo-400";
            } else {
              circleClass += "border border-white/20 text-gray-400";
              labelClass += "text-gray-500";
            }

            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className={circleClass}>
                    {content === "check" ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      content
                    )}
                  </span>
                  <span className={labelClass}>{step}</span>
                </div>
                {i < ONBOARDING_STEPS.length - 1 && <span className="h-px w-6 bg-white/10" />}
              </div>
            );
          })}
        </div>

        <div className="text-sm text-gray-400">
          Need help? <a href="#" className="text-indigo-400 hover:text-indigo-300">Contact Support</a>
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Set your corporate objectives</h1>
          <p className="mt-2 text-gray-400">
            Define strategic objectives and measurable key results for your organization.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
        >
          <h2 className="text-lg font-semibold">Corporate Objectives</h2>

          {objectives.map(function (obj: Objective) {
            return (
              <div key={obj.id} className="space-y-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={obj.title}
                    onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                      updateObjectiveTitle(obj.id, e.target.value);
                    }}
                    placeholder="Objective title"
                    className="flex-1 rounded-lg border border-white/10 bg-[#111726] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                  />
                  <select
                    value={obj.scope}
                    onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                      updateObjectiveScope(obj.id, e.target.value);
                    }}
                    className="rounded-lg border border-white/10 bg-[#111726] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
                  >
                    {SCOPE_OPTIONS.map(function (opt) {
                      return (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      );
                    })}
                  </select>
                  <button
                    type="button"
                    onClick={function () {
                      removeObjective(obj.id);
                    }}
                    className="text-gray-500 hover:text-red-400"
                    aria-label="Remove objective"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
                    </svg>
                  </button>
                </div>

                <p className="text-xs uppercase tracking-wide text-gray-500">Key Results</p>

                {obj.keyResults.map(function (kr: KeyResult) {
                  return (
                    <div key={kr.id} className="flex items-center gap-2 pl-4">
                      <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-500" />
                      <input
                        type="text"
                        value={kr.text}
                        onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                          updateKeyResult(obj.id, kr.id, e.target.value);
                        }}
                        placeholder="Key result"
                        className="flex-1 rounded-lg border border-white/10 bg-[#111726] px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                      />
                      <button
                        type="button"
                        onClick={function () {
                          removeKeyResult(obj.id, kr.id);
                        }}
                        className="text-gray-500 hover:text-red-400"
                        aria-label="Remove key result"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 6 6 18M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={function () {
                    addKeyResult(obj.id);
                  }}
                  className="ml-4 rounded-full border border-indigo-500/40 px-4 py-1.5 text-xs font-medium text-indigo-400 hover:border-indigo-500/70"
                >
                  + Add Key Result
                </button>
              </div>
            );
          })}

          <button
            type="button"
            onClick={addObjective}
            className="rounded-full border border-indigo-500/40 px-4 py-1.5 text-sm font-medium text-indigo-400 hover:border-indigo-500/70"
          >
            + Add Objective
          </button>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/org-setup");
              }}
              className="flex items-center gap-2 text-sm font-medium text-gray-400 hover:text-gray-200"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Go Back
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Save & Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

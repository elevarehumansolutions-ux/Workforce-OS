"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

interface Department {
  id: string;
  name: string;
  employeeCount: number;
  isCritical: boolean;
}

interface Location {
  id: string;
  type: string;
  place: string;
}

interface ReportingRole {
  id: string;
  title: string;
  isCritical: boolean;
  reportsTo: string;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

export default function OrgSetupPage() {
  const router = useRouter();
  const [departments, setDepartments] = useState<Department[]>([
    { id: "1", name: "Engineering", employeeCount: 0, isCritical: true },
    { id: "2", name: "Human Resources", employeeCount: 0, isCritical: true },
    { id: "3", name: "Sales & Marketing", employeeCount: 0, isCritical: true },
    { id: "4", name: "Finance", employeeCount: 0, isCritical: true },
    { id: "5", name: "Operations", employeeCount: 0, isCritical: false },
  ]);

  const [locations, setLocations] = useState<Location[]>([
    { id: "1", type: "HQ", place: "Lagos, Nigeria" },
    { id: "2", type: "Branch", place: "Abuja, Nigeria" },
    { id: "3", type: "Branch", place: "Port Harcourt, Nigeria" },
  ]);

  const [reportingRoles] = useState<ReportingRole[]>([
    { id: "1", title: "Chief Technology Officer (CTO)", isCritical: true, reportsTo: "CEO" },
    { id: "2", title: "Chief Financial Officer (CFO)", isCritical: false, reportsTo: "CEO" },
  ]);

  function toggleCritical(id: string) {
    setDepartments(
      departments.map((d: Department) => (d.id === id ? { ...d, isCritical: !d.isCritical } : d))
    );
  }

  function removeDepartment(id: string) {
    setDepartments(departments.filter((d: Department) => d.id !== id));
  }

  function addDepartment() {
    const name = window.prompt("Department name:");
    if (name && name.trim()) {
      setDepartments([
        ...departments,
        { id: crypto.randomUUID(), name: name.trim(), employeeCount: 0, isCritical: false },
      ]);
    }
  }

  function removeLocation(id: string) {
    setLocations(locations.filter((l: Location) => l.id !== id));
  }

  function addLocation() {
    const place = window.prompt("Location (e.g. City, Country):");
    if (place && place.trim()) {
      setLocations([...locations, { id: crypto.randomUUID(), type: "Branch", place: place.trim() }]);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // TODO: replace with a real call to the Org Structure module's endpoint
    // once the backend is ready.
    console.log("Org setup submitted:", { departments, locations, reportingRoles });
    router.push("/onboarding/okrs");
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      {/* Top nav */}
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
          {ONBOARDING_STEPS.map((step, i) => {
            const status = i < 1 ? "done" : i === 1 ? "active" : "upcoming";
            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                      status === "active"
                        ? "bg-indigo-500 text-white"
                        : status === "done"
                        ? "border border-indigo-500 text-indigo-400"
                        : "border border-white/20 text-gray-400"
                    }`}
                  >
                    {status === "done" ? "✓" : i + 1}
                  </span>
                  <span
                    className={`text-sm ${
                      status === "active" ? "font-medium text-indigo-400" : "text-gray-500"
                    }`}
                  >
                    {step}
                  </span>
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

      {/* Main content */}
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Set up your organization</h1>
          <p className="mt-2 text-gray-400">
            Design corporate compartments, regional bases, and the executive leadership tree.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          {/* Departments + Locations */}
          <div className="grid grid-cols-1 gap-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm lg:grid-cols-2">
            {/* Departments */}
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Departments</h2>
                <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                  {departments.length} Total
                </span>
              </div>
              <p className="mt-1 text-sm text-gray-500">
                Mark roles that are revenue-critical, operationally critical, or high-risk if vacant
              </p>

              <div className="mt-4 space-y-3">
                {departments.map((dept: Department) => (
                  <div
                    key={dept.id}
                    className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{dept.name}</p>
                      <p className="text-xs text-gray-500">{dept.employeeCount} employees</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleCritical(dept.id)}
                        className={`relative h-6 w-11 rounded-full transition ${
                          dept.isCritical ? "bg-indigo-500" : "bg-white/10"
                        }`}
                        aria-label="Toggle critical"
                      >
                        <span
                          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
                            dept.isCritical ? "left-5" : "left-0.5"
                          }`}
                        />
                      </button>
                      {dept.isCritical && (
                        <span className="rounded bg-red-500/15 px-2 py-1 text-xs font-medium text-red-400">
                          Critical
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => removeDepartment(dept.id)}
                        className="text-gray-500 hover:text-red-400"
                        aria-label="Remove department"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </div>
                ))}

                <button
                  type="button"
                  onClick={addDepartment}
                  className="w-full rounded-lg border border-dashed border-indigo-500/40 py-3 text-sm font-medium text-indigo-400 hover:border-indigo-500/70"
                >
                  + Add Department
                </button>
              </div>
            </div>

            {/* Locations */}
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Locations</h2>
                <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                  {locations.length} Bases
                </span>
              </div>

              <div className="mt-4 space-y-3">
                {locations.map((loc: Location) => (
                  <div
                    key={loc.id}
                    className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{loc.type}</p>
                      <p className="text-xs text-gray-500">{loc.place}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeLocation(loc.id)}
                      className="text-gray-500 hover:text-red-400"
                      aria-label="Remove location"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                ))}

                <button
                  type="button"
                  onClick={addLocation}
                  className="w-full rounded-lg border border-dashed border-indigo-500/40 py-3 text-sm font-medium text-indigo-400 hover:border-indigo-500/70"
                >
                  + Add Location
                </button>
              </div>
            </div>
          </div>

          {/* Reporting Hierarchy */}
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
            <h2 className="text-lg font-semibold">Reporting Hierarchy Setup</h2>
            <div className="mt-4 flex flex-col gap-4 rounded-lg border border-white/10 bg-[#0a0e1a] p-6 sm:flex-row sm:items-center">
              <div className="rounded-lg border border-indigo-500 px-4 py-3 text-center">
                <p className="text-sm font-semibold text-indigo-400">CEO</p>
                <p className="text-xs text-gray-500">Executive Leader</p>
              </div>
              <div className="hidden h-px flex-1 bg-indigo-500/40 sm:block" />
              <div className="flex flex-1 flex-col gap-2">
                {reportingRoles.map((role: ReportingRole) => (
                  <div key={role.id} className="flex flex-wrap items-center gap-2">
                    <span className="rounded-lg border border-white/10 bg-[#111726] px-4 py-2 text-sm font-medium">
                      {role.title}
                    </span>
                    {role.isCritical && (
                      <span className="rounded bg-red-500/15 px-2 py-1 text-xs font-medium text-red-400">
                        Critical
                      </span>
                    )}
                    <span className="text-xs text-gray-500">Reports to {role.reportsTo}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Footer nav */}
          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={function () {
                router.push("/onboarding/business-dna");
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

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
    </svg>
  );
}

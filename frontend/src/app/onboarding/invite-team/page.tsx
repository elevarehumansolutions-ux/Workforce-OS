"use client";

import React, { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

interface Invite {
  id: string;
  email: string;
  role: string;
  department: string;
  reportingManager: string;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

const ROLE_OPTIONS = ["Employee", "Manager", "HR Administrator", "Business Executive"];
const DEPARTMENT_OPTIONS = [
  "Engineering",
  "Human Resources",
  "Sales & Marketing",
  "Finance",
  "Operations",
];
const MANAGER_OPTIONS = ["Adewale O.", "Ngozi A.", "Femi A.", "Tolu B."];

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function InviteTeamPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [department, setDepartment] = useState("");
  const [reportingManager, setReportingManager] = useState("");
  const [invites, setInvites] = useState<Invite[]>([
    { id: makeId(), email: "ngozi@zenith.com", role: "Manager", department: "Engineering", reportingManager: "Adewale O." },
    { id: makeId(), email: "femi.alao@zenith.com", role: "HR Administrator", department: "Human Resources", reportingManager: "Ngozi A." },
    { id: makeId(), email: "kemi.a@zenith.com", role: "Employee", department: "Finance", reportingManager: "Femi A." },
  ]);

  function addInvite() {
    if (!email.trim() || !role || !department || !reportingManager) {
      window.alert("Please fill in email, role, department, and reporting manager before adding.");
      return;
    }
    setInvites([
      ...invites,
      {
        id: makeId(),
        email: email.trim(),
        role: role,
        department: department,
        reportingManager: reportingManager,
      },
    ]);
    setEmail("");
    setRole("");
    setDepartment("");
    setReportingManager("");
  }

  function removeInvite(id: string) {
    setInvites(
      invites.filter(function (invite: Invite) {
        return invite.id !== id;
      })
    );
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // TODO: replace with a real call to the Identity module's
    // membership-invite endpoint once the backend is ready.
    console.log("Invites submitted:", invites);
    // TODO: point this at the real dashboard route once it exists.
    // Using /login for now as the end of the onboarding flow.
    router.push("/login");
  }

  function handleSkip() {
    // TODO: point this at the real dashboard route once it exists.
    console.log("Skipped invites for now");
    router.push("/login");
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
            let isCheck = false;

            if (i < 5) {
              circleClass += "border border-indigo-500 text-indigo-400";
              labelClass += "text-gray-500";
              isCheck = true;
            } else {
              circleClass += "bg-indigo-500 text-white";
              labelClass += "font-medium text-indigo-400";
            }

            return (
              <div key={step} className="flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className={circleClass}>
                    {isCheck ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    ) : (
                      i + 1
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

      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Invite your team</h1>
          <p className="mt-2 text-gray-400">Bring in the people who will help run your organization</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-5">
            <div className="sm:col-span-2">
              <label className="mb-2 block text-sm font-medium text-gray-200">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                  setEmail(e.target.value);
                }}
                placeholder="e.g. ngozi@zenith.com"
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Role</label>
              <select
                value={role}
                onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                  setRole(e.target.value);
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
              >
                <option value="">Select role</option>
                {ROLE_OPTIONS.map(function (opt) {
                  return (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  );
                })}
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Department</label>
              <select
                value={department}
                onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                  setDepartment(e.target.value);
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
              >
                <option value="">Select department</option>
                {DEPARTMENT_OPTIONS.map(function (opt) {
                  return (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  );
                })}
              </select>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Reporting Manager</label>
              <div className="flex gap-2">
                <select
                  value={reportingManager}
                  onChange={function (e: React.ChangeEvent<HTMLSelectElement>) {
                    setReportingManager(e.target.value);
                  }}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-3 text-sm text-white outline-none focus:border-indigo-500"
                >
                  <option value="">Select manager</option>
                  {MANAGER_OPTIONS.map(function (opt) {
                    return (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    );
                  })}
                </select>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={addInvite}
              className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
            >
              + Add
            </button>
          </div>

          <button
            type="button"
            className="text-sm font-medium text-indigo-400 hover:text-indigo-300"
          >
            + Add Another
          </button>

          <div className="border-t border-white/10 pt-6">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">{invites.length} invites added</h2>
              <span className="text-sm text-gray-500">Review before sending</span>
            </div>

            <div className="mt-4 space-y-2">
              {invites.map(function (invite: Invite) {
                return (
                  <div
                    key={invite.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-6 text-sm">
                      <span className="font-medium">{invite.email}</span>
                      <span className="text-gray-400">{invite.role}</span>
                      <span className="text-gray-400">{invite.department}</span>
                      <span className="text-gray-400">{invite.reportingManager}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1.5 rounded-full bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                        Invite Pending
                      </span>
                      <button
                        type="button"
                        onClick={function () {
                          removeInvite(invite.id);
                        }}
                        className="rounded-lg bg-red-500/15 p-2 text-red-400 hover:bg-red-500/25"
                        aria-label="Remove invite"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <button
              type="button"
              onClick={handleSkip}
              className="text-sm font-medium text-gray-400 hover:text-gray-200"
            >
              Skip for now
            </button>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Send Invites & Continue
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </form>

        <p className="mt-4 text-center text-sm text-gray-500">Draft saved automatically</p>
      </div>
    </div>
  );
}

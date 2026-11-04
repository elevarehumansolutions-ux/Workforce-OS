"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch, clearAccessToken } from "@/lib/api";
import { formatDateTime, roleLabel } from "@/lib/tasks";
import { SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS, titleCase } from "@/lib/settings";
import type { SectionProps } from "./types";

const SPECIAL_CHARACTERS = /[!@#$%^&*(),.?":{}|<>]/;

function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push("At least 8 characters");
  if (!/[A-Z]/.test(password)) problems.push("One uppercase letter");
  if (!/[a-z]/.test(password)) problems.push("One lowercase letter");
  if (!/\d/.test(password)) problems.push("One number");
  if (!SPECIAL_CHARACTERS.test(password)) problems.push("One special character, such as ! @ # $ %");
  return problems;
}

const PROTECTIONS = [
  "Each organization's data is kept separate from every other organization's.",
  "What people can see and do depends on their role.",
  "Changes to important records are written to the audit log.",
  "Payroll changes need approval before they take effect.",
];

export default function SecuritySection(props: SectionProps) {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const problems = passwordProblems(next);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setDone(false);
    if (!current) {
      setError("Enter your current password.");
      return;
    }
    if (problems.length > 0) {
      setError("The new password doesn't meet all the requirements below yet.");
      return;
    }
    if (next !== confirm) {
      setError("The two new passwords don't match.");
      return;
    }
    if (next === current) {
      setError("The new password must be different from the current one.");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change your password. Check your connection and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    setSigningOut(true);
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Signing out on this device should work even if the server can't be reached.
    }
    clearAccessToken();
    router.push("/login");
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-white">Security</h3>
      <p className="mt-1 text-sm text-gray-500">Your sign-in, and how your organization&apos;s data is protected.</p>

      <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-gray-500">Signed in as</dt>
          <dd className="mt-1 text-gray-200">{props.me.email}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Role</dt>
          <dd className="mt-1 text-gray-200">{roleLabel(props.me.role)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Account status</dt>
          <dd className="mt-1 text-gray-200">{titleCase(props.me.accountStatus)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Last sign-in</dt>
          <dd className="mt-1 text-gray-200">{props.me.lastLoginAt ? formatDateTime(props.me.lastLoginAt) : "Not recorded"}</dd>
        </div>
      </dl>

      <form onSubmit={submit} className="mt-8 max-w-md border-t border-white/10 pt-6">
        <h4 className="text-sm font-semibold text-white">Change password</h4>
        {error ? <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
        {done ? <p className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">Your password has been changed.</p> : null}
        <div className="mt-4 space-y-4">
          <div>
            <label className={SETTINGS_LABEL_CLASS}>Current password</label>
            <input type="password" autoComplete="current-password" value={current} onChange={function (e) { setCurrent(e.target.value); }} className={SETTINGS_INPUT_CLASS} />
          </div>
          <div>
            <label className={SETTINGS_LABEL_CLASS}>New password</label>
            <input type="password" autoComplete="new-password" value={next} onChange={function (e) { setNext(e.target.value); }} className={SETTINGS_INPUT_CLASS} />
            {next && problems.length > 0 ? (
              <ul className="mt-2 space-y-0.5 text-xs text-amber-300">
                {problems.map(function (p) {
                  return <li key={p}>Needs: {p}</li>;
                })}
              </ul>
            ) : null}
          </div>
          <div>
            <label className={SETTINGS_LABEL_CLASS}>Confirm new password</label>
            <input type="password" autoComplete="new-password" value={confirm} onChange={function (e) { setConfirm(e.target.value); }} className={SETTINGS_INPUT_CLASS} />
          </div>
        </div>
        <button type="submit" disabled={saving} className="mt-5 rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:opacity-50">
          {saving ? "Changing…" : "Change password"}
        </button>
      </form>

      <div className="mt-8 border-t border-white/10 pt-6">
        <h4 className="text-sm font-semibold text-white">How your data is protected</h4>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-gray-400">
          {PROTECTIONS.map(function (p) {
            return <li key={p}>{p}</li>;
          })}
        </ul>
      </div>

      <div className="mt-8 border-t border-white/10 pt-6">
        <button type="button" disabled={signingOut} onClick={signOut} className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-50">
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
  );
}

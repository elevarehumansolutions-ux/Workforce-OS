"use client";

import { useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { ApiError, apiFetch } from "@/lib/api";
import { roleLabel } from "@/lib/tasks";
import { isHrRole, loadMe, SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS } from "@/lib/settings";
import { useLoad } from "@/lib/useLoad";

type SentStatus = "invited" | "added";

interface SentInvite {
  id: string;
  email: string;
  role: string;
  status: SentStatus;
}

// These are sent to the server as-is, so each value is the real role name.
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

interface InviteResponse {
  status: SentStatus;
  // The email the server actually stored (trimmed and lower-cased).
  membership?: { id: string; user: { email: string } } | null;
  invite?: { id: string; email: string; role: string } | null;
}

export default function InviteTeammatePage() {
  const me = useLoad("invite-me", loadMe, "Couldn't load your account. Check your connection and try again.");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("employee");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [deactivated, setDeactivated] = useState(false);
  const [sent, setSent] = useState<SentInvite[]>([]);

  const canInvite = me.data !== null && isHrRole(me.data.role);

  async function send() {
    const trimmed = email.trim();
    if (!trimmed) {
      setError("Enter an email address.");
      return;
    }
    setError("");
    setDeactivated(false);
    setSending(true);
    try {
      const res = await apiFetch<InviteResponse>("/memberships", { method: "POST", body: { email: trimmed, role: role } });
      const shown = (res.invite && res.invite.email) || (res.membership && res.membership.user.email) || trimmed;
      setSent([{ id: shown + "|" + sent.length, email: shown, role: role, status: res.status }].concat(sent));
      setEmail("");
    } catch (err) {
      if (err instanceof ApiError && err.code === "MEMBERSHIP_DEACTIVATED") {
        setDeactivated(true);
        setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Couldn't send that invite. Check your connection and try again.");
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <AppShell
      activeLabel="Employees"
      title="Invite a teammate"
      breadcrumb="Employees > Invite"
      userName={me.data ? me.data.fullName : undefined}
      userRole={me.data ? roleLabel(me.data.role) : undefined}
    >
      {me.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {me.error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{me.error}</p> : null}

      {me.data && !canInvite ? (
        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-400">
          Only an HR administrator can invite people. Ask them to send the invite.
        </div>
      ) : null}

      {canInvite ? (
        <div className="mx-auto max-w-3xl">
          <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
            <p className="text-sm text-gray-400">
              They get an email with a link to set a password and join your organization. Their department and reporting manager are set on their employee record,
              under <Link href="/employees/add" className="text-indigo-400 hover:text-indigo-300">Add Employee</Link>.
            </p>

            {error ? (
              <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {error}
                {deactivated ? (
                  <>
                    {" "}
                    <Link href="/team-management" className="font-medium underline">Open Team Management</Link> to reactivate them.
                  </>
                ) : null}
              </div>
            ) : null}

            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-[2fr_1.2fr_auto] sm:items-end">
              <div>
                <label className={SETTINGS_LABEL_CLASS}>Email address</label>
                <input
                  type="email"
                  value={email}
                  placeholder="e.g. ngozi@company.com"
                  onChange={function (e) { setEmail(e.target.value); }}
                  onKeyDown={function (e) {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      send();
                    }
                  }}
                  className={SETTINGS_INPUT_CLASS}
                />
              </div>
              <div>
                <label className={SETTINGS_LABEL_CLASS}>Role</label>
                <select value={role} onChange={function (e) { setRole(e.target.value); }} className={SETTINGS_INPUT_CLASS}>
                  {ROLE_OPTIONS.map(function (r) {
                    return (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    );
                  })}
                </select>
              </div>
              <button
                type="button"
                disabled={sending}
                onClick={send}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:opacity-50"
              >
                {sending ? "Sending…" : "Send invite"}
              </button>
            </div>

            <div className="mt-8 border-t border-white/10 pt-6">
              <h3 className="text-sm font-semibold text-white">Sent in this session ({sent.length})</h3>
              {sent.length === 0 ? (
                <p className="mt-3 text-sm text-gray-500">Invites you send will be listed here. To see everyone, open Team Management.</p>
              ) : (
                <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
                  <table className="w-full text-left text-sm">
                    <tbody className="divide-y divide-white/5">
                      {sent.map(function (s) {
                        return (
                          <tr key={s.id}>
                            <td className="px-4 py-3 text-white">{s.email}</td>
                            <td className="px-4 py-3 text-gray-300">{roleLabel(s.role)}</td>
                            <td className="px-4 py-3">
                              {s.status === "added" ? (
                                <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">Added</span>
                              ) : (
                                <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300">Invite sent</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="mt-4 text-xs text-gray-500">
                &quot;Added&quot; means that person already had an account, so they joined straight away. &quot;Invite sent&quot; means they still need to accept the email.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

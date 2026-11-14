"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, currentOrganizationId, getAccessToken, setAccessToken } from "@/lib/api";
import Logo from "@/components/Logo";
import Modal from "@/components/Modal";

interface Organization {
  id: string;
  name: string | null;
  subscription_status: string;
}

interface Membership {
  id: string;
  role: string;
  is_owner: boolean;
  deactivated_at: string | null;
  organization: Organization;
}

interface DeletedCompany {
  organization_id: string;
  name: string | null;
  deleted_at: string;
  // After this day the company is erased for good (set by the server, 30 days after deleting).
  will_be_erased_on: string;
}

interface MeResponse {
  user: { id: string; full_name: string; email: string };
  memberships: Membership[];
}

const ROLE_LABELS: Record<string, string> = {
  hr_administrator: "HR Administrator",
  manager: "Manager",
  business_executive: "Executive",
  employee: "Employee",
  system_administrator: "System Administrator",
};

function initials(name: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function OrganizationsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  // "Create a new company": the form is hidden until asked for.
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState("");
  // "Delete": a window for ONE company (the one whose icon was pressed) that asks for its name and the password.
  const [deleteTarget, setDeleteTarget] = useState<Membership | null>(null);
  const [deleteName, setDeleteName] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  // Companies this person deleted and may bring back, and the one a "Restore" window is open for.
  const [deletedCompanies, setDeletedCompanies] = useState<DeletedCompany[]>([]);
  const [restoreTarget, setRestoreTarget] = useState<DeletedCompany | null>(null);
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [restoreError, setRestoreError] = useState("");
  const [notice, setNotice] = useState("");

  // Your companies, and the ones you deleted. Called on load and again after every delete or restore.
  function loadLists() {
    return Promise.all([
      apiFetch<MeResponse>("/auth/me", { method: "GET" }),
      // If this one fails the main list should still show, so it falls back to "nothing deleted".
      apiFetch<{ data: DeletedCompany[] }>("/auth/deleted-organizations", { method: "GET" }).catch(function () {
        return { data: [] as DeletedCompany[] };
      }),
    ]).then(function (results) {
      setMe(results[0]);
      setDeletedCompanies(results[1].data);
    });
  }

  useEffect(function () {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    loadLists()
      .catch(function (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't load your organizations. Please try again.");
      })
      .finally(function () {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSwitch(membership: Membership) {
    if (membership.organization.id === currentOrganizationId()) {
      router.push("/dashboard");
      return;
    }
    setSwitching(membership.organization.id);
    setError("");
    try {
      // The server issues a new access token for the chosen company (POST /auth/switch-organization).
      const data = await apiFetch<{ access_token: string }>("/auth/switch-organization", {
        method: "POST",
        body: { organization_id: membership.organization.id },
      });
      setAccessToken(data.access_token);
      if (typeof window !== "undefined") {
        // A full page load, so the menu and every cached role start fresh for the new company.
        window.location.assign("/dashboard");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't switch company. Please try again.");
      setSwitching(null);
    }
  }

  // Matches the server's limit (MAX_OWNED_COMPANIES): companies this person started, not ones they joined.
  const MAX_OWNED = 3;
  const ownedCount = me
    ? me.memberships.filter(function (m) { return m.is_owner && !m.deactivated_at; }).length
    : 0;

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (saving) return; // a double click must not send two
    setCreateError("");
    if (newName.trim().length < 2) {
      setCreateError("Give the company a name of at least 2 characters.");
      return;
    }
    setSaving(true);
    try {
      // The answer is a session for the NEW company (POST /auth/create-organization).
      const data = await apiFetch<{ access_token: string }>("/auth/create-organization", {
        method: "POST",
        body: { name: newName.trim() },
      });
      setAccessToken(data.access_token);
      // A full page load into its onboarding, so every cached role and menu starts fresh.
      window.location.assign("/onboarding/business-dna");
    } catch (err) {
      // 409: you already have one with that name, or you own the most allowed. The message says which.
      setCreateError(err instanceof ApiError ? err.message : "Couldn't create the company. Please try again.");
      setSaving(false);
    }
  }

  // A delete icon shows on each company this person owns, but only when they have somewhere else to go.
  // (The server enforces both rules too; this only decides what to show.)
  const activeMemberships = me
    ? me.memberships.filter(function (m) { return !m.deactivated_at; })
    : [];
  const hasAnotherCompany = activeMemberships.length >= 2;
  const nameTypedCorrectly =
    deleteTarget !== null &&
    deleteName.trim().toLowerCase() === (deleteTarget.organization.name || "").trim().toLowerCase();

  function closeDeleteWindow() {
    setDeleteTarget(null);
    setDeleteName("");
    setDeletePassword("");
    setDeleteError("");
  }

  async function handleDelete(e: React.FormEvent) {
    e.preventDefault();
    if (deleteBusy || !deleteTarget) return; // a double click must not send two
    setDeleteError("");
    setDeleteBusy(true);
    try {
      // POST /auth/delete-organization. Deleting the company you are IN answers with a session for another
      // company (access_token); deleting a different one answers {session_opened: false} and changes nothing here.
      const data = await apiFetch<{ access_token?: string; session_opened?: boolean }>("/auth/delete-organization", {
        method: "POST",
        body: {
          organization_id: deleteTarget.organization.id,
          confirm_name: deleteName.trim(),
          password: deletePassword,
        },
      });
      if (data.access_token) {
        setAccessToken(data.access_token);
        // A full page load, so the menu and every cached role start fresh for the company we land in.
        window.location.assign("/dashboard");
        return;
      }
      const deletedName = deleteTarget.organization.name || "The company";
      closeDeleteWindow();
      setNotice(deletedName + " was deleted. You can restore it under Deleted companies for 30 days.");
      await loadLists();
      setDeleteBusy(false);
    } catch (err) {
      // 422: wrong password or name. 409 LAST_COMPANY: the only company. 403: not the owner.
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete the company. Please try again.");
      setDeleteBusy(false);
    }
  }

  async function handleRestore() {
    if (restoreBusy || !restoreTarget) return; // a double click must not send two
    setRestoreError("");
    setRestoreBusy(true);
    try {
      await apiFetch("/auth/restore-organization", {
        method: "POST",
        body: { organization_id: restoreTarget.organization_id },
      });
      const restoredName = restoreTarget.name || "The company";
      setRestoreTarget(null);
      setNotice(restoredName + " is back, with the people who lost access when it was deleted.");
      await loadLists();
    } catch (err) {
      // 409: you already own 3 companies, or a live one has the same name. The message says which.
      setRestoreError(err instanceof ApiError ? err.message : "Couldn't restore the company. Please try again.");
    } finally {
      setRestoreBusy(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="mb-8 flex items-center gap-3">
          <Logo size={44} textClassName="text-lg font-bold" />
        </div>

        <h1 className="text-2xl font-bold">Your companies</h1>
        <p className="mt-1 text-sm text-gray-400">
          {me ? me.user.full_name + "'s workspaces" : "Choose which workspace you want to work in."}
        </p>

        {error ? (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            {notice}
          </div>
        ) : null}

        {loading ? (
          <div className="mt-8 space-y-3">
            {[0, 1].map(function (i) {
              return <div key={i} className="h-20 animate-pulse rounded-xl border border-white/10 bg-white/5" />;
            })}
          </div>
        ) : null}

        {!loading && me && me.memberships.length === 0 ? (
          <div className="mt-8 rounded-xl border border-white/10 bg-[#0d1220] px-6 py-8 text-center text-sm text-gray-400">
            You don&apos;t belong to any organization yet.
          </div>
        ) : null}

        {!loading && me ? (
          <div className="mt-8 space-y-3">
            {me.memberships.map(function (membership) {
              const org = membership.organization;
              const isActive = org.id === currentOrganizationId();
              const isDeactivated = Boolean(membership.deactivated_at);
              // Only the owner may delete, and never the last company they can enter.
              const showDelete = membership.is_owner && !isDeactivated;
              return (
                <div key={membership.id} className="flex items-stretch gap-2">
                <button
                  onClick={function () {
                    if (!isDeactivated) handleSwitch(membership);
                  }}
                  disabled={isDeactivated || switching === org.id}
                  className={
                    "flex w-full items-center justify-between rounded-xl border px-5 py-4 text-left transition " +
                    (isActive
                      ? "border-indigo-500/50 bg-indigo-500/10"
                      : "border-white/10 bg-[#0d1220] hover:border-white/20 hover:bg-white/5") +
                    (isDeactivated ? " cursor-not-allowed opacity-50" : "")
                  }
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-indigo-500/20 text-sm font-semibold text-indigo-300">
                      {initials(org.name)}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">{org.name || "Untitled organization"}</p>
                      <p className="text-xs text-gray-400">
                        {ROLE_LABELS[membership.role] || membership.role}
                        {membership.is_owner ? " · Owner" : ""}
                        {isDeactivated ? " · Access removed" : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {isActive ? (
                      <span className="rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-medium text-indigo-300">
                        Current
                      </span>
                    ) : null}
                    {switching === org.id ? (
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                        <path d="M7 4l6 6-6 6" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                </button>
                {showDelete ? (
                  <button
                    type="button"
                    disabled={!hasAnotherCompany}
                    title={hasAnotherCompany ? "Delete " + (org.name || "this company") : "This is your only company, so it cannot be deleted"}
                    aria-label={"Delete " + (org.name || "this company")}
                    onClick={function () { setNotice(""); setDeleteTarget(membership); }}
                    className="flex w-12 items-center justify-center rounded-xl border border-white/10 bg-[#0d1220] text-gray-400 hover:border-red-500/50 hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:border-white/10 disabled:hover:bg-[#0d1220] disabled:hover:text-gray-400"
                  >
                    <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
                      <path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10M9 9v4M11 9v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                ) : null}
                </div>
              );
            })}
          </div>
        ) : null}

        {!loading && me ? (
          <div className="mt-8 rounded-xl border border-white/10 bg-[#0d1220] px-5 py-4">
            {!creating ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">Start another company</p>
                  <p className="text-xs text-gray-400">
                    {ownedCount >= MAX_OWNED
                      ? "You own " + MAX_OWNED + " companies, the most one login can create."
                      : "You own " + ownedCount + " of " + MAX_OWNED + ". It gets its own people, plan and settings."}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={ownedCount >= MAX_OWNED}
                  onClick={function () { setCreating(true); }}
                  className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Create a new company
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="space-y-3">
                <label htmlFor="new-company" className="block text-sm font-medium text-gray-200">
                  Company name
                </label>
                <input
                  id="new-company"
                  type="text"
                  value={newName}
                  onChange={function (e) { setNewName(e.target.value); }}
                  placeholder="e.g. Zenith Foods Ltd"
                  autoFocus
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
                {createError ? <p className="text-xs text-red-300">{createError}</p> : null}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
                  >
                    {saving ? "Creating…" : "Create and open it"}
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={function () { setCreating(false); setCreateError(""); }}
                    className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 hover:border-white/30"
                  >
                    Cancel
                  </button>
                </div>
                <p className="text-xs text-gray-500">
                  You will set it up from the start: its business details, plan and people.
                </p>
              </form>
            )}
          </div>
        ) : null}

        {!loading && deletedCompanies.length > 0 ? (
          <div className="mt-8 rounded-xl border border-white/10 bg-[#0d1220] px-5 py-4">
            <p className="text-sm font-semibold text-white">Deleted companies</p>
            <p className="mt-1 text-xs text-gray-400">
              You deleted these. Restoring one brings back its people too. After the date shown, a company is erased
              for good, with all its people, plans and records, and can no longer be restored.
            </p>
            <div className="mt-3 space-y-2">
              {deletedCompanies.map(function (company) {
                return (
                  <div
                    key={company.organization_id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-white">{company.name || "Untitled organization"}</p>
                      <p className="text-xs text-gray-500">
                        Deleted on {new Date(company.deleted_at).toLocaleDateString()}.{" "}
                        <span className="text-amber-300">
                          Erased for good on {new Date(company.will_be_erased_on).toLocaleDateString()}.
                        </span>
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={function () { setNotice(""); setRestoreError(""); setRestoreTarget(company); }}
                      className="rounded-lg border border-indigo-400/50 px-4 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/10"
                    >
                      Restore
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {restoreTarget ? (
          <Modal title={"Restore " + (restoreTarget.name || "this company") + "?"} onClose={function () { setRestoreTarget(null); }}>
            <p className="text-sm text-gray-300">
              The company comes back as it was. Everyone who lost access when you deleted it gets it back;
              people an administrator had removed earlier stay removed. Invitations that were waiting are
              not restored, so send them again.
            </p>
            {restoreError ? <p className="mt-3 text-xs text-red-300">{restoreError}</p> : null}
            <div className="mt-5 flex flex-wrap justify-end gap-3">
              <button
                type="button"
                disabled={restoreBusy}
                onClick={function () { setRestoreTarget(null); }}
                className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 hover:border-white/30 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={restoreBusy}
                onClick={handleRestore}
                className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
              >
                {restoreBusy ? "Restoring…" : "Restore this company"}
              </button>
            </div>
          </Modal>
        ) : null}

        {deleteTarget ? (
          <Modal title={"Delete " + (deleteTarget.organization.name || "this company") + "?"} onClose={closeDeleteWindow}>
            <form onSubmit={handleDelete} className="space-y-3">
              <p className="text-sm text-gray-300">
                Everyone in this company loses access straight away, and it disappears from every list.
                {deleteTarget.organization.id === currentOrganizationId()
                  ? " You will be moved to your other company."
                  : " You stay where you are."}
              </p>
              <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                You can restore it from Deleted companies for 30 days. After that it is erased for good, with all
                its people, plans and records, and cannot be brought back.
              </p>
              <label htmlFor="delete-name" className="block text-xs text-gray-400">
                Type the company name to confirm: <span className="font-semibold text-white">{deleteTarget.organization.name}</span>
              </label>
              <input
                id="delete-name"
                type="text"
                value={deleteName}
                onChange={function (e) { setDeleteName(e.target.value); }}
                autoFocus
                className="w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-white outline-none focus:border-red-400"
              />
              <label htmlFor="delete-password" className="block text-xs text-gray-400">
                Your password
              </label>
              <input
                id="delete-password"
                type="password"
                value={deletePassword}
                onChange={function (e) { setDeletePassword(e.target.value); }}
                autoComplete="current-password"
                className="w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-white outline-none focus:border-red-400"
              />
              {deleteError ? <p className="text-xs text-red-300">{deleteError}</p> : null}
              <div className="flex flex-wrap justify-end gap-3 pt-2">
                <button
                  type="button"
                  disabled={deleteBusy}
                  onClick={closeDeleteWindow}
                  className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-300 hover:border-white/30 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={deleteBusy || !nameTypedCorrectly || deletePassword === ""}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {deleteBusy ? "Deleting…" : "Delete this company"}
                </button>
              </div>
            </form>
          </Modal>
        ) : null}

        <a
          href="/dashboard"
          className="mt-8 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          ← Back to dashboard
        </a>
      </div>
    </div>
  );
}
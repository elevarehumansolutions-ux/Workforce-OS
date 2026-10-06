"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
  { label: "Team Management", href: "/team-management" },
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
    </aside>
  );
}

// Matches MembershipRole on the backend exactly.
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

const ROLE_LABELS: Record<string, string> = ROLE_OPTIONS.reduce(function (acc, opt) {
  acc[opt.value] = opt.label;
  return acc;
}, {} as Record<string, string>);

interface Pagination {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

interface Membership {
  id: string;
  role: string;
  is_owner: boolean;
  deactivated_at: string | null;
  created_at: string;
  user: { id: string; email: string; full_name: string };
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: Pagination;
}

function initialsFor(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  const first = parts[0] ? parts[0].charAt(0).toUpperCase() : "";
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0).toUpperCase() : "";
  return (first + last) || "?";
}

export default function TeamManagementPage() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [page, setPage] = useState(1);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [rowNotice, setRowNotice] = useState<{ id: string; text: string } | null>(null);

  function load() {
    setLoading(true);
    setLoadError("");
    apiFetch<PaginatedResponse<Membership>>("/memberships?page=" + page + "&limit=20", { method: "GET" })
      .then(function (res) {
        setMemberships(res.data);
        setPagination(res.pagination);
      })
      .catch(function (err) {
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load the team.");
      })
      .finally(function () {
        setLoading(false);
      });
  }

  useEffect(
    function () {
      // load() sets loading/error state synchronously before its fetch
      // resolves, so paging shows the spinner right away instead of leaving
      // the previous page's rows on screen while the new page loads.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      load();
    },
    // load is re-created every render (it closes over page), so listing it
    // here would re-run this effect on every render instead of only when
    // the page number actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [page]
  );

  async function handleRoleChange(membership: Membership, newRole: string) {
    if (newRole === membership.role) return;
    setBusyId(membership.id);
    setRowError(null);
    try {
      const updated = await apiFetch<Membership>("/memberships/" + membership.id, {
        method: "PATCH",
        body: { role: newRole },
      });
      setMemberships(function (prev) {
        return prev.map(function (m) {
          return m.id === updated.id ? updated : m;
        });
      });
      setRowNotice({ id: membership.id, text: "Role updated." });
    } catch (err) {
      setRowError({
        id: membership.id,
        text: err instanceof ApiError ? err.message : "Couldn't change that role.",
      });
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeactivate(membership: Membership) {
    if (!window.confirm("Deactivate " + membership.user.full_name + "? They'll lose access to this organization until reactivated.")) {
      return;
    }
    setBusyId(membership.id);
    setRowError(null);
    try {
      const updated = await apiFetch<Membership>("/memberships/" + membership.id, {
        method: "PATCH",
        body: { is_deactivated: true },
      });
      setMemberships(function (prev) {
        return prev.map(function (m) {
          return m.id === updated.id ? updated : m;
        });
      });
      setRowNotice({ id: membership.id, text: "Deactivated." });
    } catch (err) {
      setRowError({
        id: membership.id,
        text: err instanceof ApiError ? err.message : "Couldn't deactivate this person.",
      });
    } finally {
      setBusyId(null);
    }
  }

  async function handleReactivate(membership: Membership) {
    setBusyId(membership.id);
    setRowError(null);
    try {
      const updated = await apiFetch<Membership>("/memberships/" + membership.id + "/reactivate", {
        method: "POST",
        body: {},
      });
      setMemberships(function (prev) {
        return prev.map(function (m) {
          return m.id === updated.id ? updated : m;
        });
      });
      setRowNotice({ id: membership.id, text: "Reactivated — their old role is restored." });
    } catch (err) {
      if (err instanceof ApiError && err.code === "VALIDATION_FAILED" && err.status === 422) {
        setRowError({
          id: membership.id,
          text: "This person is an offboarded employee — reinstate them from the Employee Directory instead, which restores login access in the same step.",
        });
      } else if (err instanceof ApiError && err.code === "MEMBERSHIP_NOT_DEACTIVATED") {
        setRowError({ id: membership.id, text: "They're already active — refreshing the list." });
        load();
      } else {
        setRowError({
          id: membership.id,
          text: err instanceof ApiError ? err.message : "Couldn't reactivate this person.",
        });
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Team Management")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Team Management</p>
            <h1 className="text-xl font-bold text-white">Team Management</h1>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <p className="mb-6 max-w-2xl text-sm text-gray-400">
            Everyone with login access to this organization. Change a role, deactivate someone, or bring
            a deactivated person back. For Employee records and HR details, use the{" "}
            <Link href="/employees/directory" className="text-indigo-400 hover:text-indigo-300">
              Employee Directory
            </Link>{" "}
            instead.
          </p>

          {loading ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-sm text-gray-400 shadow-xl">
              Loading team…
            </div>
          ) : loadError ? (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-sm text-red-300 shadow-xl">
              {loadError}
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-6 py-3 font-medium">Member</th>
                    <th className="px-6 py-3 font-medium">Role</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {memberships.map(function (membership) {
                    const isDeactivated = membership.deactivated_at !== null;
                    const isBusy = busyId === membership.id;

                    let statusBadgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
                    statusBadgeClass += isDeactivated
                      ? "bg-white/10 text-gray-400"
                      : "bg-emerald-500/15 text-emerald-300";

                    return (
                      <tr key={membership.id} className="align-top transition hover:bg-white/5">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                              {initialsFor(membership.user.full_name)}
                            </div>
                            <div>
                              <p className="flex items-center gap-2 font-medium text-white">
                                {membership.user.full_name}
                                {membership.is_owner ? (
                                  <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-300">
                                    Owner
                                  </span>
                                ) : null}
                              </p>
                              <p className="text-xs text-gray-500">{membership.user.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <select
                            value={membership.role}
                            disabled={isBusy || membership.is_owner}
                            onChange={function (e) {
                              handleRoleChange(membership, e.target.value);
                            }}
                            className="rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {ROLE_OPTIONS.map(function (opt) {
                              return (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              );
                            })}
                          </select>
                          {membership.is_owner ? (
                            <p className="mt-1 text-[11px] text-gray-600">{ROLE_LABELS[membership.role] || membership.role} (fixed for the Owner)</p>
                          ) : null}
                        </td>
                        <td className="px-6 py-4">
                          <span className={statusBadgeClass}>{isDeactivated ? "Deactivated" : "Active"}</span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-col items-start gap-1">
                            {isDeactivated ? (
                              <button
                                type="button"
                                disabled={isBusy}
                                onClick={function () {
                                  handleReactivate(membership);
                                }}
                                className="rounded-lg border border-emerald-500/30 px-2.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {isBusy ? "Reactivating…" : "Reactivate"}
                              </button>
                            ) : (
                              <button
                                type="button"
                                disabled={isBusy || membership.is_owner}
                                onClick={function () {
                                  handleDeactivate(membership);
                                }}
                                className="rounded-lg border border-red-500/30 px-2.5 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {isBusy ? "Deactivating…" : "Deactivate"}
                              </button>
                            )}
                            {rowNotice && rowNotice.id === membership.id ? (
                              <p className="text-xs text-emerald-300">{rowNotice.text}</p>
                            ) : null}
                            {rowError && rowError.id === membership.id ? (
                              <p className="max-w-xs text-xs text-red-400">{rowError.text}</p>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {memberships.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">
                        No one on this page.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          )}

          {pagination ? (
            <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
              <p>
                Showing page {pagination.page} of {pagination.total_pages} ({pagination.total} people total)
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!pagination.has_previous}
                  onClick={function () {
                    setPage(function (p) {
                      return p - 1;
                    });
                  }}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={!pagination.has_next}
                  onClick={function () {
                    setPage(function (p) {
                      return p + 1;
                    });
                  }}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </main>
      </div>
    </div>
  );
}

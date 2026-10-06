"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
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

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

interface Pagination {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: Pagination;
}

interface Department {
  id: string;
  name: string;
}

interface Position {
  id: string;
  department_id: string;
  title: string;
}

interface Location {
  id: string;
  name: string;
}

interface Employee {
  id: string;
  user_id: string | null;
  invite_status: "pending" | "expired" | null;
  position_id: string;
  location_id: string | null;
  first_name: string;
  last_name: string;
  work_email: string;
  status: "active" | "inactive";
  employment_type: string | null;
}

interface GrantLoginResponse {
  outcome: "invited" | "added" | "linked";
  employee: Employee;
}

function initialsFor(firstName: string, lastName: string): string {
  const a = firstName.trim().charAt(0).toUpperCase();
  const b = lastName.trim().charAt(0).toUpperCase();
  return (a + b) || "?";
}

export default function EmployeeDirectoryPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [page, setPage] = useState(1);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [inviteRowId, setInviteRowId] = useState<string | null>(null);
  const [inviteRole, setInviteRole] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [rowNotice, setRowNotice] = useState<{ id: string; text: string } | null>(null);

  function load() {
    setLoading(true);
    setLoadError("");
    Promise.all([
      apiFetch<PaginatedResponse<Employee>>("/employees?page=" + page + "&limit=20", { method: "GET" }),
      apiFetch<PaginatedResponse<Department>>("/departments?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<Position>>("/positions?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<Location>>("/locations?limit=100", { method: "GET" }),
    ])
      .then(function ([employeesRes, departmentsRes, positionsRes, locationsRes]) {
        setEmployees(employeesRes.data);
        setPagination(employeesRes.pagination);
        setDepartments(departmentsRes.data);
        setPositions(positionsRes.data);
        setLocations(locationsRes.data);
      })
      .catch(function (err) {
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load the employee directory.");
      })
      .finally(function () {
        setLoading(false);
      });
  }

  useEffect(
    function () {
      // load() sets loading/error state synchronously before its fetches
      // resolve, so paging shows the spinner right away instead of leaving
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

  function departmentNameFor(employee: Employee): string {
    const position = positions.find(function (p) {
      return p.id === employee.position_id;
    });
    if (!position) return "—";
    const department = departments.find(function (d) {
      return d.id === position.department_id;
    });
    return department ? department.name : "—";
  }

  function positionTitleFor(employee: Employee): string {
    const position = positions.find(function (p) {
      return p.id === employee.position_id;
    });
    return position ? position.title : "—";
  }

  function locationNameFor(employee: Employee): string {
    if (!employee.location_id) return "—";
    const location = locations.find(function (l) {
      return l.id === employee.location_id;
    });
    return location ? location.name : "—";
  }

  function openInvitePicker(employeeId: string) {
    setInviteError("");
    setInviteRole("");
    setInviteRowId(employeeId);
  }

  async function sendInvite(employeeId: string) {
    if (!inviteRole) {
      setInviteError("Pick a role first.");
      return;
    }
    setInviteBusy(true);
    setInviteError("");
    try {
      const result = await apiFetch<GrantLoginResponse>("/employees/" + employeeId + "/grant-login", {
        method: "POST",
        body: { role: inviteRole },
      });
      setEmployees(function (prev) {
        return prev.map(function (e) {
          return e.id === employeeId ? result.employee : e;
        });
      });
      let noticeText = "Invite sent.";
      if (result.outcome === "added") noticeText = "They already had an account — added and linked instantly.";
      if (result.outcome === "linked") noticeText = "Linked instantly — they were already an active member.";
      setRowNotice({ id: employeeId, text: noticeText });
      setInviteRowId(null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "MEMBERSHIP_DEACTIVATED") {
        setInviteError("Their membership is deactivated — reactivate them from Team Management first.");
      } else if (err instanceof ApiError) {
        setInviteError(err.message);
      } else {
        setInviteError("Couldn't send that invite. Please try again.");
      }
    } finally {
      setInviteBusy(false);
    }
  }

  const filteredEmployees = employees.filter(function (employee) {
    if (statusFilter !== "all" && employee.status !== statusFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const name = (employee.first_name + " " + employee.last_name).toLowerCase();
      if (!name.includes(q) && !employee.work_email.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Employees</p>
            <h1 className="text-xl font-bold text-white">Employees</h1>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                </span>
                <input
                  type="text"
                  value={search}
                  onChange={function (e) {
                    setSearch(e.target.value);
                  }}
                  placeholder="Search this page by name or email..."
                  className="w-64 rounded-lg border border-white/10 bg-[#0a0e1a] py-2 pl-9 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
              </div>
              <select
                value={statusFilter}
                onChange={function (e) {
                  setStatusFilter(e.target.value);
                }}
                className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500"
              >
                <option value="all">Status: All</option>
                <option value="active">Active</option>
                <option value="inactive">Offboarded</option>
              </select>
            </div>
            <button
              type="button"
              onClick={function () {
                router.push("/employees/add");
              }}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              + Add Employee
            </button>
          </div>

          {loading ? (
            <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-sm text-gray-400 shadow-xl">
              Loading employees…
            </div>
          ) : loadError ? (
            <div className="mt-6 rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-sm text-red-300 shadow-xl">
              {loadError}
            </div>
          ) : (
            <div className="mt-6 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-6 py-3 font-medium">Employee</th>
                    <th className="px-6 py-3 font-medium">Department</th>
                    <th className="px-6 py-3 font-medium">Position</th>
                    <th className="px-6 py-3 font-medium">Location</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Login</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredEmployees.map(function (employee) {
                    let statusBadgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
                    statusBadgeClass +=
                      employee.status === "active"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-white/10 text-gray-400";

                    return (
                      <tr key={employee.id} className="transition hover:bg-white/5">
                        <td
                          className="cursor-pointer px-6 py-4"
                          onClick={function () {
                            router.push("/employees/" + employee.id);
                          }}
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                              {initialsFor(employee.first_name, employee.last_name)}
                            </div>
                            <div>
                              <p className="font-medium text-white">
                                {employee.first_name} {employee.last_name}
                              </p>
                              <p className="text-xs text-gray-500">{employee.work_email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-gray-300">{departmentNameFor(employee)}</td>
                        <td className="px-6 py-4 text-gray-300">{positionTitleFor(employee)}</td>
                        <td className="px-6 py-4 text-gray-300">{locationNameFor(employee)}</td>
                        <td className="px-6 py-4">
                          <span className={statusBadgeClass}>{employee.status === "active" ? "Active" : "Offboarded"}</span>
                        </td>
                        <td className="px-6 py-4">
                          {rowNotice && rowNotice.id === employee.id ? (
                            <p className="text-xs text-emerald-300">{rowNotice.text}</p>
                          ) : employee.user_id ? (
                            <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">
                              Has login
                            </span>
                          ) : inviteRowId === employee.id ? (
                            <div className="flex items-center gap-2">
                              <select
                                value={inviteRole}
                                onChange={function (e) {
                                  setInviteRole(e.target.value);
                                }}
                                className="rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500"
                              >
                                <option value="">Role…</option>
                                {ROLE_OPTIONS.map(function (opt) {
                                  return (
                                    <option key={opt.value} value={opt.value}>
                                      {opt.label}
                                    </option>
                                  );
                                })}
                              </select>
                              <button
                                type="button"
                                disabled={inviteBusy}
                                onClick={function () {
                                  sendInvite(employee.id);
                                }}
                                className="rounded-lg bg-indigo-500 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
                              >
                                {inviteBusy ? "…" : "Send"}
                              </button>
                              <button
                                type="button"
                                onClick={function () {
                                  setInviteRowId(null);
                                }}
                                className="text-xs text-gray-500 hover:text-gray-300"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              {employee.invite_status === "pending" ? (
                                <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400">
                                  Invite pending
                                </span>
                              ) : employee.invite_status === "expired" ? (
                                <span className="rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-300">
                                  Invite expired
                                </span>
                              ) : null}
                              <button
                                type="button"
                                onClick={function () {
                                  openInvitePicker(employee.id);
                                }}
                                className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-indigo-300 hover:bg-white/5"
                              >
                                {employee.invite_status ? "Resend invite" : "Send invite"}
                              </button>
                            </div>
                          )}
                          {inviteRowId === employee.id && inviteError ? (
                            <p className="mt-1 text-xs text-red-400">{inviteError}</p>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredEmployees.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                        No employees match this page&apos;s filters.
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
                Showing page {pagination.page} of {pagination.total_pages} ({pagination.total} employees total)
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

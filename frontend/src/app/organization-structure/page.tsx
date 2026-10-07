"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import PositionsEditor from "@/components/PositionsEditor";

const SIDEBAR_ITEMS: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Employees", href: "/employees" },
  { label: "Team Management", href: "/team-management" },
  { label: "Organization Structure", href: "/organization-structure" },
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

interface Department {
  id: string;
  name: string;
  is_critical: boolean;
  // null = no head yet. Optional so an older server response without the
  // field simply reads as "no head set".
  head_employee_id?: string | null;
}

interface Employee {
  id: string;
  first_name: string;
  last_name: string;
  status: string;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

async function fetchAllPages<T>(path: string): Promise<T[]> {
  const all: T[] = [];
  let page = 1;
  const joiner = path.indexOf("?") === -1 ? "?" : "&";
  while (page <= 50) {
    const res = await apiFetch<PaginatedResponse<T>>(path + joiner + "page=" + page + "&limit=100", {
      method: "GET",
    });
    for (const item of res.data) {
      all.push(item);
    }
    if (!res.pagination.has_next) break;
    page = page + 1;
  }
  return all;
}

function fullName(employee: Employee): string {
  return (employee.first_name + " " + employee.last_name).trim();
}

export default function OrganizationStructurePage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(function () {
    let cancelled = false;
    Promise.all([
      fetchAllPages<Department>("/departments"),
      fetchAllPages<Employee>("/employees"),
    ])
      .then(function (results) {
        if (cancelled) return;
        setDepartments(results[0]);
        setEmployees(results[1]);
      })
      .catch(function (err) {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load your organization structure.");
      })
      .finally(function () {
        if (!cancelled) setLoading(false);
      });
    return function () {
      cancelled = true;
    };
  }, []);

  async function refreshEmployees() {
    try {
      const list = await fetchAllPages<Employee>("/employees");
      setEmployees(list);
    } catch {
      // The picker just keeps its previous list if this refresh fails.
    }
  }

  async function refreshDepartments() {
    try {
      const list = await fetchAllPages<Department>("/departments");
      setDepartments(list);
    } catch {
      // Keep what is on screen.
    }
  }

  function employeeName(id: string): string {
    for (const e of employees) {
      if (e.id === id) return fullName(e);
    }
    return "Unknown employee";
  }

  // Any ACTIVE employee of the organization can head a department — they
  // don't have to belong to it, and one person can head several. GET
  // /employees also returns offboarded people, so hide those.
  const activeEmployees = employees.filter(function (e) {
    return e.status !== "inactive";
  });

  async function changeHead(department: Department, employeeId: string) {
    setActionError("");
    setNotice("");
    setBusyId(department.id);
    try {
      // null REMOVES the head; a uuid sets/changes it. Only this one field
      // is sent, so the department's other settings are never touched.
      const updated = await apiFetch<Department>("/departments/" + department.id, {
        method: "PATCH",
        body: { head_employee_id: employeeId ? employeeId : null },
      });
      setDepartments(
        departments.map(function (d) {
          if (d.id !== department.id) return d;
          return { ...d, head_employee_id: updated.head_employee_id === undefined ? (employeeId ? employeeId : null) : updated.head_employee_id };
        })
      );
      setNotice(
        employeeId
          ? employeeName(employeeId) + " is now the head of " + department.name + "."
          : department.name + " no longer has a head."
      );
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update that department's head.");
      // The picked person may have been offboarded (or removed) after this
      // list loaded — refresh both so the picker stops offering them and
      // any head the server cleared shows correctly.
      if (err instanceof ApiError && (err.code === "EMPLOYEE_NOT_FOUND" || err.code === "VALIDATION_FAILED")) {
        await refreshEmployees();
        await refreshDepartments();
      }
    } finally {
      setBusyId(null);
    }
  }

  const selectClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-60";

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Organization Structure")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Organization Structure</p>
            <h1 className="text-xl font-bold text-white">Organization Structure</h1>
          </div>
        </div>

        <main className="flex-1 space-y-6 px-8 py-8">
          {loading ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-sm text-gray-400 shadow-xl">
              Loading organization…
            </div>
          ) : loadError ? (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-sm text-red-300 shadow-xl">
              {loadError}
            </div>
          ) : (
            <>
              <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Departments &amp; heads</h2>
                  <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
                    {departments.length} Total
                  </span>
                </div>
                <p className="mt-1 max-w-2xl text-sm text-gray-500">
                  A department&apos;s head is its manager for the product: they are alerted when a task is
                  late, and workflow tasks land with them when nobody is assigned. This is not the same as
                  a person&apos;s reporting manager. Any active employee can be picked, even from another
                  department.
                </p>

                {actionError ? (
                  <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                    {actionError}
                  </div>
                ) : null}
                {notice ? (
                  <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                    {notice}
                  </div>
                ) : null}

                <div className="mt-4 space-y-3">
                  {departments.length === 0 ? (
                    <p className="text-sm text-gray-500">
                      No departments yet. Add them in the organization setup step first.
                    </p>
                  ) : null}

                  {departments.map(function (department) {
                    const headId = department.head_employee_id || "";
                    const headIsListed =
                      headId === "" ||
                      activeEmployees.some(function (e) {
                        return e.id === headId;
                      });
                    const isBusy = busyId === department.id;
                    return (
                      <div
                        key={department.id}
                        className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
                      >
                        <div>
                          <p className="flex items-center gap-2 text-sm font-medium">
                            {department.name}
                            {department.is_critical ? (
                              <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
                                Critical
                              </span>
                            ) : null}
                          </p>
                          <p className="text-xs text-gray-500">
                            {headId ? "Head: " + employeeName(headId) : "No head set"}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <label className="text-xs text-gray-500">Head</label>
                          <select
                            value={headId}
                            disabled={isBusy}
                            onChange={function (e) {
                              changeHead(department, e.target.value);
                            }}
                            className={selectClass}
                          >
                            <option value="">No head</option>
                            {!headIsListed ? (
                              <option value={headId}>{employeeName(headId)} (no longer active)</option>
                            ) : null}
                            {activeEmployees.map(function (e) {
                              return (
                                <option key={e.id} value={e.id}>
                                  {fullName(e)}
                                </option>
                              );
                            })}
                          </select>
                        </div>
                      </div>
                    );
                  })}

                  {departments.length > 0 && activeEmployees.length === 0 ? (
                    <p className="text-xs text-amber-300">
                      There are no active employees to choose from yet. Add employees first, then come back
                      to set each department&apos;s head.
                    </p>
                  ) : null}
                </div>
              </div>

              <PositionsEditor departments={departments} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}

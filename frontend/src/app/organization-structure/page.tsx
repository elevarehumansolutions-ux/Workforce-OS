"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import PositionsEditor from "@/components/PositionsEditor";
import { isHrRole, loadMe } from "@/lib/settings";
import { personLabel } from "@/lib/personLabel";
import { roleLabel } from "@/lib/tasks";

import RoleSidebarNav from "@/components/SidebarNav";
import Logo from "@/components/Logo";
import MobileNav from "@/components/MobileNav";
import UserMenu from "@/components/UserMenu";

// The menu is shared (and filtered by role) in components/SidebarNav.tsx.
function SidebarNav(activeLabel: string) {
  return <RoleSidebarNav activeLabel={activeLabel} />;
}

function SidebarShell(activeLabel: string) {
  return (
    <aside className="hidden w-64 flex-col justify-between border-r border-white/10 bg-[#0a0e1a] py-6 lg:flex">
      <div>
        <div className="mb-8 flex items-center gap-3 px-6">
          <Logo size={36} textClassName="text-base font-bold text-white" />
        </div>
        {SidebarNav(activeLabel)}
      </div>
      <UserMenu />
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
  position_id?: string | null;
  // The login this person signs in with, if they have one.
  user_id?: string | null;
}

// One login's access level in this company. Only HR can read the list.
interface Membership {
  role: string;
  user: { id: string };
}

interface Position {
  id: string;
  title: string;
  department_id: string;
  reports_to_position_id: string | null;
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

// Access level of each login, by user id. Only HR may read the team list, so for anyone else
// (or if it fails) this is empty and the page just cannot name the old head's access level.
async function loadAccessLevels(): Promise<Record<string, string>> {
  const levels: Record<string, string> = {};
  try {
    const me = await loadMe();
    if (!isHrRole(me.role)) return levels;
    const rows = await fetchAllPages<Membership>("/memberships");
    for (const row of rows) levels[row.user.id] = row.role;
  } catch {
    // Keep what we have.
  }
  return levels;
}

export default function OrganizationStructurePage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  // Only HR can change a department's head; everyone else sees it read-only.
  const [canEdit, setCanEdit] = useState(false);
  // Access level of each login, by user id (HR only). Used to say what the replaced head's level still is.
  const [accessLevels, setAccessLevels] = useState<Record<string, string>>({});
  // Set after a head was replaced: who it was and the access level they still have.
  const [formerHead, setFormerHead] = useState<{ name: string; department: string; level: string } | null>(null);

  useEffect(function () {
    let cancelled = false;
    Promise.all([
      fetchAllPages<Department>("/departments"),
      fetchAllPages<Employee>("/employees"),
      loadMe(),
      fetchAllPages<Position>("/positions"),
      loadAccessLevels(),
    ])
      .then(function (results) {
        if (cancelled) return;
        setDepartments(results[0]);
        setEmployees(results[1]);
        setCanEdit(isHrRole(results[2].role));
        setPositions(results[3]);
        setAccessLevels(results[4]);
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

  function departmentOfPosition(positionId: string | null | undefined): string {
    const position = positions.find(function (p) { return p.id === positionId; });
    return position ? position.department_id : "";
  }

  // Active people for the Head dropdown: this department's own people first, then everyone else.
  function headChoices(department: Department): Employee[] {
    const own: Employee[] = [];
    const others: Employee[] = [];
    activeEmployees.forEach(function (e) {
      if (departmentOfPosition(e.position_id) === department.id) {
        own.push(e);
      } else {
        others.push(e);
      }
    });
    return own.concat(others);
  }

  // The person to suggest as head: the one holder of the department's top role, meaning a role
  // whose boss is outside the department (or nobody). Only when exactly one person holds those
  // roles, so it is never a guess; with several holders HR chooses.
  function suggestedHead(department: Department): Employee | null {
    const topRoleIds: string[] = [];
    positions.forEach(function (p) {
      if (p.department_id !== department.id) return;
      const bossDepartment = departmentOfPosition(p.reports_to_position_id);
      if (!p.reports_to_position_id || bossDepartment !== department.id) {
        topRoleIds.push(p.id);
      }
    });
    const holders = activeEmployees.filter(function (e) {
      return e.position_id ? topRoleIds.indexOf(e.position_id) !== -1 : false;
    });
    return holders.length === 1 ? holders[0] : null;
  }

  // The old head keeps their access level (they may still manage people elsewhere), so we say so
  // and let HR change it. Only for someone with a login: others have no access level.
  function rememberFormerHead(oldHeadId: string, newHeadId: string, departmentName: string) {
    if (oldHeadId === "" || oldHeadId === newHeadId) return;
    const oldHead = employees.find(function (e) { return e.id === oldHeadId; });
    if (!oldHead || !oldHead.user_id) return;
    const level = accessLevels[oldHead.user_id];
    if (!level) return;
    setFormerHead({ name: fullName(oldHead), department: departmentName, level: roleLabel(level) });
  }

  async function changeHead(department: Department, employeeId: string) {
    setActionError("");
    setNotice("");
    setFormerHead(null);
    setBusyId(department.id);
    // Read the old head BEFORE the change: after it, the department points at the new one.
    const oldHeadId = department.head_employee_id || "";
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
      rememberFormerHead(oldHeadId, employeeId, department.name);
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

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav activeLabel="Organization Structure" />
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
                {formerHead && notice ? (
                  <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                    {formerHead.name} is no longer head of {formerHead.department}. Their access level is still {formerHead.level}.{" "}
                    <Link href="/team-management" className="font-medium underline">
                      Change it
                    </Link>
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
                            disabled={isBusy || !canEdit}
                            onChange={function (e) {
                              changeHead(department, e.target.value);
                            }}
                            className={selectClass}
                          >
                            <option value="">No head</option>
                            {!headIsListed ? (
                              <option value={headId}>{employeeName(headId)} (no longer active)</option>
                            ) : null}
                            {headChoices(department).map(function (e) {
                              return (
                                <option key={e.id} value={e.id}>
                                  {personLabel(e, positions, departments)}
                                </option>
                              );
                            })}
                          </select>
                        </div>
                        {headId === "" && canEdit && suggestedHead(department) ? (
                          <p className="w-full text-xs text-gray-400">
                            Suggested: {fullName(suggestedHead(department) as Employee)}, who holds this department&apos;s
                            top role.{" "}
                            <button
                              type="button"
                              disabled={isBusy}
                              onClick={function () { changeHead(department, (suggestedHead(department) as Employee).id); }}
                              className="font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50"
                            >
                              Make them head
                            </button>
                          </p>
                        ) : null}
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

              {canEdit ? (
                <PositionsEditor departments={departments} people={employees} />
              ) : (
                <p className="text-sm text-gray-400">The chart of roles is managed by HR administrators.</p>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

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

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

const EMPLOYMENT_TYPE_LABELS: Record<string, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  temporary: "Temporary",
  intern: "Intern",
};

interface Employee {
  id: string;
  user_id: string | null;
  invite_status: "pending" | "expired" | null;
  position_id: string;
  manager_id: string | null;
  location_id: string | null;
  employee_code: string | null;
  first_name: string;
  last_name: string;
  work_email: string;
  phone_number: string | null;
  address: string | null;
  employment_type: string | null;
  start_date: string;
  status: "active" | "inactive";
}

interface Position {
  id: string;
  department_id: string;
  title: string;
}

interface Department {
  id: string;
  name: string;
}

interface Location {
  id: string;
  name: string;
}

interface UnlinkedMember {
  id: string;
  user: { id: string; email: string; full_name: string };
}

interface GrantLoginResponse {
  outcome: "invited" | "added" | "linked";
  employee: Employee;
}

const TABS = ["Overview", "Attendance", "Schedule", "Leave", "KPIs"];

export default function EmployeeDetailsPage() {
  const router = useRouter();
  const params = useParams();
  const employeeId = typeof params.id === "string" ? params.id : "";

  const [activeTab, setActiveTab] = useState("Overview");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [manager, setManager] = useState<Employee | null>(null);

  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  const [showInvitePicker, setShowInvitePicker] = useState(false);
  const [inviteRole, setInviteRole] = useState("");

  const [showLinkPicker, setShowLinkPicker] = useState(false);
  const [unlinkedMembers, setUnlinkedMembers] = useState<UnlinkedMember[]>([]);
  const [linkUserId, setLinkUserId] = useState("");

  function load() {
    if (!employeeId) return;
    setLoading(true);
    setLoadError("");
    Promise.all([
      apiFetch<Employee>("/employees/" + employeeId, { method: "GET" }),
      apiFetch<{ data: Position[] }>("/positions?limit=100", { method: "GET" }),
      apiFetch<{ data: Department[] }>("/departments?limit=100", { method: "GET" }),
      apiFetch<{ data: Location[] }>("/locations?limit=100", { method: "GET" }),
    ])
      .then(function ([employeeRes, positionsRes, departmentsRes, locationsRes]) {
        setEmployee(employeeRes);
        setPositions(positionsRes.data);
        setDepartments(departmentsRes.data);
        setLocations(locationsRes.data);
        if (employeeRes.manager_id) {
          return apiFetch<Employee>("/employees/" + employeeRes.manager_id, { method: "GET" })
            .then(setManager)
            .catch(function () {
              setManager(null);
            });
        }
        setManager(null);
      })
      .catch(function (err) {
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load this employee.");
      })
      .finally(function () {
        setLoading(false);
      });
  }

  useEffect(
    function () {
      // load() sets loading/error state synchronously before its fetches
      // resolve, so the switch-employee case (navigating from one
      // /employees/[id] to another without a remount) shows the spinner
      // right away instead of leaving the previous employee's details on
      // screen while the new ones load.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      load();
    },
    // load is re-created every render (it closes over employeeId), so
    // listing it here would re-run this effect on every render instead of
    // only when the id actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [employeeId]
  );

  function positionTitle(): string {
    if (!employee) return "—";
    const position = positions.find(function (p) {
      return p.id === employee.position_id;
    });
    return position ? position.title : "—";
  }

  function departmentName(): string {
    if (!employee) return "—";
    const position = positions.find(function (p) {
      return p.id === employee.position_id;
    });
    if (!position) return "—";
    const department = departments.find(function (d) {
      return d.id === position.department_id;
    });
    return department ? department.name : "—";
  }

  function locationName(): string {
    if (!employee || !employee.location_id) return "—";
    const locationId = employee.location_id;
    const location = locations.find(function (l) {
      return l.id === locationId;
    });
    return location ? location.name : "—";
  }

  async function handleSendInvite() {
    if (!employee) return;
    if (!inviteRole) {
      setActionError("Pick a role first.");
      return;
    }
    setActionBusy(true);
    setActionError("");
    try {
      const result = await apiFetch<GrantLoginResponse>("/employees/" + employee.id + "/grant-login", {
        method: "POST",
        body: { role: inviteRole },
      });
      setEmployee(result.employee);
      let notice = "Invite sent to " + result.employee.work_email + ".";
      if (result.outcome === "added") notice = "They already had an account — added and linked instantly.";
      if (result.outcome === "linked") notice = "Linked instantly — they were already an active member.";
      setActionNotice(notice);
      setShowInvitePicker(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "MEMBERSHIP_DEACTIVATED") {
        setActionError("Their membership is deactivated — reactivate them from Team Management first.");
      } else if (err instanceof ApiError && err.code === "EMPLOYEE_ALREADY_HAS_LOGIN") {
        setActionError("This employee already has a login.");
      } else if (err instanceof ApiError) {
        setActionError(err.message);
      } else {
        setActionError("Couldn't send that invite. Please try again.");
      }
    } finally {
      setActionBusy(false);
    }
  }

  function openLinkPicker() {
    setActionError("");
    setLinkUserId("");
    setShowLinkPicker(true);
    apiFetch<{ data: UnlinkedMember[] }>("/employees/unlinked-members?limit=100", { method: "GET" })
      .then(function (res) {
        setUnlinkedMembers(res.data);
      })
      .catch(function (err) {
        setActionError(err instanceof ApiError ? err.message : "Couldn't load members to link.");
      });
  }

  async function handleLinkUser() {
    if (!employee || !linkUserId) return;
    setActionBusy(true);
    setActionError("");
    try {
      const updated = await apiFetch<Employee>("/employees/" + employee.id + "/link-user", {
        method: "POST",
        body: { user_id: linkUserId },
      });
      setEmployee(updated);
      setActionNotice("Linked — this login now belongs to this employee record.");
      setShowLinkPicker(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.message);
      } else {
        setActionError("Couldn't link that member. Please try again.");
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function handleOffboard() {
    if (!employee) return;
    if (!window.confirm("Offboard " + employee.first_name + " " + employee.last_name + "? This also deactivates their login if they have one.")) {
      return;
    }
    setActionBusy(true);
    setActionError("");
    try {
      const updated = await apiFetch<Employee>("/employees/" + employee.id + "/offboard", { method: "POST" });
      setEmployee(updated);
      setActionNotice("Offboarded.");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't offboard this employee.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleReinstate() {
    if (!employee) return;
    setActionBusy(true);
    setActionError("");
    try {
      const updated = await apiFetch<Employee>("/employees/" + employee.id + "/reinstate", { method: "POST" });
      setEmployee(updated);
      setActionNotice("Reinstated — login access is restored if they had any.");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't reinstate this employee.");
    } finally {
      setActionBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen w-full bg-[#05070f] text-white">
        {SidebarShell("Employees")}
        <div className="flex flex-1 items-center justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
        </div>
      </div>
    );
  }

  if (loadError || !employee) {
    return (
      <div className="flex min-h-screen w-full bg-[#05070f] text-white">
        {SidebarShell("Employees")}
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-8 text-center">
          <p className="text-sm text-red-300">{loadError || "Employee not found."}</p>
          <button
            type="button"
            onClick={function () {
              router.push("/employees/directory");
            }}
            className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
          >
            Back to Directory
          </button>
        </div>
      </div>
    );
  }

  const initials =
    (employee.first_name.charAt(0) + employee.last_name.charAt(0)).toUpperCase() || "?";
  let statusBadgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  statusBadgeClass += employee.status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-white/10 text-gray-400";

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">
              Employees &gt; {employee.first_name} {employee.last_name}
            </p>
            <h1 className="text-xl font-bold text-white">
              {employee.first_name} {employee.last_name}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {employee.status === "active" ? (
              <button
                type="button"
                onClick={handleOffboard}
                disabled={actionBusy}
                className="rounded-lg border border-red-500/30 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/10 disabled:opacity-60"
              >
                Offboard
              </button>
            ) : (
              <button
                type="button"
                onClick={handleReinstate}
                disabled={actionBusy}
                className="rounded-lg border border-emerald-500/30 px-4 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/10 disabled:opacity-60"
              >
                Reinstate
              </button>
            )}
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          {actionNotice ? (
            <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
              {actionNotice}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex flex-col items-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-indigo-500 text-lg font-bold text-white">
                  {initials}
                </div>
                <h2 className="mt-4 text-base font-semibold text-white">
                  {employee.first_name} {employee.last_name}
                </h2>
                <p className="text-sm text-gray-400">{positionTitle()}</p>
                <p className="mt-1 text-sm font-medium text-indigo-300">{departmentName()}</p>
                <span className={statusBadgeClass + " mt-2"}>{employee.status === "active" ? "Active" : "Offboarded"}</span>
              </div>

              <div className="mt-6 flex flex-col gap-3 border-t border-white/10 pt-4 text-sm text-gray-300">
                <div className="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="m3 7 9 6 9-6" />
                  </svg>
                  <span>{employee.work_email}</span>
                </div>
                {employee.phone_number ? (
                  <div className="flex items-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92Z" />
                    </svg>
                    <span>{employee.phone_number}</span>
                  </div>
                ) : null}
              </div>

              <div className="mt-6 border-t border-white/10 pt-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Login Access</p>
                {employee.user_id ? (
                  <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">
                    Has login
                  </span>
                ) : employee.status === "inactive" ? (
                  <p className="text-xs text-gray-500">
                    Offboarded. Reinstate this employee to send an invite or link a login.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {employee.invite_status === "pending" ? (
                      <span className="block w-fit rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400">
                        Invite pending
                      </span>
                    ) : employee.invite_status === "expired" ? (
                      <span className="block w-fit rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-300">
                        Invite expired
                      </span>
                    ) : null}

                    {showInvitePicker ? (
                      <div className="space-y-2">
                        <select
                          value={inviteRole}
                          onChange={function (e) {
                            setInviteRole(e.target.value);
                          }}
                          className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500"
                        >
                          <option value="">Select role</option>
                          {ROLE_OPTIONS.map(function (opt) {
                            return (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            );
                          })}
                        </select>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={actionBusy}
                            onClick={handleSendInvite}
                            className="flex-1 rounded-lg bg-indigo-500 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
                          >
                            {actionBusy ? "Sending…" : "Confirm"}
                          </button>
                          <button
                            type="button"
                            onClick={function () {
                              setShowInvitePicker(false);
                            }}
                            className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-gray-400 hover:bg-white/5"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : showLinkPicker ? (
                      <div className="space-y-2">
                        <select
                          value={linkUserId}
                          onChange={function (e) {
                            setLinkUserId(e.target.value);
                          }}
                          className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500"
                        >
                          <option value="">Select member</option>
                          {unlinkedMembers.map(function (m) {
                            return (
                              <option key={m.user.id} value={m.user.id}>
                                {m.user.full_name} ({m.user.email})
                              </option>
                            );
                          })}
                        </select>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={actionBusy || !linkUserId}
                            onClick={handleLinkUser}
                            className="flex-1 rounded-lg bg-indigo-500 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-60"
                          >
                            {actionBusy ? "Linking…" : "Confirm"}
                          </button>
                          <button
                            type="button"
                            onClick={function () {
                              setShowLinkPicker(false);
                            }}
                            className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-gray-400 hover:bg-white/5"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <button
                          type="button"
                          onClick={function () {
                            setActionError("");
                            setInviteRole("");
                            setShowInvitePicker(true);
                          }}
                          className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-indigo-300 hover:bg-white/5"
                        >
                          {employee.invite_status ? "Resend invite" : "Send invite"}
                        </button>
                        <button
                          type="button"
                          onClick={openLinkPicker}
                          className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5"
                        >
                          Link existing member
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {actionError ? <p className="mt-2 text-xs text-red-400">{actionError}</p> : null}
              </div>
            </div>

            <div>
              <div className="flex gap-6 border-b border-white/10">
                {TABS.map(function (tab) {
                  const isActive = tab === activeTab;
                  let tabClass = "pb-3 text-sm font-medium transition ";
                  if (isActive) {
                    tabClass = tabClass + "border-b-2 border-indigo-500 text-white";
                  } else {
                    tabClass = tabClass + "text-gray-500 hover:text-gray-300";
                  }
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={function () {
                        setActiveTab(tab);
                      }}
                      className={tabClass}
                    >
                      {tab}
                    </button>
                  );
                })}
              </div>

              {activeTab === "Overview" ? (
                <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                  <h3 className="mb-4 text-base font-semibold text-white">Employment Details</h3>
                  <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Employee Code</p>
                      <p className="mt-1 text-sm text-white">{employee.employee_code || "—"}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Address</p>
                      <p className="mt-1 text-sm text-white">{employee.address || "—"}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Employment Type</p>
                      <p className="mt-1 text-sm text-white">
                        {employee.employment_type ? EMPLOYMENT_TYPE_LABELS[employee.employment_type] || employee.employment_type : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Manager</p>
                      <p className="mt-1 text-sm text-white">
                        {manager ? manager.first_name + " " + manager.last_name : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Location</p>
                      <p className="mt-1 text-sm text-white">{locationName()}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Start Date</p>
                      <p className="mt-1 text-sm text-white">{employee.start_date}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 text-sm text-gray-500 shadow-xl">
                  {activeTab} content coming soon.
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

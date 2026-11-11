"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import Link from "next/link";
import OrgChartPicker from "@/components/OrgChartPicker";
import { personLabel } from "@/lib/personLabel";

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

// Matches MembershipRole on the backend exactly.
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "manager", label: "Manager" },
  { value: "hr_administrator", label: "HR Administrator" },
  { value: "business_executive", label: "Business Executive" },
  { value: "system_administrator", label: "System Administrator" },
];

// Matches EmploymentType on the backend exactly.
const EMPLOYMENT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "temporary", label: "Temporary" },
  { value: "intern", label: "Intern" },
];

interface PaginatedResponse<T> {
  data: T[];
  pagination: { page: number; limit: number; total: number; total_pages: number; has_next: boolean; has_previous: boolean };
}

interface Department {
  id: string;
  name: string;
}

interface Position {
  id: string;
  department_id: string;
  title: string;
  reports_to_position_id: string | null;
}

interface Location {
  id: string;
  name: string;
}

interface EmployeeSummary {
  id: string;
  first_name: string;
  last_name: string;
  work_email: string;
  position_id?: string | null;
  status?: string | null;
}

interface UnlinkedMember {
  id: string;
  role: string;
  user: { id: string; email: string; full_name: string };
}

interface EmployeeResponse {
  id: string;
  user_id: string | null;
  invite_status: "pending" | "expired" | null;
  work_email: string;
}

type LoginMode = "none" | "invite" | "link";

interface FormState {
  firstName: string;
  lastName: string;
  workEmail: string;
  phoneNumber: string;
  address: string;
  positionId: string;
  managerId: string;
  locationId: string;
  employeeCode: string;
  employmentType: string;
  startDate: string;
  loginMode: LoginMode;
  role: string;
  linkedUserId: string;
}

const INITIAL_FORM: FormState = {
  firstName: "",
  lastName: "",
  workEmail: "",
  phoneNumber: "",
  address: "",
  positionId: "",
  managerId: "",
  locationId: "",
  employeeCode: "",
  employmentType: "",
  startDate: "",
  loginMode: "invite",
  role: "",
  linkedUserId: "",
};

export default function AddEmployeePage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  // Shown after "Save and add another": who was just added, with a link to their profile.
  const [savedNotice, setSavedNotice] = useState<{ name: string; id: string } | null>(null);

  // Reference data needed to fill in the dropdowns. All start empty so the
  // server and client render the same thing on first paint; the real lists
  // are loaded in the effect below, after mount.
  const [loadingRefData, setLoadingRefData] = useState(true);
  const [refDataError, setRefDataError] = useState("");
  const [positions, setPositions] = useState<Position[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [existingEmployees, setExistingEmployees] = useState<EmployeeSummary[]>([]);
  // Which chart window is open: choosing the role, or choosing the manager.
  const [picker, setPicker] = useState<"position" | "manager" | null>(null);
  const [unlinkedMembers, setUnlinkedMembers] = useState<UnlinkedMember[]>([]);

  useEffect(function () {
    Promise.all([
      apiFetch<PaginatedResponse<Position>>("/positions?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<Department>>("/departments?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<Location>>("/locations?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<EmployeeSummary>>("/employees?limit=100", { method: "GET" }),
      apiFetch<PaginatedResponse<UnlinkedMember>>("/employees/unlinked-members?limit=100", { method: "GET" }),
    ])
      .then(function ([positionsRes, departmentsRes, locationsRes, employeesRes, unlinkedRes]) {
        setPositions(positionsRes.data);
        setDepartments(departmentsRes.data);
        setLocations(locationsRes.data);
        setExistingEmployees(employeesRes.data);
        setUnlinkedMembers(unlinkedRes.data);
      })
      .catch(function (err) {
        setRefDataError(err instanceof ApiError ? err.message : "Couldn't load the form's reference data.");
      })
      .finally(function () {
        setLoadingRefData(false);
      });
  }, []);

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm(function (prev) {
      return { ...prev, [field]: value };
    });
  }

  // The person who holds the role directly above the chosen one: the likely manager.
  // Only offered when exactly one active person holds it, so it is never a guess.
  let suggestedManager: { id: string; name: string } | null = null;
  const chosenPosition = positions.find(function (p) { return p.id === form.positionId; });
  if (chosenPosition && chosenPosition.reports_to_position_id) {
    const bossRole = chosenPosition.reports_to_position_id;
    const holders = existingEmployees.filter(function (e) {
      return e.position_id === bossRole && e.status !== "inactive";
    });
    if (holders.length === 1) {
      suggestedManager = { id: holders[0].id, name: holders[0].first_name + " " + holders[0].last_name };
    }
  }

  // People who could be the manager: everyone not offboarded. Those who hold the role directly
  // above the chosen one come first (the likely managers), then the rest.
  const bossRoleId = chosenPosition ? chosenPosition.reports_to_position_id : null;
  const likelyManagers: EmployeeSummary[] = [];
  const otherPeople: EmployeeSummary[] = [];
  existingEmployees.forEach(function (e) {
    // "inactive" is what the server calls someone who has been offboarded.
    if (e.status === "inactive") return;
    if (bossRoleId && e.position_id === bossRoleId) {
      likelyManagers.push(e);
    } else {
      otherPeople.push(e);
    }
  });
  const managerChoices = likelyManagers.concat(otherPeople);

  // The role above the chosen one exists but nobody holds it yet: say so, so the person
  // adding employees knows to add the boss first (or leave the manager empty).
  const bossRole = bossRoleId
    ? positions.find(function (p) { return p.id === bossRoleId; })
    : undefined;
  const bossRoleIsEmpty = bossRole !== undefined && likelyManagers.length === 0;

  function departmentNameFor(position: Position): string {
    const department = departments.find(function (d) {
      return d.id === position.department_id;
    });
    return department ? department.name : "Unknown department";
  }

  // The form's own submit (pressing Enter) means "save and finish".
  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    saveEmployee("finish");
  }

  // "another": stay on this page ready for the next person. "finish": go to the directory.
  async function saveEmployee(next: "another" | "finish") {
    setFormError("");
    setSavedNotice(null);

    if (!form.positionId) {
      setFormError("Position is required. Pick one below.");
      return;
    }
    if (!form.startDate) {
      setFormError("Start date is required.");
      return;
    }
    if (form.loginMode === "invite" && !form.role) {
      setFormError("Pick a role to go with the login invite.");
      return;
    }
    if (form.loginMode === "link" && !form.linkedUserId) {
      setFormError("Pick which existing member to link.");
      return;
    }

    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        position_id: form.positionId,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        work_email: form.workEmail.trim(),
        start_date: form.startDate,
        manager_id: form.managerId || null,
        location_id: form.locationId || null,
        employee_code: form.employeeCode.trim() || null,
        phone_number: form.phoneNumber.trim() || null,
        address: form.address.trim() || null,
        employment_type: form.employmentType || null,
      };
      if (form.loginMode === "invite") {
        payload.grant_login_access = true;
        payload.role = form.role;
      } else if (form.loginMode === "link") {
        payload.user_id = form.linkedUserId;
      }

      const employee = await apiFetch<EmployeeResponse>("/employees", {
        method: "POST",
        body: payload,
      });
      if (next === "finish") {
        router.push("/employees/directory");
        return;
      }

      // Add another: the new person can now be someone's manager, so add them to the choices.
      setExistingEmployees(existingEmployees.concat([{
        id: employee.id,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        work_email: form.workEmail.trim(),
        position_id: form.positionId,
        status: "active",
      }]));
      // A login that was just linked can't be linked to a second person.
      setUnlinkedMembers(unlinkedMembers.filter(function (m) { return m.user.id !== form.linkedUserId; }));

      setSavedNotice({ name: (form.firstName + " " + form.lastName).trim(), id: employee.id });
      // Keep where the next person usually sits (role, manager, location, type, start date);
      // clear what is personal to one individual.
      setForm({
        ...INITIAL_FORM,
        positionId: form.positionId,
        managerId: form.managerId,
        locationId: form.locationId,
        employmentType: form.employmentType,
        startDate: form.startDate,
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't save this employee. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav activeLabel="Employees" />
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Employees &gt; Add Employee</p>
            <h1 className="text-xl font-bold text-white">Add New Employee</h1>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          {loadingRefData ? (
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-sm text-gray-400 shadow-xl">
              Loading form…
            </div>
          ) : refDataError ? (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-sm text-red-300 shadow-xl">
              {refDataError}
            </div>
          ) : positions.length === 0 ? (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-8 text-sm text-amber-200 shadow-xl">
              <p className="font-semibold">No positions exist yet.</p>
              <p className="mt-2 text-amber-200/80">
                Every employee needs a position, and your organization doesn&apos;t have any yet. The
                Positions / Reporting Hierarchy editor isn&apos;t built in this app yet. For now, ask
                an admin to create at least one position directly on the backend before adding
                employees here.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
              {savedNotice ? (
                <div className="mb-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                  Added {savedNotice.name}. The form is ready for the next person.{" "}
                  <Link href={"/employees/" + savedNotice.id} className="font-medium underline hover:text-white">
                    View profile
                  </Link>
                </div>
              ) : null}
              {formError ? (
                <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {formError}
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-x-12 gap-y-6 md:grid-cols-2">
                <div>
                  <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-400">
                    Personal Information
                  </h2>

                  <div className="space-y-5">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        First Name
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Adaeze"
                        value={form.firstName}
                        onChange={function (e) {
                          updateField("firstName", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Last Name
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Okonkwo"
                        value={form.lastName}
                        onChange={function (e) {
                          updateField("lastName", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Work Email
                      </label>
                      <input
                        type="email"
                        placeholder="e.g. adaeze@zenith.com"
                        value={form.workEmail}
                        onChange={function (e) {
                          updateField("workEmail", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Phone Number
                      </label>
                      <input
                        type="tel"
                        placeholder="e.g. +234 801 234 5678"
                        value={form.phoneNumber}
                        onChange={function (e) {
                          updateField("phoneNumber", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Address
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. 12 Admiralty Way, Lekki, Lagos"
                        value={form.address}
                        onChange={function (e) {
                          updateField("address", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div className="rounded-lg border border-white/10 bg-[#0a0e1a] p-4">
                      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">Login Access</p>
                      <div className="space-y-3 text-sm">
                        <label className="flex items-start gap-2">
                          <input
                            type="radio"
                            name="loginMode"
                            checked={form.loginMode === "invite"}
                            onChange={function () {
                              updateField("loginMode", "invite");
                            }}
                            className="mt-0.5 h-4 w-4 accent-indigo-500"
                          />
                          <span>Send a login invite to their work email once saved.</span>
                        </label>
                        {form.loginMode === "invite" ? (
                          <select
                            value={form.role}
                            onChange={function (e) {
                              updateField("role", e.target.value);
                            }}
                            className="ml-6 w-[calc(100%-1.5rem)] rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500"
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
                        ) : null}

                        <label className="flex items-start gap-2">
                          <input
                            type="radio"
                            name="loginMode"
                            checked={form.loginMode === "link"}
                            onChange={function () {
                              updateField("loginMode", "link");
                            }}
                            className="mt-0.5 h-4 w-4 accent-indigo-500"
                          />
                          <span>Link to someone who already has a login (no employee record yet).</span>
                        </label>
                        {form.loginMode === "link" ? (
                          <select
                            value={form.linkedUserId}
                            onChange={function (e) {
                              updateField("linkedUserId", e.target.value);
                            }}
                            className="ml-6 w-[calc(100%-1.5rem)] rounded-lg border border-white/10 bg-[#0d1220] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500"
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
                        ) : null}
                        {form.loginMode === "link" && unlinkedMembers.length === 0 ? (
                          <p className="ml-6 text-xs text-gray-500">
                            Nobody in your organization is waiting to be linked right now.
                          </p>
                        ) : null}

                        <label className="flex items-start gap-2">
                          <input
                            type="radio"
                            name="loginMode"
                            checked={form.loginMode === "none"}
                            onChange={function () {
                              updateField("loginMode", "none");
                            }}
                            className="mt-0.5 h-4 w-4 accent-indigo-500"
                          />
                          <span>Just the HR record for now. I&apos;ll send login access later.</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-400">
                    Workplace Details
                  </h2>

                  <div className="space-y-5">
                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                          Position
                        </label>
                        <button
                          type="button"
                          onClick={function () { setPicker("position"); }}
                          className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
                        >
                          Choose on chart
                        </button>
                      </div>
                      <select
                        value={form.positionId}
                        onChange={function (e) {
                          updateField("positionId", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                      >
                        <option value="">Select position</option>
                        {positions.map(function (position) {
                          return (
                            <option key={position.id} value={position.id}>
                              {position.title}, {departmentNameFor(position)}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                          Reporting Manager
                        </label>
                        <button
                          type="button"
                          onClick={function () { setPicker("manager"); }}
                          className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
                        >
                          Choose on chart
                        </button>
                      </div>
                      <select
                        value={form.managerId}
                        onChange={function (e) {
                          updateField("managerId", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                      >
                        <option value="">No manager</option>
                        {managerChoices.map(function (employee) {
                          return (
                            <option key={employee.id} value={employee.id}>
                              {personLabel(employee, positions, departments)}
                            </option>
                          );
                        })}
                      </select>
                      {bossRoleIsEmpty && bossRole && form.managerId === "" ? (
                        <p className="mt-1.5 text-xs text-amber-300">
                          Nobody holds {bossRole.title} yet, the role above this one. Add that person first, or leave the
                          manager empty and set it later.
                        </p>
                      ) : null}
                      {suggestedManager && form.managerId === "" ? (
                        <p className="mt-1.5 text-xs text-gray-400">
                          Usually reports to {suggestedManager.name}, who holds the role above this one.{" "}
                          <button
                            type="button"
                            onClick={function () { updateField("managerId", suggestedManager.id); }}
                            className="font-medium text-indigo-400 hover:text-indigo-300"
                          >
                            Use {suggestedManager.name}
                          </button>
                        </p>
                      ) : null}
                    </div>

                    {picker !== null ? (
                      <OrgChartPicker
                        mode={picker}
                        title={picker === "position" ? "Where does this person sit?" : "Who does this person report to?"}
                        positions={positions}
                        employees={existingEmployees}
                        departments={departments}
                        selectedId={picker === "position" ? form.positionId : form.managerId}
                        newHire={
                          form.positionId
                            ? { positionId: form.positionId, name: (form.firstName + " " + form.lastName).trim() }
                            : null
                        }
                        onSelect={function (id) {
                          if (picker === "position") {
                            updateField("positionId", id);
                            setPicker(null);
                          } else {
                            updateField("managerId", id);
                            setPicker(null);
                          }
                        }}
                        onClose={function () { setPicker(null); }}
                      />
                    ) : null}

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Employment Type
                      </label>
                      <select
                        value={form.employmentType}
                        onChange={function (e) {
                          updateField("employmentType", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                      >
                        <option value="">Select type</option>
                        {EMPLOYMENT_TYPE_OPTIONS.map(function (opt) {
                          return (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Location
                      </label>
                      <select
                        value={form.locationId}
                        onChange={function (e) {
                          updateField("locationId", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                      >
                        <option value="">No location</option>
                        {locations.map(function (location) {
                          return (
                            <option key={location.id} value={location.id}>
                              {location.name}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Employee Code
                      </label>
                      <input
                        type="text"
                        placeholder="Optional internal code"
                        value={form.employeeCode}
                        onChange={function (e) {
                          updateField("employeeCode", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                        Start Date
                      </label>
                      <input
                        type="date"
                        value={form.startDate}
                        onChange={function (e) {
                          updateField("startDate", e.target.value);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-8 flex items-center justify-end gap-3 border-t border-white/10 pt-6">
                <button
                  type="button"
                  onClick={function () {
                    router.push("/employees/directory");
                  }}
                  className="rounded-lg border border-white/10 px-5 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={function () { saveEmployee("another"); }}
                  className="rounded-lg border border-indigo-400/60 px-5 py-2.5 text-sm font-semibold text-indigo-200 transition hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? "Saving…" : "Save and add another"}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? "Saving…" : "Save and finish"}
                </button>
              </div>
            </form>
          )}
        </main>
      </div>
    </div>
  );
}
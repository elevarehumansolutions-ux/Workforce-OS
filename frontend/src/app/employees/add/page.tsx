"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

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
      <div className="flex items-center gap-3 border-t border-white/10 px-6 pt-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500 text-xs font-semibold text-white">
          NA
        </div>
        <div>
          <p className="text-sm font-medium text-white">Ngozi Adeyemi</p>
          <p className="text-xs text-gray-500">Engineering Manager</p>
        </div>
      </div>
    </aside>
  );
}

interface AddEmployeeFormData {
  firstName: string;
  lastName: string;
  email: string;
  grantLogin: boolean;
  phone: string;
  dateOfBirth: string;
  gender: string;
  department: string;
  jobTitle: string;
  reportingManager: string;
  employmentType: string;
  location: string;
  startDate: string;
}

const INITIAL_FORM: AddEmployeeFormData = {
  firstName: "",
  lastName: "",
  email: "",
  grantLogin: true,
  phone: "",
  dateOfBirth: "",
  gender: "",
  department: "",
  jobTitle: "",
  reportingManager: "",
  employmentType: "",
  location: "",
  startDate: "",
};

export default function AddEmployeePage() {
  const router = useRouter();
  const [formData, setFormData] = useState<AddEmployeeFormData>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);

  function updateField(field: keyof AddEmployeeFormData, value: string | boolean) {
    setFormData(function (prev) {
      return { ...prev, [field]: value };
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      // TODO: wire to real POST /employees endpoint once the backend
      // exposes it — for now this just logs the payload and returns
      // to the directory so the flow can be reviewed end-to-end.
      console.log("New employee payload:", formData);
      router.push("/employees/directory");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Employees &gt; Add Employee</p>
            <h1 className="text-xl font-bold text-white">Add New Employee</h1>
          </div>
          <div className="flex items-center gap-4">
            <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">
                1
              </span>
            </button>
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">
              WOS MVP Ready
            </span>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <form onSubmit={handleSubmit} className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
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
                      value={formData.firstName}
                      onChange={(e) => updateField("firstName", e.target.value)}
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
                      value={formData.lastName}
                      onChange={(e) => updateField("lastName", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Email Address
                    </label>
                    <input
                      type="email"
                      placeholder="e.g. adaeze@zenith.com"
                      value={formData.email}
                      onChange={(e) => updateField("email", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                    <label className="mt-2 flex items-start gap-2 text-xs text-gray-400">
                      <input
                        type="checkbox"
                        checked={formData.grantLogin}
                        onChange={(e) => updateField("grantLogin", e.target.checked)}
                        className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500"
                      />
                      <span>
                        Grant this person login access — send them an invite to join Elevare.
                        <br />
                        <span className="text-gray-600">
                          An invite will be sent to {formData.email || "this address"} once this employee is saved.
                        </span>
                      </span>
                    </label>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Phone Number
                    </label>
                    <input
                      type="tel"
                      placeholder="e.g. +234 801 234 5678"
                      value={formData.phone}
                      onChange={(e) => updateField("phone", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Date of Birth
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Mar 15, 1992"
                      value={formData.dateOfBirth}
                      onChange={(e) => updateField("dateOfBirth", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Gender
                    </label>
                    <select
                      value={formData.gender}
                      onChange={(e) => updateField("gender", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                    >
                      <option value="">Select gender</option>
                      <option value="female">Female</option>
                      <option value="male">Male</option>
                      <option value="prefer_not_to_say">Prefer not to say</option>
                    </select>
                  </div>
                </div>
              </div>

              <div>
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-400">
                  Workplace Details
                </h2>

                <div className="space-y-5">
                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Department
                    </label>
                    <select
                      value={formData.department}
                      onChange={(e) => updateField("department", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                    >
                      <option value="">Select department</option>
                      <option value="engineering">Engineering</option>
                      <option value="sales">Sales</option>
                      <option value="hr">HR</option>
                      <option value="finance">Finance</option>
                      <option value="operations">Operations</option>
                      <option value="customer_success">Customer Success</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Job Title
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Senior Software Engineer"
                      value={formData.jobTitle}
                      onChange={(e) => updateField("jobTitle", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Reporting Manager
                    </label>
                    <select
                      value={formData.reportingManager}
                      onChange={(e) => updateField("reportingManager", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                    >
                      <option value="">Select manager</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Employment Type
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Full-time"
                      value={formData.employmentType}
                      onChange={(e) => updateField("employmentType", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Location
                    </label>
                    <select
                      value={formData.location}
                      onChange={(e) => updateField("location", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                    >
                      <option value="">Select office location</option>
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">
                      Start Date
                    </label>
                    <select
                      value={formData.startDate}
                      onChange={(e) => updateField("startDate", e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                    >
                      <option value="">Select date</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-8 flex items-center justify-end gap-3 border-t border-white/10 pt-6">
              <button
                type="button"
                onClick={() => router.push("/employees")}
                className="rounded-lg border border-white/10 px-5 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Saving…" : "Save Employee"}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}


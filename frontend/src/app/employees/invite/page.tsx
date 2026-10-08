"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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

interface InviteRow {
  id: string;
  email: string;
  role: string;
  department: string;
  manager: string;
}

const ROLES = ["Manager", "HR", "Employee"];
const DEPARTMENTS = ["Engineering", "Human Resources", "Finance", "Sales", "Operations", "Customer Success"];
const MANAGERS = ["Adewale O.", "Ngozi A.", "Femi A."];

let nextId = 4;

const INITIAL_INVITES: InviteRow[] = [
  { id: "1", email: "ngozi@zenith.com", role: "Manager", department: "Engineering", manager: "Adewale O." },
  { id: "2", email: "femi.alao@zenith.com", role: "HR", department: "Human Resources", manager: "Ngozi A." },
  { id: "3", email: "kemi.a@zenith.com", role: "Employee", department: "Finance", manager: "Femi A." },
];

export default function InviteEmployeePage() {
  const router = useRouter();
  const [invites, setInvites] = useState<InviteRow[]>(INITIAL_INVITES);
  const [formEmail, setFormEmail] = useState("");
  const [formRole, setFormRole] = useState("");
  const [formDepartment, setFormDepartment] = useState("");
  const [formManager, setFormManager] = useState("");

  function handleAdd() {
    if (!formEmail.trim()) return;
    const newInvite: InviteRow = {
      id: String(nextId),
      email: formEmail,
      role: formRole || "Employee",
      department: formDepartment || "Unassigned",
      manager: formManager || "Unassigned",
    };
    nextId = nextId + 1;
    setInvites(function (prev) {
      return [...prev, newInvite];
    });
    setFormEmail("");
    setFormRole("");
    setFormDepartment("");
    setFormManager("");
  }

  function handleRemove(id: string) {
    setInvites(function (prev) {
      return prev.filter(function (invite) {
        return invite.id !== id;
      });
    });
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Employees &gt; Invite Team</p>
            <h1 className="text-xl font-bold text-white">Invite Your Team</h1>
            <p className="text-sm text-gray-500">Bring in the people who&apos;ll help run your organization</p>
          </div>
          <button type="button" className="relative text-gray-400 hover:text-gray-200" aria-label="Notifications">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">1</span>
          </button>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="mx-auto max-w-4xl rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-xl">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1.2fr_1.4fr_1.2fr_auto] sm:items-end">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Email Address</label>
                <input
                  type="email"
                  placeholder="e.g. ngozi@zenith.com"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Role</label>
                <select
                  value={formRole}
                  onChange={(e) => setFormRole(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                >
                  <option value="">Select role</option>
                  {ROLES.map(function (role) {
                    return <option key={role} value={role}>{role}</option>;
                  })}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Department</label>
                <select
                  value={formDepartment}
                  onChange={(e) => setFormDepartment(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                >
                  <option value="">Select department</option>
                  {DEPARTMENTS.map(function (dept) {
                    return <option key={dept} value={dept}>{dept}</option>;
                  })}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500">Reporting Manager</label>
                <select
                  value={formManager}
                  onChange={(e) => setFormManager(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2.5 text-sm text-gray-300 outline-none focus:border-indigo-500"
                >
                  <option value="">Select manager</option>
                  {MANAGERS.map(function (manager) {
                    return <option key={manager} value={manager}>{manager}</option>;
                  })}
                </select>
              </div>
              <button
                type="button"
                onClick={handleAdd}
                className="rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600"
              >
                + Add
              </button>
            </div>

            <button
              type="button"
              onClick={handleAdd}
              className="mt-3 text-sm font-medium text-indigo-400 hover:text-indigo-300"
            >
              + Add Another
            </button>

            <div className="mt-6 border-t border-white/10 pt-6">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">{invites.length} invites added</h3>
                <p className="text-xs text-gray-500">Review before sending</p>
              </div>

              <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <tbody className="divide-y divide-white/5">
                    {invites.map(function (invite) {
                      return (
                        <tr key={invite.id}>
                          <td className="px-4 py-3 text-white">{invite.email}</td>
                          <td className="px-4 py-3 text-gray-300">{invite.role}</td>
                          <td className="px-4 py-3 text-gray-300">{invite.department}</td>
                          <td className="px-4 py-3 text-gray-300">{invite.manager}</td>
                          <td className="px-4 py-3">
                            <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300">
                              Invite Pending
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleRemove(invite.id)}
                              aria-label="Remove invite"
                              className="text-red-400 hover:text-red-300"
                            >
                              &#128465;
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-between border-t border-white/10 pt-6">
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                className="text-sm font-medium text-gray-400 hover:text-gray-200"
              >
                Skip for now
              </button>
              <button
                type="button"
                onClick={() => console.log("Sending invites:", invites)}
                className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-600"
              >
                Send Invites &amp; Continue &rarr;
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

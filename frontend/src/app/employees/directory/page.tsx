"use client";

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

interface Employee {
  id: string;
  initials: string;
  name: string;
  email: string;
  department: string;
  jobTitle: string;
  status: "Active" | "On Leave" | "Inactive";
  joinDate: string;
}

const EMPLOYEES: Employee[] = [
  { id: "1", initials: "AO", name: "Adaeze Okonkwo", email: "adaeze@zenith.com", department: "Engineering", jobTitle: "Senior Software Engineer", status: "Active", joinDate: "Mar 2024" },
  { id: "2", initials: "TB", name: "Tunde Balogun", email: "tunde@zenith.com", department: "Sales", jobTitle: "Account Manager", status: "Active", joinDate: "Jan 2025" },
  { id: "3", initials: "FA", name: "Fatima Abubakar", email: "fatima@zenith.com", department: "HR", jobTitle: "HR Coordinator", status: "On Leave", joinDate: "Jun 2023" },
  { id: "4", initials: "EN", name: "Emeka Nwankwo", email: "emeka@zenith.com", department: "Engineering", jobTitle: "DevOps Engineer", status: "Active", joinDate: "Sep 2024" },
  { id: "5", initials: "KA", name: "Kemi Adebayo", email: "kemi@zenith.com", department: "Finance", jobTitle: "Financial Analyst", status: "Active", joinDate: "Nov 2023" },
  { id: "6", initials: "YI", name: "Yusuf Ibrahim", email: "yusuf@zenith.com", department: "Operations", jobTitle: "Operations Lead", status: "Inactive", joinDate: "Feb 2024" },
  { id: "7", initials: "OC", name: "Obioma Chukwu", email: "obioma@zenith.com", department: "Engineering", jobTitle: "QA Engineer", status: "Active", joinDate: "Jul 2025" },
  { id: "8", initials: "AE", name: "Amara Eze", email: "amara@zenith.com", department: "Customer Success", jobTitle: "Support Lead", status: "Active", joinDate: "Aug 2024" },
];

function StatusBadge(status: Employee["status"]) {
  let badgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (status === "Active") {
    badgeClass = badgeClass + "bg-emerald-500/15 text-emerald-300";
  } else if (status === "On Leave") {
    badgeClass = badgeClass + "bg-cyan-500/15 text-cyan-300";
  } else {
    badgeClass = badgeClass + "bg-white/10 text-gray-400";
  }
  return <span className={badgeClass}>{status}</span>;
}

export default function EmployeeDirectoryPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Dashboard &gt; Employees</p>
            <h1 className="text-xl font-bold text-white">Employees</h1>
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
                  placeholder="Search employees..."
                  className="w-64 rounded-lg border border-white/10 bg-[#0a0e1a] py-2 pl-9 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
              </div>
              <select className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500">
                <option>Department: All</option>
              </select>
              <select className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500">
                <option>Status: All</option>
              </select>
              <select className="rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-300 outline-none focus:border-indigo-500">
                <option>Location: All</option>
              </select>
            </div>
            <button
              type="button"
              onClick={() => router.push("/employees/add")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              + Add Employee
            </button>
          </div>

          <div className="mt-6 overflow-hidden rounded-2xl border border-white/10 bg-[#0d1220]/80 shadow-xl">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-6 py-3 font-medium">
                    <input type="checkbox" className="h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500" />
                  </th>
                  <th className="px-6 py-3 font-medium">Employee</th>
                  <th className="px-6 py-3 font-medium">Department</th>
                  <th className="px-6 py-3 font-medium">Job Title</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Join Date</th>
                  <th className="px-6 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {EMPLOYEES.map(function (employee) {
                  return (
                    <tr
                      key={employee.id}
                      className="cursor-pointer transition hover:bg-white/5"
                      onClick={() => router.push("/employees/" + employee.id)}
                    >
                      <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" className="h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500" />
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/20 text-xs font-semibold text-indigo-300">
                            {employee.initials}
                          </div>
                          <div>
                            <p className="font-medium text-white">{employee.name}</p>
                            <p className="text-xs text-gray-500">{employee.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-300">{employee.department}</td>
                      <td className="px-6 py-4 text-gray-300">{employee.jobTitle}</td>
                      <td className="px-6 py-4">{StatusBadge(employee.status)}</td>
                      <td className="px-6 py-4 text-gray-300">{employee.joinDate}</td>
                      <td className="px-6 py-4 text-gray-500">
                        <button type="button" onClick={(e) => e.stopPropagation()} aria-label="Row actions">
                          &#8942;
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
            <p>Showing 1-8 of 284 employees</p>
            <div className="flex items-center gap-2">
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">
                Previous
              </button>
              <button type="button" className="rounded-lg bg-indigo-500 px-3 py-1.5 font-medium text-white">
                1
              </button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">
                2
              </button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">
                3
              </button>
              <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-gray-400 hover:bg-white/5">
                Next
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}


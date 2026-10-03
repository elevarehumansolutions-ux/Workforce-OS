"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";

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

interface EmployeeDetail {
  id: string;
  initials: string;
  fullName: string;
  jobTitle: string;
  department: string;
  status: "Active" | "On Leave" | "Inactive";
  email: string;
  phone: string;
  employeeId: string;
  dateOfBirth: string;
  gender: string;
  address: string;
  emergencyContact: string;
  employmentType: string;
  manager: string;
  location: string;
  startDate: string;
}

const EMPLOYEE_DETAILS: Record<string, EmployeeDetail> = {
  "1": {
    id: "1",
    initials: "AO",
    fullName: "Adaeze Okonkwo",
    jobTitle: "Senior Software Engineer",
    department: "Engineering",
    status: "Active",
    email: "adaeze@zenith.com",
    phone: "+234 801 234 5678",
    employeeId: "EMP-001",
    dateOfBirth: "Mar 15, 1992",
    gender: "Female",
    address: "12 Admiralty Way, Lekki, Lagos",
    emergencyContact: "Chinedu Okonkwo - +234 802 345 6789",
    employmentType: "Full-time",
    manager: "Ngozi Adeyemi",
    location: "HQ - Lagos",
    startDate: "Mar 12, 2024",
  },
};

const DEFAULT_DETAIL: EmployeeDetail = EMPLOYEE_DETAILS["1"];

const TABS = ["Overview", "Attendance", "Schedule", "Leave", "KPIs"];

export default function EmployeeDetailsPage() {
  const router = useRouter();
  const params = useParams();
  const idParam = typeof params.id === "string" ? params.id : "1";
  const employee = EMPLOYEE_DETAILS[idParam] || { ...DEFAULT_DETAIL, id: idParam };

  const [activeTab, setActiveTab] = useState("Overview");

  let statusBadgeClass = "rounded-full px-2.5 py-1 text-xs font-medium ";
  if (employee.status === "Active") {
    statusBadgeClass = statusBadgeClass + "bg-emerald-500/15 text-emerald-300";
  } else if (employee.status === "On Leave") {
    statusBadgeClass = statusBadgeClass + "bg-cyan-500/15 text-cyan-300";
  } else {
    statusBadgeClass = statusBadgeClass + "bg-white/10 text-gray-400";
  }

  return (
    <div className="flex min-h-screen w-full bg-[#05070f] text-white">
      {SidebarShell("Employees")}

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 px-8 py-5">
          <div>
            <p className="text-xs text-gray-500">Employees &gt; {employee.fullName}</p>
            <h1 className="text-xl font-bold text-white">{employee.fullName}</h1>
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
            <button
              type="button"
              onClick={() => router.push("/employees/directory")}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Edit Employee
            </button>
          </div>
        </div>

        <main className="flex-1 px-8 py-8">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
            <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
              <div className="flex flex-col items-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-indigo-500 text-lg font-bold text-white">
                  {employee.initials}
                </div>
                <h2 className="mt-4 text-base font-semibold text-white">{employee.fullName}</h2>
                <p className="text-sm text-gray-400">{employee.jobTitle}</p>
                <p className="mt-1 text-sm font-medium text-indigo-300">{employee.department}</p>
                <span className={statusBadgeClass + " mt-2"}>{employee.status}</span>
              </div>

              <div className="mt-6 flex flex-col gap-3 border-t border-white/10 pt-4 text-sm text-gray-300">
                <div className="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="m3 7 9 6 9-6" />
                  </svg>
                  <span>{employee.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92Z" />
                  </svg>
                  <span>{employee.phone}</span>
                </div>
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
                    <button key={tab} type="button" onClick={() => setActiveTab(tab)} className={tabClass}>
                      {tab}
                    </button>
                  );
                })}
              </div>

              {activeTab === "Overview" ? (
                <div className="mt-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 shadow-xl">
                  <h3 className="mb-4 text-base font-semibold text-white">Personal &amp; Professional Details</h3>
                  <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Full Name</p>
                      <p className="mt-1 text-sm text-white">{employee.fullName}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Employee ID</p>
                      <p className="mt-1 text-sm text-white">{employee.employeeId}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Date of Birth</p>
                      <p className="mt-1 text-sm text-white">{employee.dateOfBirth}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Gender</p>
                      <p className="mt-1 text-sm text-white">{employee.gender}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Address</p>
                      <p className="mt-1 text-sm text-white">{employee.address}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Emergency Contact</p>
                      <p className="mt-1 text-sm text-white">{employee.emergencyContact}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Employment Type</p>
                      <p className="mt-1 text-sm text-white">{employee.employmentType}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Manager</p>
                      <p className="mt-1 text-sm text-white">{employee.manager}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Location</p>
                      <p className="mt-1 text-sm text-white">{employee.location}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-gray-500">Start Date</p>
                      <p className="mt-1 text-sm text-white">{employee.startDate}</p>
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


// What each role sees in the sidebar. The backend still enforces the real
// permissions on every call; this only stops people being shown links to
// screens they cannot use.

export interface SidebarItem {
  label: string;
  href: string;
  // Roles that see this item. A "soon" item has no backend yet (Phase 2).
  roles: string[];
  soon?: boolean;
}

const EVERYONE = ["hr_administrator", "business_executive", "manager", "employee"];
const LEADERS = ["hr_administrator", "business_executive", "manager"];
const HR_AND_EXECUTIVES = ["hr_administrator", "business_executive"];

export const SIDEBAR_ITEMS: SidebarItem[] = [
  { label: "Dashboard", href: "/dashboard", roles: EVERYONE },
  { label: "Employees", href: "/employees", roles: LEADERS },
  { label: "Team Management", href: "/team-management", roles: ["hr_administrator"] },
  { label: "Organization Structure", href: "/organization-structure", roles: LEADERS },
  { label: "Attendance", href: "/attendance", roles: EVERYONE },
  { label: "Workflow", href: "/workflow/templates", roles: EVERYONE },
  { label: "Tasks", href: "/tasks", roles: EVERYONE },
  { label: "Performance", href: "/performance", roles: EVERYONE },
  { label: "KPIs", href: "/performance/kpis", roles: EVERYONE },
  { label: "Strategy", href: "/strategy-performance", roles: EVERYONE },
  { label: "Leave Management", href: "/leave", roles: HR_AND_EXECUTIVES, soon: true },
  { label: "Payroll", href: "/payroll", roles: HR_AND_EXECUTIVES, soon: true },
  { label: "Reports", href: "/reports", roles: HR_AND_EXECUTIVES, soon: true },
  { label: "Settings", href: "/settings", roles: EVERYONE },
];

// Until we know the role (the first moment of a page load) the role is "",
// and we treat that as an employee: the smallest menu, so nobody flashes a
// menu they should not see.
export function itemsForRole(role: string): SidebarItem[] {
  let who = role;
  if (who === "") {
    who = "employee";
  }
  const out: SidebarItem[] = [];
  for (const item of SIDEBAR_ITEMS) {
    if (item.roles.indexOf(who) !== -1) {
      out.push(item);
    }
  }
  return out;
}

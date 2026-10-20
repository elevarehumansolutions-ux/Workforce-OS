import { apiFetch } from "@/lib/api";

export interface MeOrganization {
  id: string;
  name: string | null;
  subscription_status: string;
  subscription_expires_at: string | null;
  fiscal_year_start_month: number;
  created_at: string;
}

export interface MeData {
  userId: string;
  fullName: string;
  email: string;
  accountStatus: string;
  lastLoginAt: string | null;
  role: string;
  organization: MeOrganization | null;
}

interface MeResponse {
  user: {
    id: string;
    email: string;
    full_name: string;
    account_status: string;
    last_login_at: string | null;
  };
  memberships: { role: string; deactivated_at: string | null; organization: MeOrganization }[];
}

export async function loadMe(): Promise<MeData> {
  const res = await apiFetch<MeResponse>("/auth/me", { method: "GET" });
  let role = "";
  let organization: MeOrganization | null = null;
  // The first active membership is used until an organization switcher exists.
  for (const m of res.memberships) {
    if (!m.deactivated_at) {
      role = m.role;
      organization = m.organization;
      break;
    }
  }
  return {
    userId: res.user.id,
    fullName: res.user.full_name,
    email: res.user.email,
    accountStatus: res.user.account_status,
    lastLoginAt: res.user.last_login_at,
    role: role,
    organization: organization,
  };
}

export const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function monthName(month: number): string {
  return MONTH_NAMES[month - 1] || String(month);
}

export function subscriptionLabel(status: string): string {
  if (status === "trial") return "Trial";
  if (status === "active") return "Active";
  if (status === "expired") return "Expired";
  if (status === "cancelled") return "Cancelled";
  return status;
}

export function subscriptionClasses(status: string): string {
  if (status === "active") return "bg-emerald-500/15 text-emerald-400";
  if (status === "trial") return "bg-indigo-500/15 text-indigo-300";
  if (status === "expired") return "bg-amber-500/15 text-amber-300";
  return "bg-gray-500/20 text-gray-400";
}

export function isHrRole(role: string): boolean {
  return role === "hr_administrator";
}

export function canReadAuditLog(role: string): boolean {
  return role === "hr_administrator" || role === "business_executive";
}

export function titleCase(text: string): string {
  const spaced = text.replace(/_/g, " ").trim();
  if (!spaced) return text;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export const SETTINGS_INPUT_CLASS =
  "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-2.5 text-sm text-white outline-none focus:border-indigo-500 disabled:opacity-60";
export const SETTINGS_LABEL_CLASS = "mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-500";

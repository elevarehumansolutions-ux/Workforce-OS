import { fetchAllPages } from "@/lib/tasks";

// The little we need to know about the old head; every page's own Employee type has these.
interface PersonWithLogin {
  first_name: string;
  last_name: string;
  user_id?: string | null;
}

// The access levels HR can give, from lowest to highest.
export const ACCESS_LEVELS = ["employee", "manager", "business_executive", "hr_administrator"];

// The person who was head of a department before someone else replaced them.
export interface FormerHead {
  name: string;
  department: string;
  membershipId: string;
  role: string;
}

interface MembershipRow {
  id: string;
  role: string;
  user: { id: string };
}

// Call this AFTER the head was changed, with the old head you read BEFORE the change.
// Returns null when there is nothing to ask HR about: no old head, no login (so no access level),
// or the caller may not read the team list (only HR can).
export async function findFormerHead(oldHead: PersonWithLogin | undefined, departmentName: string): Promise<FormerHead | null> {
  if (!oldHead || !oldHead.user_id) return null;
  try {
    const rows = await fetchAllPages<MembershipRow>("/memberships");
    for (const row of rows) {
      if (row.user.id === oldHead.user_id) {
        return { name: (oldHead.first_name + " " + oldHead.last_name).trim(), department: departmentName, membershipId: row.id, role: row.role };
      }
    }
  } catch {
    // Not HR, or the list could not load: skip the question rather than block the head change.
  }
  return null;
}

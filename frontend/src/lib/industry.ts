export const OTHER_INDUSTRY = "Other";

export const INDUSTRY_OPTIONS = [
  "Information Technology",
  "Financial Services",
  "Consulting Services",
  "Manufacturing",
  "Healthcare",
  "Retail & E-commerce",
  "Agriculture",
  "Logistics & Transportation",
  OTHER_INDUSTRY,
];

// A saved industry that isn't in the list was typed in by the company, so it
// shows as "Other" with that text filled in.
export function splitIndustry(saved: string | null | undefined): { choice: string; custom: string } {
  if (!saved) return { choice: INDUSTRY_OPTIONS[0], custom: "" };
  if (INDUSTRY_OPTIONS.indexOf(saved) !== -1 && saved !== OTHER_INDUSTRY) return { choice: saved, custom: "" };
  return { choice: OTHER_INDUSTRY, custom: saved === OTHER_INDUSTRY ? "" : saved };
}

// The value that gets saved: the chosen industry, or the typed one for "Other".
export function resolveIndustry(choice: string, custom: string): string {
  return choice === OTHER_INDUSTRY ? custom.trim() : choice;
}

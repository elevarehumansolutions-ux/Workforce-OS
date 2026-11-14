import { apiFetch } from "@/lib/api";

// The month the company's financial year starts in, 1 (January) to 12 (December).
// It decides where quarters begin: with April, the quarters are Apr to Jun, Jul to Sep, and so on.
// The current value comes from GET /auth/me (organization.fiscal_year_start_month).
export function saveFiscalYear(month: number): Promise<{ fiscal_year_start_month: number }> {
  return apiFetch<{ fiscal_year_start_month: number }>("/fiscal-year", {
    method: "PUT",
    body: { fiscal_year_start_month: month },
  });
}

// Shown wherever the month can be changed, so the person knows what a change does.
export const FISCAL_YEAR_WARNING =
  "Quarter-end reviews, KPI periods and scores follow this. Quarters already closed keep their dates; " +
  "the quarter in progress and later ones move to the new month.";

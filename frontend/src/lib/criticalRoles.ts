// Shared bits for the Critical Roles screens. The option values are exactly
// what the backend accepts (CriticalityType / RiskLevel enums).

export const CRITICALITY_OPTIONS: { value: string; label: string }[] = [
  { value: "revenue_generating", label: "Revenue generating" },
  { value: "revenue_enabling", label: "Revenue enabling" },
  { value: "operational", label: "Operational" },
  { value: "customer", label: "Customer" },
  { value: "compliance", label: "Compliance" },
  { value: "strategic", label: "Strategic" },
  { value: "financial", label: "Financial" },
  { value: "legal", label: "Legal" },
  { value: "reputational", label: "Reputational" },
];

export const RISK_OPTIONS: { value: string; label: string }[] = [
  { value: "very_low", label: "Very low" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "very_high", label: "Very high" },
];

export function optionLabel(options: { value: string; label: string }[], value: string | null): string {
  if (!value) return "Not set";
  for (const o of options) {
    if (o.value === value) return o.label;
  }
  return value;
}

export function riskClasses(risk: string | null): string {
  if (risk === "high" || risk === "very_high") return "bg-red-500/15 text-red-300";
  if (risk === "medium") return "bg-amber-500/15 text-amber-300";
  if (risk === "low" || risk === "very_low") return "bg-emerald-500/15 text-emerald-300";
  return "bg-gray-500/20 text-gray-400";
}

export function isHighRisk(risk: string | null): boolean {
  return risk === "high" || risk === "very_high";
}

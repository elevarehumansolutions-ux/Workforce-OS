import { apiFetch } from "@/lib/api";

// The "blueprint" is what the OS proposes for a company right after its first
// Business DNA save: departments, positions (with who each reports to), objectives
// with key results, and clean-ups of what the company already has. Nothing is real
// until HR approves it. Backend: docs/05_API_DESIGN.md "Blueprint".

export type BlueprintKind =
  | "department"
  | "position"
  | "objective"
  | "key_result"
  | "kpi"
  | "rename_department"
  | "rename_position"
  | "review_note"
  // A department or role the plan leaves out because another one covers its work.
  | "folded";

export type BlueprintStatus = "pending" | "approved" | "edited" | "rejected";

export interface BlueprintItem {
  id: string;
  batch_id: string;
  kind: BlueprintKind;
  // The short key other items of the same batch use to point at this one ("D1", "P3").
  ref: string | null;
  sort_order: number;
  // Department name, position title, objective title or key result text. For a
  // rename it is the NEW name; for a note it is the heading.
  title: string;
  rationale: string;
  // A parent is EITHER an id (it already exists as a real row) OR a ref (it is
  // another proposed item). Both empty means "none": top of the chart for a
  // position's boss, company-wide for an objective.
  department_id: string | null;
  position_id: string | null;
  reports_to_position_id: string | null;
  department_ref: string | null;
  reports_to_ref: string | null;
  objective_ref: string | null;
  // Only for a "folded" note: the ref of the proposed department or position that covers it.
  // When the one that covers it already exists, department_id / position_id is set instead.
  folded_into_ref: string | null;
  // Only for a KPI: the key result it measures (a ref, or null for none), its share of
  // the department's KPIs in percent, its target and unit, and whether a LOWER figure
  // is better (for example days to deliver). The API sends decimals as strings.
  key_result_ref: string | null;
  // Decided by the OS, not asked of the user. A department: critical or not, and its
  // share of the capital investment in percent (an independent expected-return target:
  // different departments' shares may add up to more than 100). A position: critical,
  // with the kind of criticality and its risk level.
  is_critical: boolean | null;
  revenue_allocation_pct: string | number | null;
  // A department's estimated profit margin in percent (an estimate that HR can change).
  profit_margin_pct: string | number | null;
  criticality_type: string | null;
  risk_level: string | null;
  kpi_weight: string | number | null;
  kpi_target_value: string | number | null;
  kpi_unit: string | null;
  kpi_is_inverse: boolean | null;
  status: BlueprintStatus;
  reviewed_title: string | null;
  created_entity_id: string | null;
  reviewed_at: string | null;
  created_at: string;
}

// A department or position the company already has (from GET /departments, /positions).
export interface ExistingDepartment {
  id: string;
  name: string;
}

export interface ExistingPosition {
  id: string;
  title: string;
  department_id: string;
  reports_to_position_id: string | null;
}

interface PaginatedBlueprint {
  data: BlueprintItem[];
}

export interface AcceptAllResult {
  accepted: number;
  skipped: { id: string; title: string; reason: string }[];
}

// A whole blueprint is at most about 95 items, so one page of 100 holds it.
// The newest batch comes first; older batches (from an earlier "generate again")
// follow, so keep only the newest.
export async function fetchLatestBlueprint(): Promise<BlueprintItem[]> {
  const res = await apiFetch<PaginatedBlueprint>("/blueprint?limit=100", { method: "GET" });
  if (res.data.length === 0) return [];
  const newestBatch = res.data[0].batch_id;
  return res.data.filter(function (item) {
    return item.batch_id === newestBatch;
  });
}

export function approveBlueprintItem(id: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/approve", { method: "POST" });
}

// Details that can be corrected before an item is added, beside its wording. A KPI: target,
// unit, direction (null clears the target or unit). A department: its share of the capital
// (the others are re-spread to keep the total at 100) and its estimated profit margin.
export interface EditDetails {
  kpi_target_value?: string | null;
  kpi_unit?: string | null;
  kpi_is_inverse?: boolean;
  revenue_allocation_pct?: string;
  profit_margin_pct?: string | null;
}

export function editBlueprintItem(id: string, title: string, details?: EditDetails): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/edit", {
    method: "POST",
    body: { title: title, ...(details || {}) },
  });
}

export function rejectBlueprintItem(id: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/reject", { method: "POST" });
}

// A left-out department or role comes back as its own pending item.
export function addBlueprintItemSeparately(id: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/add-separately", { method: "POST" });
}

// Merge a suggested department (or role) into another suggested one of the same kind. The
// first stops being its own and becomes a "left out" note covered by the target.
export function mergeBlueprintItem(id: string, targetId: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/merge", {
    method: "POST",
    body: { target_id: targetId },
  });
}

export function acceptAllBlueprint(): Promise<AcceptAllResult> {
  return apiFetch<AcceptAllResult>("/blueprint/accept-all", { method: "POST" });
}

// "queued" = started in the background; "already_pending" = items still wait for review.
export function generateBlueprint(): Promise<{ status: "queued" | "already_pending" }> {
  return apiFetch<{ status: "queued" | "already_pending" }>("/blueprint/generate", { method: "POST" });
}

export function isPending(item: BlueprintItem): boolean {
  return item.status === "pending";
}

// What the user sees for an item that has been decided. An edited item shows HR's
// own wording, an approved one the OS's.
export function shownTitle(item: BlueprintItem): string {
  if ((item.status === "edited" || item.status === "approved") && item.reviewed_title) {
    return item.reviewed_title;
  }
  return item.title;
}

// ---------------------------------------------------------------------------
// What the screen draws
// ---------------------------------------------------------------------------

export interface ObjectiveGroup {
  objective: BlueprintItem;
  keyResults: BlueprintItem[];
}

// One department, proposed (has an item to approve) or already there (item is null).
export interface DepartmentCard {
  key: string;
  name: string;
  color: string;
  item: BlueprintItem | null;
  isCritical: boolean;
  // Its share of the capital in percent, or null when it has none. The capital is split
  // between the departments that have not been skipped, so these add up to 100.
  sharePct: number | null;
  // Share x capital: the revenue this department is expected to bring in a year (its
  // revenue target). Null when there is no share or no capital amount was entered.
  annualReturn: number | null;
  // Estimated profit margin in percent, and revenue target x margin.
  marginPct: number | null;
  annualProfit: number | null;
  // Its roles, top first, each with how far down its own department's chart it sits.
  roles: DepartmentRole[];
}

export interface DepartmentRole {
  node: ChartNode;
  depth: number;
}

// One box of the department-level chart: a department with its money, joined to the
// department it reports into (the department of its top role's boss).
export interface DepartmentChartNode {
  key: string;
  virtual: boolean;
  card: DepartmentCard | null;
  children: DepartmentChartNode[];
}

// One box in the organization chart: a proposed position (item set) or one the
// company already has (item null). The very top box may be a made-up "Company"
// box that only joins several tops together (virtual).
export interface ChartNode {
  key: string;
  item: BlueprintItem | null;
  virtual: boolean;
  title: string;
  departmentName: string;
  // "ref:D1" or "id:<uuid>" for the department it belongs to, "" when unknown.
  departmentKey: string;
  color: string;
  // Decided in the plan, not asked of the user. For a critical role: what kind and how risky, in words.
  isCritical: boolean;
  criticalLabel: string | null;
  children: ChartNode[];
}

export interface ObjectiveSection {
  title: string;
  color: string | null;
  objectives: ObjectiveGroup[];
}

export interface KpiSection {
  title: string;
  color: string;
  kpis: BlueprintItem[];
  // The department's yearly return target; each KPI's own return is its weight's share of it.
  departmentAnnualReturn: number | null;
}

// One department or role the plan leaves out because another one covers it.
export interface FoldedNote {
  item: BlueprintItem;
  // Is the thing left out a department or a position? It is the same kind as what covers it.
  what: "department" | "position";
  // The name of the department or position that covers it ("" if it could not be found).
  coveredBy: string;
}

// How lean the plan is: what it keeps, and what the full structure would have had.
export interface LeanCounts {
  departments: number;
  roles: number;
  fullDepartments: number;
  fullRoles: number;
}

export interface BlueprintView {
  // The capital investment from the Business DNA, or null when none was entered.
  capital: number | null;
  // Sum of the departments' shares. Can be above 100: the shares are independent targets.
  totalSharePct: number;
  departments: DepartmentCard[];
  // The chart of departments (with their money), and the chart of roles.
  departmentChart: DepartmentChartNode | null;
  chart: ChartNode | null;
  objectiveSections: ObjectiveSection[];
  kpiSections: KpiSection[];
  cleanups: BlueprintItem[];
  folded: FoldedNote[];
  lean: LeanCounts;
}

// "95.00" -> "95", "2.50" -> "2.5". The API sends decimals as strings.
export function trimNumber(value: string | number): string {
  return String(Number(value));
}

// Money is in naira: the Business DNA has no currency field (docs/04_DATABASE.md).
export function formatMoney(amount: number): string {
  return "₦" + Math.round(amount).toLocaleString("en-NG");
}

// Capital x share: what a department is expected to return in a year.
export function annualReturn(capital: number | null, sharePct: number | null): number | null {
  if (capital === null || sharePct === null) return null;
  return (capital * sharePct) / 100;
}

// A KPI's own expected return: its weight's share of its department's yearly return,
// so a department's KPIs add up to the department's total.
export function kpiAnnualReturn(departmentReturn: number | null, weight: string | number | null): number | null {
  if (departmentReturn === null || weight === null) return null;
  return (departmentReturn * Number(weight)) / 100;
}

const CRITICALITY_LABELS: Record<string, string> = {
  revenue_generating: "Brings in revenue",
  revenue_enabling: "Enables revenue",
  operational: "Keeps operations running",
  customer: "Customer critical",
  compliance: "Compliance critical",
  strategic: "Strategically important",
  financial: "Financially critical",
  legal: "Legally critical",
};

const RISK_LABELS: Record<string, string> = {
  very_low: "very low risk",
  low: "low risk",
  medium: "medium risk",
  high: "high risk",
  very_high: "very high risk",
};

// For a critical role: "Keeps operations running · high risk if unfilled".
function criticalLabelOf(item: BlueprintItem): string | null {
  if (!item.is_critical) return null;
  const kind = item.criticality_type ? CRITICALITY_LABELS[item.criticality_type] || item.criticality_type : "Critical role";
  const risk = item.risk_level ? RISK_LABELS[item.risk_level] || item.risk_level : "";
  return risk ? kind + " · " + risk + " if unfilled" : kind;
}

// Plain words for the direction of a KPI (the database calls it "inverse").
export function directionText(item: BlueprintItem): string {
  return item.kpi_is_inverse
    ? "A lower result is better (for example fewer days, fewer complaints)"
    : "A higher result is better";
}

// Colours that tell departments apart in the chart. Used in order.
const DEPARTMENT_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4", "#8b5cf6", "#ef4444", "#84cc16"];
const NEUTRAL_COLOR = "#6b7280";

function departmentKeyOf(item: BlueprintItem): string {
  if (item.department_ref) return "ref:" + item.department_ref;
  if (item.department_id) return "id:" + item.department_id;
  return "";
}

export function buildBlueprintView(
  items: BlueprintItem[],
  existingDepartments: ExistingDepartment[],
  existingPositions: ExistingPosition[],
  capital: number | null
): BlueprintView {
  const departmentItems = items.filter(function (i) { return i.kind === "department"; });
  const positionItems = items.filter(function (i) { return i.kind === "position" && i.status !== "rejected"; });
  const objectiveItems = items.filter(function (i) { return i.kind === "objective"; });
  const keyResultItems = items.filter(function (i) { return i.kind === "key_result"; });
  const kpiItems = items.filter(function (i) { return i.kind === "kpi"; });
  const cleanups = items.filter(function (i) {
    return i.kind === "rename_department" || i.kind === "rename_position" || i.kind === "review_note";
  });

  const existingDepartmentName: Record<string, string> = {};
  existingDepartments.forEach(function (d) { existingDepartmentName[d.id] = d.name; });

  // --- departments and their colours --------------------------------------
  const departments: DepartmentCard[] = [];
  const colorOf: Record<string, string> = {};
  const nameOf: Record<string, string> = {};

  // The capital is SPLIT between the departments that have not been skipped, so their
  // shares are scaled to add up to 100. The server does exactly the same when HR approves
  // or skips a department, so what is shown here is what gets saved.
  let rawShareTotal = 0;
  departmentItems.forEach(function (d) {
    if (d.status !== "rejected" && d.revenue_allocation_pct !== null) rawShareTotal += Number(d.revenue_allocation_pct);
  });
  function effectiveShare(item: BlueprintItem | null): number | null {
    if (!item || item.status === "rejected" || item.revenue_allocation_pct === null || rawShareTotal <= 0) return null;
    return Math.round((Number(item.revenue_allocation_pct) / rawShareTotal) * 10000) / 100;
  }

  function addDepartment(key: string, name: string, item: BlueprintItem | null) {
    if (colorOf[key]) return;
    colorOf[key] = DEPARTMENT_COLORS[departments.length % DEPARTMENT_COLORS.length];
    nameOf[key] = name;
    const sharePct = effectiveShare(item);
    const revenue = annualReturn(capital, sharePct);
    const marginText = item ? item.profit_margin_pct : null;
    const marginPct = marginText === null || marginText === undefined ? null : Number(marginText);
    const card: DepartmentCard = {
      key: key,
      name: name,
      color: colorOf[key],
      item: item,
      isCritical: item ? item.is_critical === true : false,
      sharePct: sharePct,
      annualReturn: revenue,
      marginPct: marginPct,
      annualProfit: revenue !== null && marginPct !== null ? (revenue * marginPct) / 100 : null,
      roles: [],
    };
    departments.push(card);
  }

  departmentItems.forEach(function (d) {
    addDepartment("ref:" + d.ref, shownTitle(d), d);
  });
  // Existing departments that something on screen belongs to, plus the ones the
  // company's own positions sit in.
  function addExistingDepartmentOf(id: string | null) {
    if (id && existingDepartmentName[id]) addDepartment("id:" + id, existingDepartmentName[id], null);
  }
  positionItems.concat(objectiveItems, kpiItems).forEach(function (i) { addExistingDepartmentOf(i.department_id); });

  // --- the chart ------------------------------------------------------------
  // A real position that a proposed item became (after approval) is drawn once,
  // as the item, not again as an "existing" position.
  const itemOfRealId: Record<string, BlueprintItem> = {};
  items.forEach(function (i) {
    if (i.created_entity_id) itemOfRealId[i.created_entity_id] = i;
  });

  const nodes: Record<string, ChartNode> = {};
  const bossKey: Record<string, string | null> = {};

  function keyOfRealPosition(id: string | null): string | null {
    if (!id) return null;
    const viaItem = itemOfRealId[id];
    if (viaItem) return viaItem.status === "rejected" ? null : viaItem.id;
    return "ex-" + id;
  }

  positionItems.forEach(function (p) {
    const dKey = departmentKeyOf(p);
    nodes[p.id] = {
      key: p.id,
      item: p,
      virtual: false,
      title: shownTitle(p),
      departmentName: nameOf[dKey] || "",
      departmentKey: dKey,
      color: colorOf[dKey] || NEUTRAL_COLOR,
      isCritical: p.is_critical === true,
      criticalLabel: criticalLabelOf(p),
      children: [],
    };
    if (p.reports_to_ref) {
      const boss = positionItems.find(function (x) { return x.ref === p.reports_to_ref; });
      bossKey[p.id] = boss ? boss.id : null;
    } else {
      bossKey[p.id] = keyOfRealPosition(p.reports_to_position_id);
    }
  });

  existingPositions.forEach(function (p) {
    if (itemOfRealId[p.id]) return;
    addExistingDepartmentOf(p.department_id);
    const dKey = "id:" + p.department_id;
    const key = "ex-" + p.id;
    nodes[key] = {
      key: key,
      item: null,
      virtual: false,
      title: p.title,
      departmentName: nameOf[dKey] || existingDepartmentName[p.department_id] || "",
      departmentKey: dKey,
      color: colorOf[dKey] || NEUTRAL_COLOR,
      isCritical: false,
      criticalLabel: null,
      children: [],
    };
    bossKey[key] = keyOfRealPosition(p.reports_to_position_id);
  });

  // Hang each box under its boss. A boss that is not on screen (skipped, deleted)
  // means the box is a top. A box in a reporting ring is also made a top, so the
  // drawing can never loop forever.
  const roots: ChartNode[] = [];
  const keys = Object.keys(nodes);

  function reachesItself(startKey: string): boolean {
    let current: string | null = bossKey[startKey];
    for (let steps = 0; current && steps < 50; steps += 1) {
      if (current === startKey) return true;
      current = bossKey[current] || null;
    }
    return false;
  }

  keys.forEach(function (key) {
    const boss = bossKey[key];
    const bossExists = boss ? nodes[boss] !== undefined : false;
    if (bossExists && !reachesItself(key)) {
      nodes[boss as string].children.push(nodes[key]);
    } else {
      roots.push(nodes[key]);
    }
  });

  let chart: ChartNode | null = null;
  if (roots.length === 1) {
    chart = roots[0];
  } else if (roots.length > 1) {
    chart = {
      key: "virtual-root",
      item: null,
      virtual: true,
      title: "Company",
      departmentName: "",
      departmentKey: "",
      color: NEUTRAL_COLOR,
      isCritical: false,
      criticalLabel: null,
      children: roots,
    };
  }

  // --- the department chart ---------------------------------------------------
  // Walk the role chart. A role in the same department as the role above it sits one step
  // deeper in that department's list; a role whose boss is in ANOTHER department makes its
  // department a child of the boss's department (the first time this is seen).
  const cardOf: Record<string, DepartmentCard> = {};
  departments.forEach(function (d) { cardOf[d.key] = d; });
  const parentDepartment: Record<string, string> = {};

  function walk(node: ChartNode, parent: ChartNode | null, depthInDepartment: number) {
    let depth = 0;
    if (!node.virtual) {
      const sameAsParent = parent !== null && !parent.virtual && parent.departmentKey === node.departmentKey;
      depth = sameAsParent ? depthInDepartment : 0;
      if (cardOf[node.departmentKey]) cardOf[node.departmentKey].roles.push({ node: node, depth: depth });
      if (
        parent !== null && !parent.virtual && node.departmentKey !== "" &&
        parent.departmentKey !== "" && parent.departmentKey !== node.departmentKey &&
        parentDepartment[node.departmentKey] === undefined
      ) {
        parentDepartment[node.departmentKey] = parent.departmentKey;
      }
    }
    node.children.forEach(function (child) { walk(child, node, node.virtual ? 0 : depth + 1); });
  }
  if (chart) walk(chart, null, 0);

  // A department that would end up under itself (a loop of departments) is made a top.
  function climbsToItself(start: string): boolean {
    let current: string | undefined = parentDepartment[start];
    for (let steps = 0; current !== undefined && steps < 50; steps += 1) {
      if (current === start) return true;
      current = parentDepartment[current];
    }
    return false;
  }

  const departmentNodes: Record<string, DepartmentChartNode> = {};
  departments.forEach(function (d) {
    if (d.item && d.item.status === "rejected") return;
    departmentNodes[d.key] = { key: d.key, virtual: false, card: d, children: [] };
  });
  const departmentRoots: DepartmentChartNode[] = [];
  Object.keys(departmentNodes).forEach(function (key) {
    const parentKey = parentDepartment[key];
    if (parentKey !== undefined && departmentNodes[parentKey] && !climbsToItself(key)) {
      departmentNodes[parentKey].children.push(departmentNodes[key]);
    } else {
      departmentRoots.push(departmentNodes[key]);
    }
  });
  let departmentChart: DepartmentChartNode | null = null;
  if (departmentRoots.length === 1) {
    departmentChart = departmentRoots[0];
  } else if (departmentRoots.length > 1) {
    departmentChart = { key: "company", virtual: true, card: null, children: departmentRoots };
  }

  // --- objectives, grouped by department (company-wide first) ----------------
  function groupsOf(match: (o: BlueprintItem) => boolean): ObjectiveGroup[] {
    return objectiveItems.filter(match).map(function (o) {
      return {
        objective: o,
        keyResults: keyResultItems.filter(function (k) { return k.objective_ref === o.ref; }),
      };
    });
  }

  const objectiveSections: ObjectiveSection[] = [];
  const companyWide = groupsOf(function (o) { return departmentKeyOf(o) === ""; });
  if (companyWide.length > 0) {
    objectiveSections.push({ title: "Company-wide", color: null, objectives: companyWide });
  }
  departments.forEach(function (d) {
    const mine = groupsOf(function (o) { return departmentKeyOf(o) === d.key; });
    if (mine.length > 0) {
      objectiveSections.push({ title: d.name, color: d.color, objectives: mine });
    }
  });

  // --- KPIs, grouped by department ------------------------------------------------
  const kpiSections: KpiSection[] = [];
  departments.forEach(function (d) {
    const mine = kpiItems.filter(function (k) { return departmentKeyOf(k) === d.key; });
    if (mine.length > 0) {
      kpiSections.push({ title: d.name, color: d.color, kpis: mine, departmentAnnualReturn: d.annualReturn });
    }
  });

  let totalSharePct = 0;
  departments.forEach(function (d) {
    if (d.sharePct !== null && d.item && d.item.status !== "rejected") totalSharePct += d.sharePct;
  });

  // --- what the plan leaves out, and how lean it is ---------------------------------
  // What covers a left-out item is either another item of this plan (found by its ref) or
  // something the company already has (found by its id). Its kind tells what was left out.
  const folded: FoldedNote[] = [];
  items.forEach(function (i) {
    if (i.kind !== "folded") return;
    let what: "department" | "position" = "department";
    let coveredBy = "";
    const host = i.folded_into_ref ? items.find(function (x) { return x.ref === i.folded_into_ref; }) : undefined;
    if (host) {
      what = host.kind === "position" ? "position" : "department";
      coveredBy = shownTitle(host);
    } else if (i.position_id) {
      what = "position";
      const existing = existingPositions.find(function (p) { return p.id === i.position_id; });
      coveredBy = existing ? existing.title : "";
    } else if (i.department_id) {
      coveredBy = existingDepartmentName[i.department_id] || "";
    }
    folded.push({ item: i, what: what, coveredBy: coveredBy });
  });

  const keptDepartments = departmentItems.filter(function (d) { return d.status !== "rejected"; }).length;
  const leftOutDepartments = folded.filter(function (f) { return f.what === "department"; }).length;
  const leftOutRoles = folded.length - leftOutDepartments;
  const lean: LeanCounts = {
    departments: keptDepartments,
    roles: positionItems.length,
    fullDepartments: keptDepartments + leftOutDepartments,
    fullRoles: positionItems.length + leftOutRoles,
  };

  return {
    capital: capital,
    totalSharePct: totalSharePct,
    departments: departments,
    departmentChart: departmentChart,
    chart: chart,
    objectiveSections: objectiveSections,
    kpiSections: kpiSections,
    cleanups: cleanups,
    folded: folded,
    lean: lean,
  };
}
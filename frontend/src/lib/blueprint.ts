import { apiFetch } from "@/lib/api";

// The "blueprint" is what the AI proposes for a company right after its first
// Business DNA save: departments, positions (with who each reports to), objectives
// with key results, and clean-ups of what the company already has. Nothing is real
// until HR approves it. Backend: docs/05_API_DESIGN.md "Blueprint".

export type BlueprintKind =
  | "department"
  | "position"
  | "objective"
  | "key_result"
  | "rename_department"
  | "rename_position"
  | "review_note";

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

export function editBlueprintItem(id: string, title: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/edit", { method: "POST", body: { title: title } });
}

export function rejectBlueprintItem(id: string): Promise<BlueprintItem> {
  return apiFetch<BlueprintItem>("/blueprint/" + id + "/reject", { method: "POST" });
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
// own wording, an approved one the AI's.
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
  color: string;
  children: ChartNode[];
}

export interface ObjectiveSection {
  title: string;
  color: string | null;
  objectives: ObjectiveGroup[];
}

export interface BlueprintView {
  departments: DepartmentCard[];
  chart: ChartNode | null;
  objectiveSections: ObjectiveSection[];
  cleanups: BlueprintItem[];
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
  existingPositions: ExistingPosition[]
): BlueprintView {
  const departmentItems = items.filter(function (i) { return i.kind === "department"; });
  const positionItems = items.filter(function (i) { return i.kind === "position" && i.status !== "rejected"; });
  const objectiveItems = items.filter(function (i) { return i.kind === "objective"; });
  const keyResultItems = items.filter(function (i) { return i.kind === "key_result"; });
  const cleanups = items.filter(function (i) {
    return i.kind === "rename_department" || i.kind === "rename_position" || i.kind === "review_note";
  });

  const existingDepartmentName: Record<string, string> = {};
  existingDepartments.forEach(function (d) { existingDepartmentName[d.id] = d.name; });

  // --- departments and their colours --------------------------------------
  const departments: DepartmentCard[] = [];
  const colorOf: Record<string, string> = {};
  const nameOf: Record<string, string> = {};

  function addDepartment(key: string, name: string, item: BlueprintItem | null) {
    if (colorOf[key]) return;
    colorOf[key] = DEPARTMENT_COLORS[departments.length % DEPARTMENT_COLORS.length];
    nameOf[key] = name;
    departments.push({ key: key, name: name, color: colorOf[key], item: item });
  }

  departmentItems.forEach(function (d) {
    addDepartment("ref:" + d.ref, shownTitle(d), d);
  });
  // Existing departments that something on screen belongs to, plus the ones the
  // company's own positions sit in.
  function addExistingDepartmentOf(id: string | null) {
    if (id && existingDepartmentName[id]) addDepartment("id:" + id, existingDepartmentName[id], null);
  }
  positionItems.concat(objectiveItems).forEach(function (i) { addExistingDepartmentOf(i.department_id); });

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
      color: colorOf[dKey] || NEUTRAL_COLOR,
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
      color: colorOf[dKey] || NEUTRAL_COLOR,
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
      color: NEUTRAL_COLOR,
      children: roots,
    };
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

  return { departments: departments, chart: chart, objectiveSections: objectiveSections, cleanups: cleanups };
}

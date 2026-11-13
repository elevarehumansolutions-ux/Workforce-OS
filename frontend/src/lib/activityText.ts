// Turns an audit-log row (action + what it acted on) into a sentence for "Recent activity",
// for example action "create" + entity "department" -> "added a department".
// Every screen that lists activity uses this, so the same event reads the same everywhere.

// The thing that was acted on, with its article.
const THING: Record<string, string> = {
  task: "a task",
  task_block: "a blocked task",
  employee: "an employee",
  department: "a department",
  position: "a position",
  location: "a location",
  kpi: "a KPI",
  kpi_score: "a KPI score",
  okr: "an objective",
  key_result: "a key result",
  workflow_template: "a workflow template",
  workflow_instance: "a workflow case",
  workflow_step: "a workflow step",
  membership: "a team member",
  invite: "a team invite",
  attendance_record: "an attendance record",
  business_dna: "the business profile",
  business_dna_core_value: "a core value",
  blueprint_item: "a plan item",
  ai_suggestion: "a plan suggestion",
};

// What was done, in the past tense. The thing follows it: "added" + "a department".
const DOING: Record<string, string> = {
  create: "added",
  add: "added",
  update: "updated",
  edit: "edited",
  delete: "removed",
  cancel: "cancelled",
  approve: "approved",
  reject: "rejected",
  undo: "undid",
  undo_merge: "undid the merge of",
  redo: "redid",
  complete: "completed",
  start: "started",
  block: "blocked",
  unblock: "unblocked",
  reassign: "reassigned",
  unassign: "unassigned",
  reorder: "reordered",
  offboard: "offboarded",
  reinstate: "reinstated",
  reactivate: "reactivated",
  link_user: "linked a login to",
  grant_login: "gave login access to",
  skip_step: "skipped a step of",
  invite: "sent",
};

// Actions that already say everything, so no "thing" is added after them.
const STANDALONE: Record<string, string> = {
  clock_in: "clocked in",
  clock_out: "clocked out",
  auto_close: "had an attendance record closed automatically",
};

// "business_dna_core_value" -> "business dna core value", only for things not listed above.
function plainWords(text: string): string {
  return text.replace(/_/g, " ");
}

// "an employee" -> "employee": the kind without its article, to put before a name.
function kindWord(entityType: string): string {
  const withArticle = THING[entityType] || "a " + plainWords(entityType);
  return withArticle.replace(/^(a|an|the) /, "");
}

// ``subject`` is what the row was about, from the server ("Chidi Okafor (chidi@x.com)", "Sales").
// With it the sentence names the thing: "added employee Chidi Okafor (chidi@x.com)".
export function describeActivity(action: string, entityType: string, subject?: string | null): string {
  if (STANDALONE[action]) {
    return STANDALONE[action];
  }

  if (subject) {
    // An invite is about an email address, a membership about a person added to the team.
    if (entityType === "invite") {
      return "invited " + subject;
    }
    if (entityType === "membership" && action === "add") {
      return "added " + subject + " to the team";
    }
    const verb = DOING[action] || plainWords(action);
    return verb + " " + kindWord(entityType) + " " + subject;
  }

  const thing = THING[entityType] || "a " + plainWords(entityType);
  const doing = DOING[action] || plainWords(action);
  return doing + " " + thing;
}

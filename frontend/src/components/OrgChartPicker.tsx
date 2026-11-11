"use client";

// A window that shows the organization chart (who reports to whom) and lets the person
// pick on it, instead of choosing from a drop-down list of names. Used wherever someone
// has to say "who does this report to".

export interface PickerPosition {
  id: string;
  title: string;
  department_id: string;
  reports_to_position_id: string | null;
}

export interface PickerEmployee {
  id: string;
  first_name: string;
  last_name: string;
  position_id?: string | null;
  // "active" or "inactive" (offboarded); someone who has left is not offered as a manager.
  status?: string | null;
}

export interface PickerDepartment {
  id: string;
  name: string;
}

interface Box {
  position: PickerPosition;
  children: Box[];
}

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4", "#8b5cf6", "#ef4444", "#84cc16"];

// Turns the flat list of roles into a tree. A role whose boss is not in the list, and a
// role in a reporting ring, becomes a top, so the drawing can never loop.
function buildBoxes(positions: PickerPosition[]): Box[] {
  const boxes: Record<string, Box> = {};
  positions.forEach(function (p) {
    boxes[p.id] = { position: p, children: [] };
  });

  function reachesItself(startId: string): boolean {
    let current: string | null = boxes[startId].position.reports_to_position_id;
    for (let steps = 0; current && steps < 50; steps += 1) {
      if (current === startId) return true;
      current = boxes[current] ? boxes[current].position.reports_to_position_id : null;
    }
    return false;
  }

  const roots: Box[] = [];
  positions.forEach(function (p) {
    const boss = p.reports_to_position_id;
    if (boss && boxes[boss] && !reachesItself(p.id)) {
      boxes[boss].children.push(boxes[p.id]);
    } else {
      roots.push(boxes[p.id]);
    }
  });
  return roots;
}

interface OrgChartPickerProps {
  // "position": click a role. "manager": click a person.
  mode: "position" | "manager";
  title: string;
  positions: PickerPosition[];
  employees: PickerEmployee[];
  departments: PickerDepartment[];
  // The role (position mode) or person (manager mode) chosen right now.
  selectedId: string;
  // Where the person being added will sit, drawn as a dashed "new" box under that role.
  newHire?: { positionId: string; name: string } | null;
  // Roles that cannot be chosen (for example a role and everything under it, when picking its boss).
  disabledPositionIds?: string[];
  onSelect: (id: string) => void;
  onClose: () => void;
}

export default function OrgChartPicker(props: OrgChartPickerProps) {
  const roots = buildBoxes(props.positions);
  const disabled = new Set(props.disabledPositionIds || []);

  const colorOfDepartment: Record<string, string> = {};
  props.departments.forEach(function (d, i) {
    colorOfDepartment[d.id] = COLORS[i % COLORS.length];
  });
  const departmentName: Record<string, string> = {};
  props.departments.forEach(function (d) {
    departmentName[d.id] = d.name;
  });

  const peopleByPosition: Record<string, PickerEmployee[]> = {};
  props.employees.forEach(function (e) {
    if (!e.position_id || e.status === "inactive") return;
    if (!peopleByPosition[e.position_id]) peopleByPosition[e.position_id] = [];
    peopleByPosition[e.position_id].push(e);
  });

  const nobodyIsPlaced = Object.keys(peopleByPosition).length === 0;

  function renderBox(box: Box) {
    const p = box.position;
    const color = colorOfDepartment[p.department_id] || "#6b7280";
    const people = peopleByPosition[p.id] || [];
    const isDisabled = disabled.has(p.id);
    const selectedHere = props.mode === "position" && props.selectedId === p.id;
    const holdsSelected = people.some(function (e) { return e.id === props.selectedId; });

    return (
      <div
        className={
          "inline-block w-52 rounded-xl border bg-[#0a0e1a] px-3 pb-3 pt-2.5 text-left shadow-lg " +
          (selectedHere || holdsSelected ? "border-indigo-400 ring-2 ring-indigo-400/40" : "border-white/10") +
          (isDisabled ? " opacity-40" : "")
        }
        style={{ borderTop: "3px solid " + color }}
      >
        {props.mode === "position" ? (
          <button
            type="button"
            disabled={isDisabled}
            onClick={function () { props.onSelect(p.id); }}
            className="block w-full text-left disabled:cursor-not-allowed"
            title={isDisabled ? "A role cannot report to itself or to a role under it" : "Choose this role"}
          >
            <span className="block text-sm font-semibold leading-snug text-white">{p.title}</span>
            <span className="mt-0.5 flex items-center gap-1.5 text-xs text-gray-400">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {departmentName[p.department_id] || ""}
            </span>
          </button>
        ) : (
          <div>
            <p className="text-sm font-semibold leading-snug text-white">{p.title}</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-gray-400">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {departmentName[p.department_id] || ""}
            </p>
          </div>
        )}

        {props.mode === "manager" ? (
          <div className="mt-2 space-y-1">
            {people.length === 0 ? (
              <p className="rounded-md border border-dashed border-white/10 px-2 py-1 text-[11px] text-gray-500">
                Vacant: no one holds this role yet
              </p>
            ) : (
              people.map(function (e) {
                const chosen = props.selectedId === e.id;
                return (
                  <button
                    key={e.id}
                    type="button"
                    onClick={function () { props.onSelect(e.id); }}
                    className={
                      "block w-full rounded-md px-2 py-1 text-left text-xs " +
                      (chosen ? "bg-indigo-500 font-semibold text-white" : "bg-white/5 text-gray-200 hover:bg-white/10")
                    }
                  >
                    {e.first_name} {e.last_name}
                  </button>
                );
              })
            )}
          </div>
        ) : people.length > 0 ? (
          <p className="mt-1.5 text-[11px] text-gray-500">
            {people.map(function (e) { return e.first_name + " " + e.last_name; }).join(", ")}
          </p>
        ) : null}
      </div>
    );
  }

  function renderNode(box: Box) {
    const isNewHireSeat = props.newHire ? props.newHire.positionId === box.position.id : false;
    return (
      <li key={box.position.id}>
        {renderBox(box)}
        {box.children.length > 0 || isNewHireSeat ? (
          <ul>
            {box.children.map(renderNode)}
            {isNewHireSeat && props.newHire ? (
              <li key="new-hire">
                <div className="inline-block w-44 rounded-xl border border-dashed border-emerald-400/70 bg-emerald-500/5 px-3 py-2 text-left">
                  <p className="text-xs font-semibold text-emerald-300">New</p>
                  <p className="text-sm text-white">{props.newHire.name || "This person"}</p>
                  <p className="text-[11px] text-gray-400">joins as {box.position.title}</p>
                </div>
              </li>
            ) : null}
          </ul>
        ) : null}
      </li>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8" role="dialog" aria-modal="true">
      <div className="w-full max-w-6xl rounded-2xl border border-white/10 bg-[#0d1220] p-5 shadow-2xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">{props.title}</h2>
            <p className="mt-0.5 text-sm text-gray-400">
              {props.mode === "position"
                ? "Click the role this one reports to. The lines show who reports to whom."
                : "Click the person this employee reports to. The lines show who reports to whom."}
            </p>
          </div>
          <button type="button" onClick={props.onClose} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
            Done
          </button>
        </div>

        {props.mode === "manager" && nobodyIsPlaced ? (
          <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            No one has been added to any role yet, so there is nobody to choose. Close this window, finish adding this
            person, then add the people below them. Or add the most senior person first, and come back to set managers.
          </p>
        ) : null}

        {props.positions.length === 0 ? (
          <p className="mt-6 rounded-lg border border-white/10 p-6 text-center text-sm text-gray-400">
            There are no roles yet, so there is no chart to show.
          </p>
        ) : (
          <div className="mt-5 overflow-x-auto pb-3 [color-scheme:dark]">
            <div className="org-tree mx-auto w-max min-w-full">
              <ul>
                {roots.length === 1 ? (
                  renderNode(roots[0])
                ) : (
                  <li>
                    <div className="inline-block rounded-full border border-white/20 bg-[#111726] px-5 py-2 text-sm font-semibold text-gray-200">
                      Company
                    </div>
                    <ul>{roots.map(renderNode)}</ul>
                  </li>
                )}
              </ul>
            </div>
          </div>
        )}

        {props.mode === "manager" ? (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-gray-500">The person at the very top has no manager.</p>
            <button
              type="button"
              onClick={function () { props.onSelect(""); }}
              className="text-xs text-gray-400 underline hover:text-gray-200"
            >
              No manager
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

"use client";

import { COLORS, buildBoxes } from "@/components/OrgChartPicker";
import type { Box, PickerDepartment, PickerEmployee, PickerPosition } from "@/components/OrgChartPicker";

// The organization chart on a page (not a window): every role with the people who hold it inside
// its box, "Vacant" where nobody does, a star on a department head, and "shared by N" on a role
// several people hold. Clicking a person tells the page, which decides what to show.

interface OrgChartViewProps {
  positions: PickerPosition[];
  employees: PickerEmployee[];
  departments: PickerDepartment[];
  // Employee ids that head a department, shown with a star.
  headIds: string[];
  selectedPersonId: string;
  onSelectPerson: (id: string) => void;
}

export default function OrgChartView(props: OrgChartViewProps) {
  const roots = buildBoxes(props.positions);

  const colorOfDepartment: Record<string, string> = {};
  const nameOfDepartment: Record<string, string> = {};
  props.departments.forEach(function (d, i) {
    colorOfDepartment[d.id] = COLORS[i % COLORS.length];
    nameOfDepartment[d.id] = d.name;
  });

  // Active people by role. Someone whose role is not on the chart is listed apart, below it.
  const roleIds = new Set(props.positions.map(function (p) { return p.id; }));
  const peopleByRole: Record<string, PickerEmployee[]> = {};
  const withoutRole: PickerEmployee[] = [];
  props.employees.forEach(function (e) {
    if (e.status === "inactive") return;
    if (e.position_id && roleIds.has(e.position_id)) {
      if (!peopleByRole[e.position_id]) peopleByRole[e.position_id] = [];
      peopleByRole[e.position_id].push(e);
    } else {
      withoutRole.push(e);
    }
  });

  function personButton(e: PickerEmployee) {
    const chosen = props.selectedPersonId === e.id;
    const isHead = props.headIds.indexOf(e.id) !== -1;
    return (
      <button
        key={e.id}
        type="button"
        onClick={function () { props.onSelectPerson(e.id); }}
        className={
          "block w-full rounded-md px-2 py-1 text-left text-xs " +
          (chosen ? "bg-indigo-500 font-semibold text-white" : "bg-white/5 text-gray-200 hover:bg-white/10")
        }
      >
        {isHead ? <span className="mr-1 text-amber-300" title="Head of the department">★</span> : null}
        {e.first_name} {e.last_name}
      </button>
    );
  }

  function renderBox(box: Box) {
    const p = box.position;
    const color = colorOfDepartment[p.department_id] || "#6b7280";
    const people = peopleByRole[p.id] || [];
    return (
      <div
        className="inline-block w-52 rounded-xl border border-white/10 bg-[#0a0e1a] px-3 pb-3 pt-2.5 text-left shadow-lg"
        style={{ borderTop: "3px solid " + color }}
      >
        <p className="text-sm font-semibold leading-snug text-white">{p.title}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-gray-400">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
          {nameOfDepartment[p.department_id] || ""}
          {people.length > 1 ? (
            <span className="rounded bg-amber-500/15 px-1 text-[11px] text-amber-300">shared by {people.length}</span>
          ) : null}
        </p>
        <div className="mt-2 space-y-1">
          {people.length === 0 ? (
            <p className="rounded-md border border-dashed border-white/10 px-2 py-1 text-[11px] text-gray-500">Vacant</p>
          ) : (
            people.map(personButton)
          )}
        </div>
      </div>
    );
  }

  function renderNode(box: Box) {
    return (
      <li key={box.position.id}>
        {renderBox(box)}
        {box.children.length > 0 ? <ul>{box.children.map(renderNode)}</ul> : null}
      </li>
    );
  }

  if (props.positions.length === 0) {
    return (
      <p className="rounded-lg border border-white/10 p-6 text-center text-sm text-gray-400">
        There are no roles yet, so there is no chart to show.
      </p>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto pb-3 [color-scheme:dark]">
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

      {withoutRole.length > 0 ? (
        <div className="mt-4 rounded-lg border border-white/10 bg-[#0a0e1a] p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Not on the chart ({withoutRole.length}): their role is missing or was removed
          </p>
          <div className="mt-2 flex flex-wrap gap-2">{withoutRole.map(personButton)}</div>
        </div>
      ) : null}
    </div>
  );
}

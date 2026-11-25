"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import type { MoveDepartment, MoveRole } from "@/components/MovePersonDialog";
import { ApiError, apiFetch } from "@/lib/api";
import { fullName } from "@/lib/tasks";
import type { Employee } from "@/lib/tasks";

interface MoveRoleDialogProps {
  role: MoveRole;
  departments: MoveDepartment[];
  employees: Employee[];
  // Set when the role was dropped onto a department on the chart.
  startDepartmentId?: string;
  // The message is empty when the window was closed without moving.
  onClose: (message: string) => void;
}

export default function MoveRoleDialog(props: MoveRoleDialogProps) {
  const [departmentId, setDepartmentId] = useState(props.startDepartmentId || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const oldDepartment = props.departments.find(function (d) { return d.id === props.role.department_id; });
  const newDepartment = props.departments.find(function (d) { return d.id === departmentId; });
  const holders = props.employees.filter(function (e) { return e.position_id === props.role.id && e.status === "active"; });
  const leavingHead = holders.find(function (e) { return oldDepartment !== undefined && oldDepartment.head_employee_id === e.id; });

  async function move() {
    if (!newDepartment) return;
    setBusy(true);
    setError("");
    try {
      await apiFetch("/positions/" + props.role.id + "/move", { method: "POST", body: { department_id: newDepartment.id } });
      props.onClose(props.role.title + " is now in " + newDepartment.name + ".");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't move that role. Try again.");
      setBusy(false);
    }
  }

  return (
    <Modal title={"Move the role " + props.role.title} onClose={function () { props.onClose(""); }}>
      <div className="space-y-4 text-sm">
        <p className="text-gray-400">Now in {oldDepartment ? oldDepartment.name : "no department"}</p>

        <label className="block text-xs text-gray-400">
          Move to department
          <select
            value={departmentId}
            onChange={function (e) { setDepartmentId(e.target.value); }}
            className="mt-1 block w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500"
          >
            <option value="">Choose a department</option>
            {props.departments
              .filter(function (d) { return d.id !== props.role.department_id; })
              .map(function (d) { return <option key={d.id} value={d.id}>{d.name}</option>; })}
          </select>
        </label>

        {newDepartment ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
            <p className="font-semibold">What will change</p>
            <ul className="mt-1 list-disc space-y-1 pl-4">
              <li>
                {holders.length === 0 ? "Nobody holds this role, so only the role moves." : "These people move with it: " + holders.map(fullName).join(", ") + "."}
              </li>
              {leavingHead && oldDepartment ? <li>{oldDepartment.name} will have no head, because {fullName(leavingHead)} is leaving it.</li> : null}
              <li>Reporting lines, tasks, past scores and access levels do not change.</li>
            </ul>
          </div>
        ) : null}

        {error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p> : null}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={function () { props.onClose(""); }} className="rounded-lg border border-white/10 px-4 py-2 text-xs text-gray-300 hover:bg-white/5">
            Cancel
          </button>
          <button type="button" disabled={!newDepartment || busy} onClick={move} className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50">
            {busy ? "Moving…" : newDepartment ? "Move to " + newDepartment.name : "Move"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

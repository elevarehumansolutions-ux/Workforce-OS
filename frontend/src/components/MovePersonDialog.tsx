"use client";

import { useState } from "react";
import Link from "next/link";
import Modal from "@/components/Modal";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchAllPages, fullName } from "@/lib/tasks";
import type { Employee, Task } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";

const FIELD =
  "mt-1 block w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500";

export interface MoveDepartment {
  id: string;
  name: string;
  head_employee_id: string | null;
}

export interface MoveRole {
  id: string;
  department_id: string;
  title: string;
  reports_to_position_id: string | null;
}

interface MoveData {
  departments: MoveDepartment[];
  roles: MoveRole[];
  employees: Employee[];
  // The person's unfinished tasks: shown so someone can reassign them.
  openTasks: Task[];
}

async function loadMoveData(employeeId: string): Promise<MoveData> {
  const results = await Promise.all([
    fetchAllPages<MoveDepartment>("/departments"),
    fetchAllPages<MoveRole>("/positions"),
    fetchAllPages<Employee>("/employees"),
    fetchAllPages<Task>("/tasks?assigned_to_employee_id=" + employeeId),
  ]);
  const openTasks = results[3].filter(function (task) {
    return task.status !== "completed" && task.status !== "cancelled";
  });
  return { departments: results[0], roles: results[1], employees: results[2], openTasks: openTasks };
}

// The same rule as the server: the manager is the one active person holding the role above.
// A role created here has no role above it, so it gives no manager.
function newManager(data: MoveData, role: MoveRole | undefined, employeeId: string): Employee | null {
  if (!role || !role.reports_to_position_id) return null;
  const bosses = data.employees.filter(function (e) {
    return e.position_id === role.reports_to_position_id && e.status === "active" && e.id !== employeeId;
  });
  return bosses.length === 1 ? bosses[0] : null;
}

// The value of the role list that means "make a new role in this department".
const NEW_ROLE = "new";

interface MovePersonDialogProps {
  employeeId: string;
  // Set when the person was dropped onto a role on the chart, so it is already chosen.
  startRoleId?: string;
  // The message is empty when the window was closed without moving.
  onClose: (message: string) => void;
}

export default function MovePersonDialog(props: MovePersonDialogProps) {
  const [reload, setReload] = useState(0);
  const state = useLoad<MoveData>(
    "move-person|" + props.employeeId + "|" + reload,
    function () { return loadMoveData(props.employeeId); },
    "Couldn't load what is needed to move them. Close this window and try again."
  );
  // Empty until HR picks one; a dropped-on role counts as picked.
  const [pickedDepartmentId, setPickedDepartmentId] = useState("");
  const [roleId, setRoleId] = useState(props.startRoleId || "");
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const data = state.data;
  const person = data ? data.employees.find(function (e) { return e.id === props.employeeId; }) : undefined;
  const oldRole = data && person ? data.roles.find(function (r) { return r.id === person.position_id; }) : undefined;
  const chosenRole = data ? data.roles.find(function (r) { return r.id === roleId; }) : undefined;
  const departmentId = chosenRole ? chosenRole.department_id : pickedDepartmentId;
  const ready = roleId === NEW_ROLE ? departmentId !== "" && newTitle.trim() !== "" : chosenRole !== undefined;

  async function move() {
    if (!person || !ready) return;
    setBusy(true);
    setError("");
    let targetId = roleId;
    try {
      if (roleId === NEW_ROLE) {
        const created = await apiFetch<MoveRole>("/positions", {
          method: "POST",
          body: { department_id: departmentId, title: newTitle.trim() },
        });
        // Remember it: if the move below fails, trying again must not create the role twice.
        targetId = created.id;
        setPickedDepartmentId(departmentId);
        setRoleId(created.id);
        setReload(reload + 1);
      }
      await apiFetch("/employees/" + person.id + "/move", { method: "POST", body: { position_id: targetId } });
      props.onClose(fullName(person) + " was moved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't move them. Try again.");
      setBusy(false);
    }
  }

  const oldDepartment = data && oldRole ? data.departments.find(function (d) { return d.id === oldRole.department_id; }) : undefined;
  const newDepartment = data ? data.departments.find(function (d) { return d.id === departmentId; }) : undefined;
  const losesHeadship =
    person !== undefined && oldDepartment !== undefined && oldDepartment.head_employee_id === person.id && departmentId !== oldDepartment.id;
  const manager = data && person ? newManager(data, chosenRole, person.id) : null;
  const reports = data && person ? data.employees.filter(function (e) { return e.manager_id === person.id && e.status === "active"; }) : [];

  return (
    <Modal title={person ? "Move " + fullName(person) : "Move"} onClose={function () { props.onClose(""); }}>
      {state.loading ? <p className="text-sm text-gray-400">Loading…</p> : null}
      {state.error ? <p className="text-sm text-red-300">{state.error}</p> : null}
      {data && person ? (
        <div className="space-y-4 text-sm">
          <p className="text-gray-400">
            Now: {oldRole ? oldRole.title : "no role"}{oldDepartment ? ", " + oldDepartment.name : ""}
          </p>

          <label className="block text-xs text-gray-400">
            Move to department
            <select
              value={departmentId}
              onChange={function (e) { setPickedDepartmentId(e.target.value); setRoleId(""); }}
              className={FIELD}
            >
              <option value="">Choose a department</option>
              {data.departments.map(function (d) { return <option key={d.id} value={d.id}>{d.name}</option>; })}
            </select>
          </label>

          {departmentId ? (
            <label className="block text-xs text-gray-400">
              Role
              <select value={roleId} onChange={function (e) { setPickedDepartmentId(departmentId); setRoleId(e.target.value); }} className={FIELD}>
                <option value="">Choose a role</option>
                {data.roles
                  .filter(function (r) { return r.department_id === departmentId && r.id !== person.position_id; })
                  .map(function (r) { return <option key={r.id} value={r.id}>{r.title}</option>; })}
                <option value={NEW_ROLE}>+ Create a new role here</option>
              </select>
            </label>
          ) : null}

          {roleId === NEW_ROLE ? (
            <label className="block text-xs text-gray-400">
              New role title
              <input value={newTitle} maxLength={255} onChange={function (e) { setNewTitle(e.target.value); }} className={FIELD} />
            </label>
          ) : null}

          {ready ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              <p className="font-semibold">What will change</p>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {losesHeadship && oldDepartment ? <li>{oldDepartment.name} will have no head. Choose a new one afterwards.</li> : null}
                <li>{manager ? "Their manager will be " + fullName(manager) + "." : "They will have no manager set. You can set one afterwards."}</li>
                {reports.length > 0 ? <li>{reports.length === 1 ? "1 person still reports" : reports.length + " people still report"} to them.</li> : null}
                {data.openTasks.length > 0 ? (
                  <li>
                    Their unfinished tasks stay with their department and stay assigned to them. Reassign them if needed:
                    {data.openTasks.slice(0, 5).map(function (t) {
                      return <Link key={t.id} href={"/tasks/" + t.id} className="ml-1 block underline">{t.title}</Link>;
                    })}
                    {data.openTasks.length > 5 ? <span className="block">and {data.openTasks.length - 5} more</span> : null}
                  </li>
                ) : null}
                <li>Past scores and their access level do not change.</li>
              </ul>
            </div>
          ) : null}

          {error ? <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p> : null}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={function () { props.onClose(""); }} className="rounded-lg border border-white/10 px-4 py-2 text-xs text-gray-300 hover:bg-white/5">
              Cancel
            </button>
            <button type="button" disabled={!ready || busy} onClick={move} className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50">
              {busy ? "Moving…" : newDepartment ? "Move to " + newDepartment.name : "Move"}
            </button>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

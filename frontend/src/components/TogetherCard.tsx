"use client";

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { departmentName, employeeName, statusLabel } from "@/lib/tasks";
import type { CallerContext, PaginatedResponse, Task } from "@/lib/tasks";
import { useLoad } from "@/lib/useLoad";

// Shown on a task that other departments work on with this one:
//  - a task created for several departments at once lists the others' copies (the ones this person may see);
//  - a task that is part of a workflow step done together says so, and points to the case.
// Shows nothing for an ordinary task.
export default function TogetherCard({ task, ctx }: { task: Task; ctx: CallerContext }) {
  const groupId = task.shared_group_id;
  const siblings = useLoad<Task[]>(
    "together|" + (groupId || "none"),
    function () {
      if (!groupId) return Promise.resolve([]);
      return apiFetch<PaginatedResponse<Task>>("/tasks?shared_group_id=" + groupId + "&limit=20", { method: "GET" }).then(function (res) {
        return res.data;
      });
    },
    "Couldn't load the other departments' copies."
  );

  const others = (siblings.data || []).filter(function (t) {
    return t.id !== task.id;
  });

  if (task.workflow_task_role) {
    return (
      <div className="mt-6 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-100">
        <p>
          {task.workflow_task_role === "lead"
            ? "This is one department's part of a workflow step that several departments do together. The other departments have their own tasks."
            : "This is your department's part of a workflow step that several departments do together. The other departments have their own tasks."}
        </p>
        {task.workflow_instance_id ? (
          <Link href={"/workflow/case-detail?id=" + task.workflow_instance_id} className="mt-1 inline-block text-xs font-medium text-indigo-300 hover:text-indigo-200">
            See every department&apos;s progress on the case
          </Link>
        ) : null}
      </div>
    );
  }

  if (!groupId || others.length === 0) return null;

  return (
    <div className="mt-6 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm">
      <p className="text-xs text-gray-500">The same task is also assigned to</p>
      <ul className="mt-2 space-y-1">
        {others.map(function (t) {
          return (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-gray-200">
                {departmentName(ctx, t.department_id)} · {employeeName(ctx, t.assigned_to_employee_id)} · {statusLabel(t.status)}
              </span>
              <Link href={"/tasks/" + t.id} className="text-xs font-medium text-indigo-400 hover:text-indigo-300">
                Open
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-gray-500">You only see the copies you are allowed to see. Each department finishes its own.</p>
    </div>
  );
}

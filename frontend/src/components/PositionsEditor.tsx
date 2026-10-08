"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

// Positions are the org chart of ROLES (the CTO role reports to the CEO role,
// whoever holds them) — not a person's own manager, which is the "Reporting
// Manager" field on Add Employee. See 05_API_DESIGN.md (Org Structure ->
// "Reporting hierarchy rules on positions").

export interface PositionsEditorDepartment {
  id: string;
  name: string;
}

interface Position {
  id: string;
  department_id: string;
  title: string;
  reports_to_position_id: string | null;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

// There is no tree endpoint, so the chart is drawn from GET /positions —
// which is offset-paginated, so every page has to be fetched before drawing
// or roles on later pages would wrongly look like they're at the top.
async function fetchAllPositions(): Promise<Position[]> {
  const all: Position[] = [];
  let page = 1;
  // Hard stop so a misbehaving response can never loop forever.
  while (page <= 50) {
    const res = await apiFetch<PaginatedResponse<Position>>(
      "/positions?page=" + page + "&limit=100",
      { method: "GET" }
    );
    for (const p of res.data) {
      all.push(p);
    }
    if (!res.pagination.has_next) break;
    page = page + 1;
  }
  return all;
}

// Everything that reports to `rootId`, directly or through a chain. Used to
// hide those from the "Reports to" picker, since picking one would create a
// loop (the server refuses it either way). The visited set keeps this safe
// even if the data somehow already contains a ring.
function collectDescendants(rootId: string, positions: Position[]): Set<string> {
  const childrenOf: Record<string, string[]> = {};
  for (const p of positions) {
    if (p.reports_to_position_id) {
      if (!childrenOf[p.reports_to_position_id]) childrenOf[p.reports_to_position_id] = [];
      childrenOf[p.reports_to_position_id].push(p.id);
    }
  }
  const found = new Set<string>();
  const stack: string[] = [rootId];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    const kids = childrenOf[current] || [];
    for (const kid of kids) {
      if (!found.has(kid)) {
        found.add(kid);
        stack.push(kid);
      }
    }
  }
  return found;
}

export default function PositionsEditor(props: { departments: PositionsEditorDepartment[] }) {
  const departments = props.departments;

  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [deleteHint, setDeleteHint] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [newTitle, setNewTitle] = useState("");
  const [newDepartmentId, setNewDepartmentId] = useState("");
  const [newParentId, setNewParentId] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(function () {
    let cancelled = false;
    fetchAllPositions()
      .then(function (list) {
        if (cancelled) return;
        setPositions(list);
      })
      .catch(function (err) {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load positions.");
      })
      .finally(function () {
        if (!cancelled) setLoading(false);
      });
    return function () {
      cancelled = true;
    };
  }, []);

  function departmentName(id: string): string {
    for (const d of departments) {
      if (d.id === id) return d.name;
    }
    return "Unknown department";
  }

  function positionTitle(id: string): string {
    for (const p of positions) {
      if (p.id === id) return p.title;
    }
    return "Unknown position";
  }

  async function refreshPositions() {
    try {
      const list = await fetchAllPositions();
      setPositions(list);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't refresh positions.");
    }
  }

  async function addPosition() {
    const title = newTitle.trim();
    const departmentId = newDepartmentId || (departments.length === 1 ? departments[0].id : "");
    if (!title || !departmentId) {
      setActionError("Choose a department and enter a title for the position.");
      return;
    }
    setActionError("");
    setDeleteHint(false);
    setAdding(true);
    try {
      const body: Record<string, unknown> = { department_id: departmentId, title: title };
      if (newParentId) body.reports_to_position_id = newParentId;
      await apiFetch<Position>("/positions", { method: "POST", body: body });
      setNewTitle("");
      setNewParentId("");
      await refreshPositions();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't add that position.");
      // The chosen parent may have been deleted since the list loaded.
      if (err instanceof ApiError && err.code === "POSITION_NOT_FOUND") {
        await refreshPositions();
      }
    } finally {
      setAdding(false);
    }
  }

  async function changeParent(position: Position, parentId: string) {
    setActionError("");
    setDeleteHint(false);
    setBusyId(position.id);
    try {
      // null removes the parent (top of the chart); a uuid sets it.
      await apiFetch<Position>("/positions/" + position.id, {
        method: "PATCH",
        body: { reports_to_position_id: parentId ? parentId : null },
      });
      setPositions(
        positions.map(function (p) {
          if (p.id !== position.id) return p;
          return { ...p, reports_to_position_id: parentId ? parentId : null };
        })
      );
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't update that position.");
      // 404 here is about the chosen PARENT (the position being edited does
      // exist) — refresh so the picker stops offering it.
      if (err instanceof ApiError && err.code === "POSITION_NOT_FOUND") {
        await refreshPositions();
      }
    } finally {
      setBusyId(null);
    }
  }

  async function removePosition(position: Position) {
    if (!window.confirm('Delete the position "' + position.title + '"?')) return;
    setActionError("");
    setDeleteHint(false);
    setBusyId(position.id);
    try {
      await apiFetch("/positions/" + position.id, { method: "DELETE" });
      await refreshPositions();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't delete that position.");
      if (err instanceof ApiError && err.status === 409) {
        setDeleteHint(true);
      }
    } finally {
      setBusyId(null);
    }
  }

  // The picker for one position: every position in the organization (the
  // parent can sit in any department), minus itself and its own descendants.
  function parentOptionsFor(position: Position): Position[] {
    const blocked = collectDescendants(position.id, positions);
    return positions.filter(function (p) {
      return p.id !== position.id && !blocked.has(p.id);
    });
  }

  // ---- Reporting chart ----

  const knownIds = new Set<string>(
    positions.map(function (p) {
      return p.id;
    })
  );
  const childrenByParent: Record<string, Position[]> = {};
  const roots: Position[] = [];
  for (const p of positions) {
    if (p.reports_to_position_id && knownIds.has(p.reports_to_position_id)) {
      if (!childrenByParent[p.reports_to_position_id]) childrenByParent[p.reports_to_position_id] = [];
      childrenByParent[p.reports_to_position_id].push(p);
    } else {
      roots.push(p);
    }
  }

  function renderNode(position: Position, depth: number, seen: Set<string>) {
    if (seen.has(position.id) || depth > 30) return null;
    const nextSeen = new Set<string>(seen);
    nextSeen.add(position.id);
    const kids = childrenByParent[position.id] || [];
    return (
      <li key={position.id}>
        <div className="flex items-center gap-2 py-1">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
          <span className="text-sm font-medium text-white">{position.title}</span>
          <span className="text-xs text-gray-500">{departmentName(position.department_id)}</span>
        </div>
        {kids.length > 0 ? (
          <ul className="ml-3 border-l border-white/10 pl-4">
            {kids.map(function (kid) {
              return renderNode(kid, depth + 1, nextSeen);
            })}
          </ul>
        ) : null}
      </li>
    );
  }

  const selectClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-60";
  const inputClass =
    "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500";

  return (
    <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Positions &amp; Reporting Hierarchy</h2>
        <span className="rounded-full bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-300">
          {positions.length} Positions
        </span>
      </div>
      <p className="mt-1 text-sm text-gray-500">
        This is the chart of roles: which role reports to which, whoever holds them. A person&apos;s own
        manager is set separately on the employee.
      </p>

      {loadError ? (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {loadError}
        </div>
      ) : null}
      {actionError ? (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {actionError}
          {deleteHint ? (
            <span className="mt-1 block text-xs text-red-200/80">
              Reassign first: point the positions that report to this one at a different role, move or
              offboard the employees who hold it, then try deleting again.
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Add a position */}
      <div className="mt-5 grid grid-cols-1 gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] p-4 sm:grid-cols-4">
        <input
          type="text"
          value={newTitle}
          onChange={function (e) {
            setNewTitle(e.target.value);
          }}
          onKeyDown={function (e) {
            // This editor can sit inside the onboarding <form>, where Enter
            // would otherwise submit the whole wizard step.
            if (e.key === "Enter") {
              e.preventDefault();
              addPosition();
            }
          }}
          placeholder="Position title, e.g. Chief Technology Officer"
          className={inputClass + " sm:col-span-2"}
        />
        <select
          value={newDepartmentId}
          onChange={function (e) {
            setNewDepartmentId(e.target.value);
          }}
          className={selectClass + " py-2"}
        >
          <option value="">Department…</option>
          {departments.map(function (d) {
            return (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            );
          })}
        </select>
        <select
          value={newParentId}
          onChange={function (e) {
            setNewParentId(e.target.value);
          }}
          className={selectClass + " py-2"}
        >
          <option value="">Reports to: nobody (top)</option>
          {positions.map(function (p) {
            return (
              <option key={p.id} value={p.id}>
                {"Reports to: " + p.title}
              </option>
            );
          })}
        </select>
        <button
          type="button"
          onClick={addPosition}
          disabled={adding || departments.length === 0}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-4 sm:w-fit"
        >
          {adding ? "Adding…" : "+ Add Position"}
        </button>
        {departments.length === 0 ? (
          <p className="text-xs text-amber-300 sm:col-span-4">
            Add at least one department first. Every position belongs to a department.
          </p>
        ) : null}
      </div>

      {/* Existing positions */}
      <div className="mt-5 space-y-2">
        {loading ? (
          <div className="h-14 animate-pulse rounded-lg border border-white/10 bg-white/5" />
        ) : null}

        {!loading && positions.length === 0 && !loadError ? (
          <p className="text-sm text-gray-500">
            No positions yet. Add your first one above, usually the top role, such as the CEO.
          </p>
        ) : null}

        {!loading &&
          positions.map(function (position) {
            const isBusy = busyId === position.id;
            const options = parentOptionsFor(position);
            const currentParent = position.reports_to_position_id || "";
            const parentIsListed =
              currentParent === "" ||
              options.some(function (o) {
                return o.id === currentParent;
              });
            return (
              <div
                key={position.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">{position.title}</p>
                  <p className="text-xs text-gray-500">{departmentName(position.department_id)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <label className="text-xs text-gray-500">Reports to</label>
                  <select
                    value={currentParent}
                    disabled={isBusy}
                    onChange={function (e) {
                      changeParent(position, e.target.value);
                    }}
                    className={selectClass}
                  >
                    <option value="">Nobody (top of chart)</option>
                    {!parentIsListed ? (
                      <option value={currentParent}>{positionTitle(currentParent)}</option>
                    ) : null}
                    {options.map(function (o) {
                      return (
                        <option key={o.id} value={o.id}>
                          {o.title + " · " + departmentName(o.department_id)}
                        </option>
                      );
                    })}
                  </select>
                  <button
                    type="button"
                    onClick={function () {
                      removePosition(position);
                    }}
                    disabled={isBusy}
                    className="text-xs text-gray-500 hover:text-red-400 disabled:opacity-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
      </div>

      {/* Reporting chart */}
      {!loading && positions.length > 0 ? (
        <div className="mt-6 border-t border-white/10 pt-5">
          <h3 className="text-sm font-semibold text-gray-300">Reporting chart</h3>
          <ul className="mt-3">
            {roots.map(function (root) {
              return renderNode(root, 0, new Set<string>());
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

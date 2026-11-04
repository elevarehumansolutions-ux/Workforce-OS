"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchAllPages, formatDateTime, fullName } from "@/lib/tasks";
import type { Employee } from "@/lib/tasks";
import { SETTINGS_INPUT_CLASS, SETTINGS_LABEL_CLASS, canReadAuditLog, titleCase } from "@/lib/settings";
import type { SectionProps } from "./types";

interface AuditRow {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: { old?: unknown; new?: unknown } | null;
  created_at: string;
}

interface AuditPage {
  data: AuditRow[];
  pagination: { next_cursor: string | null; count: number; total?: number };
}

const ENTITY_SUGGESTIONS = ["task", "task_block", "employee", "department", "position", "kpi", "membership", "business_dna", "workflow_template", "workflow_instance"];

export default function AuditLogSection(props: SectionProps) {
  const allowed = canReadAuditLog(props.me.role);
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  // The filters that are applied; typing in the boxes doesn't reload by itself.
  const [applied, setApplied] = useState({ entityType: "", dateFrom: "", dateTo: "" });
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loadedKey, setLoadedKey] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});

  const key = [applied.entityType, applied.dateFrom, applied.dateTo].join("|");
  const loading = allowed && loadedKey !== key;

  function buildPath(after: string | null): string {
    const params = ["limit=50"];
    if (applied.entityType.trim()) params.push("entity_type=" + encodeURIComponent(applied.entityType.trim()));
    if (applied.dateFrom) params.push("date_from=" + applied.dateFrom);
    if (applied.dateTo) params.push("date_to=" + applied.dateTo);
    if (after) params.push("cursor=" + encodeURIComponent(after));
    return "/audit-log?" + params.join("&");
  }

  useEffect(
    function () {
      if (!allowed) return;
      let cancelled = false;
      apiFetch<AuditPage>(buildPath(null), { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setRows(res.data);
          setCursor(res.pagination.next_cursor);
          setTotal(typeof res.pagination.total === "number" ? res.pagination.total : null);
          setError("");
          setLoadedKey(key);
        })
        .catch(function (err) {
          if (cancelled) return;
          setRows([]);
          setCursor(null);
          setError(err instanceof ApiError ? err.message : "Couldn't load the audit log.");
          setLoadedKey(key);
        });
      return function () {
        cancelled = true;
      };
    },
    // buildPath only reads the applied filters, which key already covers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allowed, key]
  );

  // Names for the people behind each change; the log itself only has user ids.
  useEffect(
    function () {
      if (!allowed) return;
      let cancelled = false;
      fetchAllPages<Employee>("/employees")
        .then(function (list) {
          if (cancelled) return;
          const map: Record<string, string> = {};
          for (const e of list) {
            if (e.user_id) map[e.user_id] = fullName(e);
          }
          setNames(map);
        })
        .catch(function () {
          // Without names the log still works; it just says "Someone".
        });
      return function () {
        cancelled = true;
      };
    },
    [allowed]
  );

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const res = await apiFetch<AuditPage>(buildPath(cursor), { method: "GET" });
      setRows(rows.concat(res.data));
      setCursor(res.pagination.next_cursor);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load more.");
    } finally {
      setLoadingMore(false);
    }
  }

  function actor(id: string | null): string {
    if (!id) return "The system";
    if (id === props.me.userId) return "You";
    return names[id] || "Someone";
  }

  if (!allowed) {
    return (
      <div>
        <h3 className="text-base font-semibold text-white">Audit log</h3>
        <p className="mt-4 text-sm text-gray-500">Only HR administrators and business executives can see the audit log.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-white">Audit log</h3>
      <p className="mt-1 text-sm text-gray-500">A record of who changed what, and when. Entries can&apos;t be edited or removed.</p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <div>
          <label className={SETTINGS_LABEL_CLASS}>Type of record</label>
          <input list="audit-entities" value={entityType} onChange={function (e) { setEntityType(e.target.value); }} placeholder="Any" className={SETTINGS_INPUT_CLASS} />
          <datalist id="audit-entities">
            {ENTITY_SUGGESTIONS.map(function (s) {
              return <option key={s} value={s} />;
            })}
          </datalist>
        </div>
        <div>
          <label className={SETTINGS_LABEL_CLASS}>From</label>
          <input type="date" value={dateFrom} onChange={function (e) { setDateFrom(e.target.value); }} className={SETTINGS_INPUT_CLASS} />
        </div>
        <div>
          <label className={SETTINGS_LABEL_CLASS}>To</label>
          <input type="date" value={dateTo} onChange={function (e) { setDateTo(e.target.value); }} className={SETTINGS_INPUT_CLASS} />
        </div>
        <button
          type="button"
          onClick={function () {
            setApplied({ entityType: entityType, dateFrom: dateFrom, dateTo: dateTo });
          }}
          className="rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-600"
        >
          Apply
        </button>
      </div>

      {loading ? <p className="mt-6 text-sm text-gray-400">Loading…</p> : null}
      {error ? <p className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}
      {!loading && !error && rows.length === 0 ? <p className="mt-6 text-sm text-gray-500">Nothing has been recorded for these filters.</p> : null}

      {!loading && rows.length > 0 ? (
        <>
          {total !== null ? <p className="mt-6 text-xs text-gray-500">{total} entries</p> : null}
          <ul className="mt-3 divide-y divide-white/5 rounded-xl border border-white/10">
            {rows.map(function (r) {
              const hasChanges = r.changes !== null && (r.changes.old !== undefined || r.changes.new !== undefined);
              return (
                <li key={r.id} className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-gray-200">
                      <span className="font-medium text-white">{actor(r.actor_user_id)}</span> · {titleCase(r.action)} · {titleCase(r.entity_type)}
                    </p>
                    <span className="text-xs text-gray-500">{formatDateTime(r.created_at)}</span>
                  </div>
                  {hasChanges ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-indigo-400">Show what changed</summary>
                      <pre className="mt-2 overflow-x-auto rounded-lg bg-[#0a0e1a] p-3 text-xs text-gray-300">{JSON.stringify(r.changes, null, 2)}</pre>
                    </details>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {cursor ? (
            <div className="mt-4 text-center">
              <button type="button" disabled={loadingMore} onClick={loadMore} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-300 hover:bg-white/5 disabled:opacity-50">
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

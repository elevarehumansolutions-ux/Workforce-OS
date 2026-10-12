"use client";

import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export type TrackingMode = "manual" | "task_count";

interface TaskProgress {
  kpi_id: string;
  period_start: string;
  period_end: string;
  completed_tasks: number;
  target_value: string | number | null;
  unit: string | null;
  score_percentage: string | number | null;
}

interface ProgressResult {
  key: string;
  progress: TaskProgress | null;
  error: string;
}

interface KpiTrackingControlProps {
  // null = the KPI hasn't been saved yet, so there is nothing to change on the server.
  kpiId: string | null;
  mode: TrackingMode;
  // Re-reads the progress when the saved target changes.
  targetValue: string;
  onChanged: (mode: TrackingMode) => void;
}

function formatDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function percentText(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return String(Math.round(n * 10) / 10);
}

export default function KpiTrackingControl(props: KpiTrackingControlProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ProgressResult | null>(null);

  const key = [props.kpiId, props.mode, props.targetValue].join("|");
  const wantsProgress = props.kpiId !== null && props.mode === "task_count";
  const loading = wantsProgress && (result === null || result.key !== key);

  useEffect(
    function () {
      if (!props.kpiId || props.mode !== "task_count") return;
      let cancelled = false;
      apiFetch<TaskProgress>("/kpis/" + props.kpiId + "/task-progress", { method: "GET" })
        .then(function (res) {
          if (cancelled) return;
          setResult({ key: key, progress: res, error: "" });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            progress: null,
            error: err instanceof ApiError ? err.message : "Couldn't load the live progress.",
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [props.kpiId, props.mode, key]
  );

  async function change(next: TrackingMode) {
    if (!props.kpiId || next === props.mode) return;
    setError("");
    setSaving(true);
    try {
      // Only the changed field is sent.
      await apiFetch("/kpis/" + props.kpiId, { method: "PATCH", body: { tracking_mode: next } });
      props.onChanged(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change how this KPI is measured.");
    } finally {
      setSaving(false);
    }
  }

  const progress = result && result.key === key ? result.progress : null;
  const progressError = result && result.key === key ? result.error : "";

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
      <label className="flex items-center gap-2 text-gray-400">
        How is progress measured?
        <select
          value={props.mode}
          disabled={props.kpiId === null || saving}
          onChange={function (e: ChangeEvent<HTMLSelectElement>) {
            change(e.target.value as TrackingMode);
          }}
          className="rounded-lg border border-white/10 bg-[#111726] px-2 py-1.5 text-xs text-white outline-none focus:border-indigo-500 disabled:opacity-50"
        >
          <option value="manual">I will enter the value</option>
          <option value="task_count">Count completed tasks linked to this KPI</option>
        </select>
      </label>

      {props.kpiId === null && <span className="text-gray-500">Save this department&apos;s KPIs first to change this.</span>}
      {error && <span className="text-red-300">{error}</span>}

      {wantsProgress && (
        <span className="text-gray-300">
          {loading ? (
            "Loading progress…"
          ) : progressError ? (
            <span className="text-red-300">{progressError}</span>
          ) : progress ? (
            <>
              <span className="font-medium text-white">
                {progress.completed_tasks}
                {progress.target_value !== null && progress.target_value !== undefined
                  ? " of " + progress.target_value + (progress.unit ? " " + progress.unit : "")
                  : " completed"}
              </span>
              {progress.score_percentage !== null && progress.score_percentage !== undefined ? (
                <span> ({percentText(progress.score_percentage)}%)</span>
              ) : (
                <span className="text-gray-500"> · No target set</span>
              )}
              <span className="text-gray-500">
                {" "}
                · {formatDay(progress.period_start)} - {formatDay(progress.period_end)}
              </span>
            </>
          ) : null}
        </span>
      )}
    </div>
  );
}

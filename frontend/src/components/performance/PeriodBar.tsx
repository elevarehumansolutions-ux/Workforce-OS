"use client";

import { CURRENT_QUARTER, nextQuarter, periodLabel, previousQuarter, startsInFuture } from "@/lib/performance";
import type { Period } from "@/lib/performance";

interface PeriodBarProps {
  // The dates the server actually used (from the last response), or null while loading.
  shownStart: string | null;
  shownEnd: string | null;
  // The period currently asked for; "current quarter" has null dates.
  asked: Period;
  isFinal: boolean;
  onChange: (period: Period) => void;
}

const arrowClass =
  "rounded-lg border border-white/10 px-3 py-1.5 text-sm text-gray-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40";

// Previous / next quarter arrows around the dates the server used, and a
// "Final" or "So far" marker: a closed quarter never changes again.
export default function PeriodBar(props: PeriodBarProps) {
  const ready = props.shownStart !== null && props.shownEnd !== null;
  const isCurrent = props.asked.start === null;

  function goPrevious() {
    if (props.shownStart !== null) props.onChange(previousQuarter(props.shownStart));
  }

  function goNext() {
    if (props.shownEnd !== null) props.onChange(nextQuarter(props.shownEnd));
  }

  const nextIsFuture = props.shownEnd !== null && startsInFuture(nextQuarter(props.shownEnd));

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" onClick={goPrevious} disabled={!ready} className={arrowClass} aria-label="Previous quarter">
        ◀
      </button>
      <span className="min-w-[14rem] text-center text-sm font-medium text-white">
        {ready ? periodLabel(props.shownStart as string, props.shownEnd as string) : "Loading…"}
      </span>
      <button
        type="button"
        onClick={goNext}
        disabled={!ready || nextIsFuture}
        className={arrowClass}
        aria-label="Next quarter"
      >
        ▶
      </button>
      {ready ? (
        <span
          className={
            "rounded-full px-2.5 py-1 text-xs font-medium " +
            (props.isFinal ? "bg-emerald-500/15 text-emerald-300" : "bg-indigo-500/15 text-indigo-300")
          }
        >
          {props.isFinal ? "Final" : "So far"}
        </span>
      ) : null}
      {!isCurrent ? (
        <button
          type="button"
          onClick={function () {
            props.onChange(CURRENT_QUARTER);
          }}
          className="text-xs text-indigo-300 hover:underline"
        >
          Back to the current quarter
        </button>
      ) : null}
    </div>
  );
}

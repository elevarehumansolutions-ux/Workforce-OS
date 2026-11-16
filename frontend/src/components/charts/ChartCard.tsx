"use client";

import { useState } from "react";
import type { ReactNode } from "react";

// The frame every chart sits in: a title, a plain sentence saying what it shows, the chart, and a
// "View as table" switch so the same numbers can be read without the picture (and by screen readers).
export default function ChartCard(props: {
  title: string;
  subtitle?: string;
  chart: ReactNode;
  table: ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-white">{props.title}</p>
          {props.subtitle ? <p className="mt-0.5 text-xs text-gray-500">{props.subtitle}</p> : null}
        </div>
        <button
          type="button"
          onClick={function () {
            setShowTable(!showTable);
          }}
          className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-gray-300 hover:bg-white/5"
        >
          {showTable ? "View as chart" : "View as table"}
        </button>
      </div>
      <div className="mt-4">{showTable ? props.table : props.chart}</div>
    </div>
  );
}

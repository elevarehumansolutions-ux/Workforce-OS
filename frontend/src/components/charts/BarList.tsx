"use client";

import Link from "next/link";

export interface BarRow {
  label: string;
  // null means "no data yet". It is never drawn as an empty bar, because that would read as 0.
  value: number | null;
  // Small grey text under the label, for example "5 tasks".
  note?: string;
  // When set, the label is a link (a person's card, for example).
  href?: string;
}

const BAR_COLOUR = "#3987e5";
const LINE_COLOUR = "rgba(255,255,255,0.18)";

// The same rows as a plain table, for the "View as table" switch.
export function BarTable(props: { rows: BarRow[]; valueHeading: string }) {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
          <th className="py-2 pr-4 font-medium">Name</th>
          <th className="py-2 font-medium">{props.valueHeading}</th>
        </tr>
      </thead>
      <tbody>
        {props.rows.map(function (row, i) {
          return (
            <tr key={i} className="border-b border-white/5">
              <td className="py-2 pr-4 text-white">{row.label}</td>
              <td className="py-2 text-gray-300">{row.value === null ? "No data yet" : String(row.value)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// One thin bar per row, all on the same scale so lengths can be compared. The scale runs to 100,
// or to the biggest value when a score goes above 100 (beating a target). A thin vertical line
// marks 100, the "target met" point.
export default function BarList(props: { rows: BarRow[]; valueSuffix?: string }) {
  let scaleMax = 100;
  for (const row of props.rows) {
    if (row.value !== null && row.value > scaleMax) {
      scaleMax = row.value;
    }
  }
  const targetLeft = (100 / scaleMax) * 100;
  const suffix = props.valueSuffix ? props.valueSuffix : "";

  return (
    <ul className="space-y-3">
      {props.rows.map(function (row, index) {
        const width = row.value === null ? 0 : Math.max(1, (row.value / scaleMax) * 100);
        const valueText = row.value === null ? "No data yet" : String(Math.round(row.value * 100) / 100) + suffix;

        return (
          <li key={index}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate">
                {row.href ? (
                  <Link href={row.href} className="text-white hover:text-indigo-300 hover:underline">
                    {row.label}
                  </Link>
                ) : (
                  <span className="text-white">{row.label}</span>
                )}
                {row.note ? <span className="ml-2 text-xs text-gray-500">{row.note}</span> : null}
              </span>
              <span className={row.value === null ? "text-xs text-gray-500" : "font-semibold text-gray-100"}>{valueText}</span>
            </div>
            <div
              className="relative mt-1 h-2 rounded-full bg-white/5"
              role="img"
              aria-label={row.label + ": " + valueText}
              title={row.label + ": " + valueText}
            >
              {row.value !== null ? (
                <div className="h-2 rounded-full" style={{ width: width + "%", backgroundColor: BAR_COLOUR }} />
              ) : null}
              <div className="absolute top-[-2px] h-3 w-px" style={{ left: targetLeft + "%", backgroundColor: LINE_COLOUR }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

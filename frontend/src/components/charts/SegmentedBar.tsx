"use client";

export interface Segment {
  label: string;
  value: number;
  colour: string;
}

// Status colours, kept for the meanings they carry. Each segment is also named in the legend
// underneath with its number, so colour is never the only way to tell them apart.
export const GOOD_COLOUR = "#0ca30c";
export const WARNING_COLOUR = "#fab219";
export const CRITICAL_COLOUR = "#d03b3b";
export const NEUTRAL_COLOUR = "#3987e5";

// The same parts as a plain table, for the "View as table" switch.
export function SegmentedTable(props: { segments: Segment[]; format: (value: number) => string }) {
  return (
    <table className="w-full text-left text-sm">
      <tbody>
        {props.segments.map(function (segment) {
          return (
            <tr key={segment.label} className="border-b border-white/5">
              <td className="py-2 pr-4 text-white">{segment.label}</td>
              <td className="py-2 text-gray-300">{props.format(segment.value)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// One bar split into parts that add up to a whole (tasks on time / late / not done, or money
// at risk / lost / secured). Parts with a value of 0 are left out of the bar but stay in the legend.
export default function SegmentedBar(props: {
  segments: Segment[];
  // Turns a number into the text shown in the legend, for example money or "3 tasks".
  format: (value: number) => string;
}) {
  let total = 0;
  for (const segment of props.segments) {
    total = total + segment.value;
  }

  return (
    <div>
      {total === 0 ? (
        <div className="h-3 rounded-full bg-white/5" />
      ) : (
        // The 2px gap between parts is the card colour showing through, so neighbours stay distinct.
        <div className="flex h-3 gap-[2px] overflow-hidden rounded-full bg-[#0d1220]" role="img" aria-label="Split of the total">
          {props.segments.map(function (segment) {
            if (segment.value <= 0) {
              return null;
            }
            return (
              <div
                key={segment.label}
                title={segment.label + ": " + props.format(segment.value)}
                style={{ width: (segment.value / total) * 100 + "%", backgroundColor: segment.colour }}
              />
            );
          })}
        </div>
      )}

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-400">
        {props.segments.map(function (segment) {
          return (
            <li key={segment.label} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: segment.colour }} />
              <span>
                {segment.label} <span className="font-semibold text-gray-200">{props.format(segment.value)}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

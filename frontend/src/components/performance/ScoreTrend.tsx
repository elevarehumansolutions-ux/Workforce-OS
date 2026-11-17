"use client";

import ChartCard from "@/components/charts/ChartCard";
import TrendLines from "@/components/charts/TrendLines";
import { useLoad } from "@/lib/useLoad";
import { previousQuarter } from "@/lib/performance";
import type { Period } from "@/lib/performance";

function quarterLabel(startIso: string): string {
  return new Date(startIso + "T00:00:00Z").toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

// The score for one quarter, or null when there is none (no data, or the quarter could not be
// loaded). A failed quarter shows as a gap in the line instead of breaking the whole chart.
async function scoreOrNull(loadScore: (period: Period) => Promise<string | null>, period: Period): Promise<number | null> {
  try {
    const score = await loadScore(period);
    return score === null ? null : Number(score);
  } catch {
    return null;
  }
}

// The shown quarter and the three before it, as one direction-coloured chart. The shown quarter's
// score is already on the screen, so only the three earlier quarters are requested.
// `loadScore` asks the server for one quarter and returns that screen's score.
export default function ScoreTrend(props: {
  // Used to reload when another person or department is opened.
  subjectKey: string;
  title: string;
  measureName: string;
  shownStart: string;
  shownScore: string | null;
  loadScore: (period: Period) => Promise<string | null>;
}) {
  const quarters: Period[] = [];
  let walking = previousQuarter(props.shownStart);
  for (let i = 0; i < 3; i++) {
    quarters.unshift(walking);
    walking = previousQuarter(walking.start as string);
  }

  const earlier = useLoad<(number | null)[]>(
    "trend|" + props.subjectKey + "|" + props.shownStart,
    function () {
      return Promise.all(
        quarters.map(function (q) {
          return scoreOrNull(props.loadScore, q);
        })
      );
    },
    "Could not load the earlier quarters."
  );

  const labels = quarters.map(function (q) {
    return quarterLabel(q.start as string);
  });
  labels.push(quarterLabel(props.shownStart));

  const shown = props.shownScore === null ? null : Number(props.shownScore);

  if (earlier.loading || earlier.data === null) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <p className="text-sm font-semibold text-white">{props.title}</p>
        <p className="mt-3 text-sm text-gray-400">{earlier.error ? earlier.error : "Loading earlier quarters…"}</p>
      </div>
    );
  }

  const values = earlier.data.concat([shown]);

  const table = (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
          <th className="py-2 pr-4 font-medium">Quarter</th>
          <th className="py-2 font-medium">{props.measureName}</th>
        </tr>
      </thead>
      <tbody>
        {labels.map(function (label, i) {
          return (
            <tr key={label} className="border-b border-white/5">
              <td className="py-2 pr-4 text-white">{label}</td>
              <td className="py-2 text-gray-300">{values[i] === null ? "No data yet" : String(Math.round((values[i] as number) * 100) / 100)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <ChartCard
      title={props.title}
      subtitle="Green when it rose, red when it fell. A quarter with no data leaves a gap."
      chart={<TrendLines labels={labels} values={values} measureName={props.measureName} />}
      table={table}
    />
  );
}

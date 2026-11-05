import Link from "next/link";
import { scoreClasses, scoreText } from "@/lib/performance";
import type { PersonPerformance } from "@/lib/performance";

// The body of a person's performance card: the overall score, how many KPIs it
// rests on, and one row per KPI. Used for "My performance" and for a colleague's card.
export default function PersonCard(props: { data: PersonPerformance }) {
  const data = props.data;
  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500">Overall score</p>
          <p className={"mt-1 text-5xl font-bold " + scoreClasses(data.overall_score)}>
            {data.overall_score === null ? "—" : scoreText(data.overall_score)}
          </p>
        </div>
        <div className="pb-1">
          {data.overall_score === null ? (
            <p className="text-sm text-gray-400">No data yet. {data.no_data_reason}</p>
          ) : (
            <p className="text-sm text-gray-400">
              Based on {data.kpis_counted} of {data.kpis_expected} KPIs
              {data.kpis_counted < data.kpis_expected ? " (the others have no tasks yet)" : ""}
            </p>
          )}
        </div>
      </div>

      {data.kpis.length > 0 ? (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-gray-500">
                <th className="py-2 pr-4 font-medium">KPI</th>
                <th className="py-2 pr-4 font-medium">Weight</th>
                <th className="py-2 pr-4 font-medium">Score</th>
                <th className="py-2 pr-4 font-medium">On time</th>
                <th className="py-2 pr-4 font-medium">Late</th>
                <th className="py-2 font-medium">Not done</th>
              </tr>
            </thead>
            <tbody>
              {data.kpis.map(function (line) {
                return (
                  <tr key={line.kpi_id} className="border-b border-white/5">
                    <td className="py-3 pr-4 text-white">{line.kpi_name}</td>
                    <td className="py-3 pr-4 text-gray-400">{scoreText(line.weight)}%</td>
                    <td className={"py-3 pr-4 font-semibold " + scoreClasses(line.score_percentage)}>
                      {scoreText(line.score_percentage)}
                    </td>
                    <td className="py-3 pr-4 text-gray-300">{line.tasks_on_time}</td>
                    <td className="py-3 pr-4 text-gray-300">{line.tasks_late}</td>
                    <td className="py-3 text-gray-300">{line.tasks_not_done}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <p className="mt-6 text-xs text-gray-500">
        Each task counts 100 if finished on time, 50 if late and 0 if never done; a KPI&apos;s score is the average of
        its tasks. To see the tasks behind a score, open{" "}
        <Link href="/tasks" className="text-indigo-300 hover:underline">
          Tasks
        </Link>
        .
      </p>
    </div>
  );
}

"use client";

import { DAY_NAMES, hourLabel } from "@/lib/workingHours";

interface Week {
  start_hour: number;
  end_hour: number;
  work_days: number[];
}

interface Props {
  value: Week;
  onChange: (week: Week) => void;
  disabled?: boolean;
}

const START_HOURS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
const END_HOURS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23];

const selectClass =
  "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500 disabled:opacity-60";

// The company's working week: from which hour to which hour, and on which days.
// The parent keeps the value; this only draws it and reports changes.
export default function WorkingHoursFields({ value, onChange, disabled }: Props) {
  function toggleDay(day: number) {
    let days = value.work_days.slice();
    if (days.indexOf(day) === -1) {
      days.push(day);
    } else {
      days = days.filter(function (d) { return d !== day; });
    }
    days.sort(function (a, b) { return a - b; });
    onChange({ ...value, work_days: days });
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <label className="block text-xs text-gray-400">
          Opens at
          <select
            value={value.start_hour}
            disabled={disabled}
            onChange={function (e) { onChange({ ...value, start_hour: Number(e.target.value) }); }}
            className={"mt-1 " + selectClass}
          >
            {START_HOURS.map(function (h) {
              return <option key={h} value={h}>{hourLabel(h)}</option>;
            })}
          </select>
        </label>
        <label className="block text-xs text-gray-400">
          Closes at
          <select
            value={value.end_hour}
            disabled={disabled}
            onChange={function (e) { onChange({ ...value, end_hour: Number(e.target.value) }); }}
            className={"mt-1 " + selectClass}
          >
            {END_HOURS.map(function (h) {
              return <option key={h} value={h}>{hourLabel(h)}</option>;
            })}
          </select>
        </label>
      </div>

      <div>
        <p className="mb-2 text-xs text-gray-400">Working days</p>
        <div className="flex flex-wrap gap-2">
          {DAY_NAMES.map(function (name, day) {
            const on = value.work_days.indexOf(day) !== -1;
            return (
              <button
                key={name}
                type="button"
                disabled={disabled}
                aria-pressed={on}
                onClick={function () { toggleDay(day); }}
                className={
                  "rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-60 " +
                  (on
                    ? "border-indigo-400/60 bg-indigo-500/20 text-indigo-200"
                    : "border-white/10 text-gray-400 hover:border-white/30")
                }
              >
                {name.slice(0, 3)}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

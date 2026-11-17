"use client";

import { useState } from "react";

// "2026-11-17T17:00", the text a datetime-local box holds (the person's own clock, no timezone).
function toInputValue(date: Date): string {
  const pad = function (n: number) {
    return String(n).padStart(2, "0");
  };
  return (
    date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" + pad(date.getHours()) + ":" + pad(date.getMinutes())
  );
}

// The same day at a given hour (24-hour clock), minutes 0.
function atHour(base: Date, hour: number): Date {
  const result = new Date(base);
  result.setHours(hour, 0, 0, 0);
  return result;
}

interface Pick {
  label: string;
  when: Date;
}

// Buttons under a deadline box. The calendar picks the date easily, but the time has to be typed
// digit by digit; these fill the whole box in one press. The box stays for any other time.
export default function DeadlineQuickPicks(props: { onPick: (value: string) => void }) {
  // "Now" is read once when the buttons appear (reading the clock while rendering is not allowed).
  const [openedAt] = useState(function () {
    return new Date();
  });

  const inOneHour = new Date(openedAt.getTime() + 60 * 60 * 1000);
  const todayFive = atHour(openedAt, 17);
  const tomorrowNine = atHour(new Date(openedAt.getTime() + 24 * 60 * 60 * 1000), 9);
  const inThreeDays = atHour(new Date(openedAt.getTime() + 3 * 24 * 60 * 60 * 1000), 17);

  // The next Monday after today, at 9.
  const daysToMonday = ((8 - openedAt.getDay()) % 7) || 7;
  const nextMonday = atHour(new Date(openedAt.getTime() + daysToMonday * 24 * 60 * 60 * 1000), 9);

  const picks: Pick[] = [{ label: "In 1 hour", when: inOneHour }];
  // "Today 5 pm" is only offered while it is still ahead.
  if (todayFive.getTime() > openedAt.getTime()) {
    picks.push({ label: "Today 5:00 pm", when: todayFive });
  }
  picks.push({ label: "Tomorrow 9:00 am", when: tomorrowNine });
  picks.push({ label: "In 3 days, 5:00 pm", when: inThreeDays });
  picks.push({ label: "Next Monday 9:00 am", when: nextMonday });

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {picks.map(function (pick) {
        return (
          <button
            key={pick.label}
            type="button"
            onClick={function () {
              props.onPick(toInputValue(pick.when));
            }}
            className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-gray-300 hover:bg-white/5 hover:text-white"
          >
            {pick.label}
          </button>
        );
      })}
    </div>
  );
}

"use client";

import { useState } from "react";

// The time as people say it: 5:30 PM. hour is 1 to 12, minute is 0 to 59, ampm is "AM" or "PM".
interface ClockTime {
  hour: number;
  minute: number;
  ampm: "AM" | "PM";
}

const DEFAULT_TIME: ClockTime = { hour: 9, minute: 0, ampm: "AM" };

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// "2026-11-18T17:30" -> the date "2026-11-18" and the time 5:30 PM.
function splitValue(value: string): { date: string; time: ClockTime } {
  const date = value.slice(0, 10);
  const hour24 = Number(value.slice(11, 13));
  const minute = Number(value.slice(14, 16));
  const ampm = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return { date: date, time: { hour: hour12, minute: minute, ampm: ampm } };
}

// The date and the time back into "2026-11-18T17:30", the text the rest of the screen already uses.
function joinValue(date: string, time: ClockTime): string {
  let hour24 = time.hour % 12;
  if (time.ampm === "PM") {
    hour24 = hour24 + 12;
  }
  return date + "T" + pad(hour24) + ":" + pad(time.minute);
}

const HOURS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const MINUTES: number[] = [];
for (let m = 0; m < 60; m++) {
  MINUTES.push(m);
}

const BOX = "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-white outline-none focus:border-indigo-500";
// The three time boxes are narrower than the date box, so they fit side by side on a phone too.
const TIME_BOX = BOX + " px-2";

// A deadline chosen like the date is: a calendar for the day, and drop-downs for the time.
// `value` and `onChange` use the same "YYYY-MM-DDTHH:mm" text a datetime-local box uses ("" = no
// deadline), so a screen can swap its old box for this one without other changes.
export default function DeadlineField(props: { value: string; onChange: (value: string) => void; id?: string }) {
  // The time chosen while no date is picked yet is remembered here, so picking the date later keeps it.
  const [waitingTime, setWaitingTime] = useState<ClockTime>(DEFAULT_TIME);

  const hasValue = props.value !== "";
  const parts = hasValue ? splitValue(props.value) : { date: "", time: waitingTime };

  function changeDate(newDate: string) {
    if (newDate === "") {
      props.onChange("");
      return;
    }
    props.onChange(joinValue(newDate, parts.time));
  }

  function changeTime(newTime: ClockTime) {
    if (hasValue) {
      props.onChange(joinValue(parts.date, newTime));
    } else {
      setWaitingTime(newTime);
    }
  }

  // Two lines: the date, then the time. The time line never wraps, so hour, minute and AM/PM
  // always stay together, however narrow the column is.
  return (
    <div className="space-y-2">
      <input
        id={props.id}
        type="date"
        value={parts.date}
        onChange={function (e) {
          changeDate(e.target.value);
        }}
        className={BOX + " w-full"}
      />
      <div className="flex flex-nowrap items-center gap-2">
        <select
          aria-label="Hour"
          value={parts.time.hour}
          onChange={function (e) {
            changeTime({ hour: Number(e.target.value), minute: parts.time.minute, ampm: parts.time.ampm });
          }}
          className={TIME_BOX}
        >
          {HOURS.map(function (h) {
            return (
              <option key={h} value={h}>
                {h}
              </option>
            );
          })}
        </select>
        <span className="text-gray-500">:</span>
        <select
          aria-label="Minute"
          value={parts.time.minute}
          onChange={function (e) {
            changeTime({ hour: parts.time.hour, minute: Number(e.target.value), ampm: parts.time.ampm });
          }}
          className={TIME_BOX}
        >
          {MINUTES.map(function (m) {
            return (
              <option key={m} value={m}>
                {pad(m)}
              </option>
            );
          })}
        </select>
        <select
          aria-label="AM or PM"
          value={parts.time.ampm}
          onChange={function (e) {
            changeTime({ hour: parts.time.hour, minute: parts.time.minute, ampm: e.target.value === "PM" ? "PM" : "AM" });
          }}
          className={TIME_BOX}
        >
          <option value="AM">AM</option>
          <option value="PM">PM</option>
        </select>
      </div>
    </div>
  );
}

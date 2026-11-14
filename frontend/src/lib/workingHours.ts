import { apiFetch } from "@/lib/api";

// The company's working week: used to count business hours in workflow deadlines.
// Hours are whole hours (0 to 23); days are numbered Monday 0 to Sunday 6.
export interface WorkingHours {
  start_hour: number;
  end_hour: number;
  work_days: number[];
  // How long one working day is: what "1 day" means for a workflow step.
  hours_per_day: number;
  // The company's timezone: the week above is in this clock.
  timezone: string;
}

export const DEFAULT_WORKING_HOURS: WorkingHours = {
  start_hour: 9,
  end_hour: 17,
  work_days: [0, 1, 2, 3, 4],
  hours_per_day: 8,
  timezone: "Africa/Lagos",
};

const WEEKDAY_NUMBER: Record<string, number> = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

// The weekday (Monday 0 to Sunday 6) and the hour (0 to 23) at `moment` on a clock in `timezone`.
// A timezone name the browser does not know falls back to the device's own clock.
function clockIn(timezone: string, moment: Date): { weekday: number; hour: number } {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone: timezone, weekday: "short", hour: "numeric", hourCycle: "h23" }).formatToParts(moment);
    let weekday = 0;
    let hour = 0;
    for (const part of parts) {
      if (part.type === "weekday") weekday = WEEKDAY_NUMBER[part.value] ?? 0;
      if (part.type === "hour") hour = Number(part.value);
    }
    return { weekday: weekday, hour: hour };
  } catch {
    return { weekday: (moment.getDay() + 6) % 7, hour: moment.getHours() };
  }
}

// Whether `moment` is a working day and inside the working hours, on the company's clock.
export function isWorkingTime(week: WorkingHours, moment: Date): boolean {
  const now = clockIn(week.timezone, moment);
  return week.work_days.indexOf(now.weekday) !== -1 && now.hour >= week.start_hour && now.hour < week.end_hour;
}

// The calendar day (YYYY-MM-DD) of `moment` on a clock in `timezone`; two moments on the same company day give the same text.
export function dayInTimezone(timezone: string, moment: Date): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(moment);
  } catch {
    return moment.toISOString().slice(0, 10);
  }
}

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// 8 -> "8 AM", 17 -> "5 PM", 0 -> "12 AM"
export function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "AM" : "PM";
  const twelveHour = hour % 12 === 0 ? 12 : hour % 12;
  return twelveHour + " " + suffix;
}

// "Mon to Fri, 8 AM to 5 PM" or, for days that are not one run, "Mon, Wed, Sat, 8 AM to 5 PM"
export function describeWorkingHours(week: { start_hour: number; end_hour: number; work_days: number[] }): string {
  const days = week.work_days.slice().sort(function (a, b) { return a - b; });
  let dayText = days.map(function (d) { return DAY_SHORT[d]; }).join(", ");
  const isOneRun = days.length > 2 && days[days.length - 1] - days[0] === days.length - 1;
  if (isOneRun) {
    dayText = DAY_SHORT[days[0]] + " to " + DAY_SHORT[days[days.length - 1]];
  }
  return dayText + ", " + hourLabel(week.start_hour) + " to " + hourLabel(week.end_hour);
}

// Why a week cannot be saved, in words, or "" when it is fine. The server checks the same rules.
export function workingHoursProblem(week: { start_hour: number; end_hour: number; work_days: number[] }): string {
  if (week.start_hour >= week.end_hour) return "The working day must start before it ends.";
  if (week.work_days.length === 0) return "Pick at least one working day.";
  return "";
}

export function fetchWorkingHours(): Promise<WorkingHours> {
  return apiFetch<WorkingHours>("/working-hours", { method: "GET" });
}

export function saveWorkingHours(week: { start_hour: number; end_hour: number; work_days: number[] }): Promise<WorkingHours> {
  return apiFetch<WorkingHours>("/working-hours", { method: "PUT", body: week });
}

import { apiFetch } from "@/lib/api";

// The company's working week: used to count business hours in workflow deadlines.
// Hours are whole hours (0 to 23); days are numbered Monday 0 to Sunday 6.
export interface WorkingHours {
  start_hour: number;
  end_hour: number;
  work_days: number[];
  // How long one working day is: what "1 day" means for a workflow step.
  hours_per_day: number;
}

export const DEFAULT_WORKING_HOURS: WorkingHours = {
  start_hour: 9,
  end_hour: 17,
  work_days: [0, 1, 2, 3, 4],
  hours_per_day: 8,
};

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

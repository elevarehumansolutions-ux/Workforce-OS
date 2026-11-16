"use client";

import { useState } from "react";

type Unit = "minutes" | "hours" | "days";

const UNIT_MINUTES: Record<Unit, number> = { minutes: 1, hours: 60, days: 1440 };

// Quick choices, in minutes.
const PRESETS: { label: string; minutes: number }[] = [
  { label: "30 minutes", minutes: 30 },
  { label: "1 hour", minutes: 60 },
  { label: "4 hours", minutes: 240 },
  { label: "1 day", minutes: 1440 },
];

// 120 minutes -> { amount: "2", unit: "hours" }: the largest unit that divides the time evenly.
function splitMinutes(minutes: number): { amount: string; unit: Unit } {
  if (minutes % 1440 === 0) return { amount: String(minutes / 1440), unit: "days" };
  if (minutes % 60 === 0) return { amount: String(minutes / 60), unit: "hours" };
  return { amount: String(minutes), unit: "minutes" };
}

interface ExtensionPickerProps {
  // Where the choice starts (for example what the person asked for).
  defaultMinutes: number;
  // Called with the chosen number of minutes, or 0 when the amount is empty or not a whole number above zero.
  onChange: (minutes: number) => void;
  disabled?: boolean;
}

// How much extra time a reviewer gives: quick choices, or any amount in minutes, hours or days.
export default function ExtensionPicker({ defaultMinutes, onChange, disabled }: ExtensionPickerProps) {
  const start = splitMinutes(defaultMinutes);
  const [amount, setAmount] = useState(start.amount);
  const [unit, setUnit] = useState<Unit>(start.unit);

  function report(nextAmount: string, nextUnit: Unit) {
    const trimmed = nextAmount.trim();
    if (!/^[0-9]+$/.test(trimmed) || Number(trimmed) < 1) {
      onChange(0);
      return;
    }
    onChange(Number(trimmed) * UNIT_MINUTES[nextUnit]);
  }

  const fieldClass =
    "rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500 disabled:opacity-50";

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map(function (p) {
          return (
            <button
              key={p.label}
              type="button"
              disabled={disabled}
              onClick={function () {
                const parts = splitMinutes(p.minutes);
                setAmount(parts.amount);
                setUnit(parts.unit);
                onChange(p.minutes);
              }}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/5 disabled:opacity-50"
            >
              {p.label}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <input
          type="number"
          min={1}
          step={1}
          value={amount}
          disabled={disabled}
          aria-label="Extra time"
          onChange={function (e) {
            setAmount(e.target.value);
            report(e.target.value, unit);
          }}
          className={fieldClass + " w-28"}
        />
        <select
          value={unit}
          disabled={disabled}
          aria-label="Unit of time"
          onChange={function (e) {
            const next = e.target.value as Unit;
            setUnit(next);
            report(amount, next);
          }}
          className={fieldClass}
        >
          <option value="minutes">Minutes</option>
          <option value="hours">Hours</option>
          <option value="days">Days</option>
        </select>
      </div>
    </div>
  );
}

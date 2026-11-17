"use client";

import { useState } from "react";

const UP_COLOUR = "#0ca30c";
const DOWN_COLOUR = "#d03b3b";
const FLAT_COLOUR = "#9ca3af";

const WIDTH = 600;
const HEIGHT = 220;
const LEFT = 36;
const RIGHT = 16;
const TOP = 12;
const BOTTOM = 28;

function colourOfChange(change: number): string {
  if (change > 0) {
    return UP_COLOUR;
  }
  if (change < 0) {
    return DOWN_COLOUR;
  }
  return FLAT_COLOUR;
}

function arrowOfChange(change: number): string {
  if (change > 0) {
    return "▲";
  }
  if (change < 0) {
    return "▼";
  }
  return "■";
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

// The change between a quarter and the closest earlier quarter that has data. null when there is
// nothing to compare with (the first quarter, or no earlier data).
function changeAt(values: (number | null)[], index: number): number | null {
  const now = values[index];
  if (now === null) {
    return null;
  }
  for (let i = index - 1; i >= 0; i--) {
    const before = values[i];
    if (before !== null) {
      return now - before;
    }
  }
  return null;
}

// ONE measure over time, coloured by direction like a market chart: each stretch of line is green
// when the score rose into that quarter and red when it fell. Colour is never the only signal:
// the headline above the chart and the tooltip show an arrow, the words and the change in points.
// A quarter with no data breaks the line (never a drop to 0).
export default function TrendLines(props: { labels: string[]; values: (number | null)[]; measureName: string }) {
  const [hovered, setHovered] = useState<number | null>(null);

  let top = 100;
  for (const v of props.values) {
    if (v !== null && v > top) {
      top = Math.ceil(v / 10) * 10;
    }
  }

  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const count = props.labels.length;

  function xOf(index: number): number {
    if (count === 1) {
      return LEFT + plotWidth / 2;
    }
    return LEFT + (index / (count - 1)) * plotWidth;
  }

  function yOf(value: number): number {
    return TOP + plotHeight - (value / top) * plotHeight;
  }

  // The newest quarter with data, and how it moved from the one before.
  let latestIndex = -1;
  for (let i = 0; i < props.values.length; i++) {
    if (props.values[i] !== null) {
      latestIndex = i;
    }
  }
  const latestChange = latestIndex >= 0 ? changeAt(props.values, latestIndex) : null;

  // Each piece of line joins a quarter to the closest earlier quarter that has data.
  // It is drawn as its own segment so it can have its own colour.
  const segments: { x1: number; y1: number; x2: number; y2: number; colour: string }[] = [];
  for (let i = 1; i < props.values.length; i++) {
    const now = props.values[i];
    if (now === null) {
      continue;
    }
    // Only join to the quarter directly before: a missing quarter in between stays a visible gap.
    const before = props.values[i - 1];
    if (before === null) {
      continue;
    }
    segments.push({ x1: xOf(i - 1), y1: yOf(before), x2: xOf(i), y2: yOf(now), colour: colourOfChange(now - before) });
  }

  const gridValues = [0, top / 2, top];

  return (
    <div>
      {latestIndex >= 0 ? (
        <p className="mb-2 text-sm text-gray-300">
          <span className="text-2xl font-bold text-white">{round2(props.values[latestIndex] as number)}</span>{" "}
          {latestChange === null ? (
            <span className="text-gray-500">first quarter with data, nothing to compare with yet</span>
          ) : (
            <span className="font-semibold" style={{ color: colourOfChange(latestChange) }}>
              {arrowOfChange(latestChange)} {latestChange > 0 ? "Rising" : latestChange < 0 ? "Falling" : "Flat"}{" "}
              {latestChange > 0 ? "+" : ""}
              {round2(latestChange)} points
            </span>
          )}
          {latestChange === null ? (
            <span className="ml-2 text-xs text-gray-500">({props.labels[latestIndex]})</span>
          ) : (
            <span className="ml-2 text-xs text-gray-500">vs the earlier quarter, now {props.labels[latestIndex]}</span>
          )}
        </p>
      ) : (
        <p className="mb-2 text-sm text-gray-500">No data yet in these quarters.</p>
      )}

      <div className="relative">
        <svg viewBox={"0 0 " + WIDTH + " " + HEIGHT} className="w-full" role="img" aria-label={props.measureName + " over the last quarters"}>
          {gridValues.map(function (g) {
            return (
              <g key={g}>
                <line x1={LEFT} x2={WIDTH - RIGHT} y1={yOf(g)} y2={yOf(g)} stroke="rgba(255,255,255,0.1)" strokeWidth={1} />
                <text x={LEFT - 6} y={yOf(g) + 4} textAnchor="end" fontSize={11} fill="#6b7280">
                  {g}
                </text>
              </g>
            );
          })}

          {props.labels.map(function (label, i) {
            return (
              <text key={label + i} x={xOf(i)} y={HEIGHT - 8} textAnchor="middle" fontSize={11} fill="#9ca3af">
                {label}
              </text>
            );
          })}

          {hovered !== null ? (
            <line x1={xOf(hovered)} x2={xOf(hovered)} y1={TOP} y2={TOP + plotHeight} stroke="rgba(255,255,255,0.25)" strokeWidth={1} />
          ) : null}

          {segments.map(function (s, i) {
            return <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={s.colour} strokeWidth={2.5} strokeLinecap="round" />;
          })}

          {props.values.map(function (v, i) {
            if (v === null) {
              return null;
            }
            const change = changeAt(props.values, i);
            const colour = change === null ? FLAT_COLOUR : colourOfChange(change);
            // The ring in the card colour keeps a dot readable where it meets a line.
            return <circle key={i} cx={xOf(i)} cy={yOf(v)} r={4.5} fill={colour} stroke="#0d1220" strokeWidth={2} />;
          })}

          {/* One wide invisible strip per quarter: a bigger target than the dots for hovering. */}
          {props.labels.map(function (label, i) {
            return (
              <rect
                key={"hit" + i}
                x={xOf(i) - plotWidth / count / 2}
                y={TOP}
                width={plotWidth / count}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={function () {
                  setHovered(i);
                }}
                onMouseLeave={function () {
                  setHovered(null);
                }}
              />
            );
          })}
        </svg>

        {hovered !== null ? (
          <div className="pointer-events-none absolute right-2 top-2 rounded-lg border border-white/10 bg-[#0a0e1a] px-3 py-2 text-xs shadow-lg">
            <p className="font-semibold text-white">{props.labels[hovered]}</p>
            {props.values[hovered] === null ? (
              <p className="mt-1 text-gray-400">No data yet</p>
            ) : (
              <p className="mt-1 text-gray-300">
                {props.measureName}: {round2(props.values[hovered] as number)}
                {changeAt(props.values, hovered) !== null ? (
                  <span style={{ color: colourOfChange(changeAt(props.values, hovered) as number) }}>
                    {" "}
                    {arrowOfChange(changeAt(props.values, hovered) as number)} {round2(changeAt(props.values, hovered) as number)}
                  </span>
                ) : null}
              </p>
            )}
          </div>
        ) : null}
      </div>

      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-400">
        <li className="flex items-center gap-1.5">
          <span style={{ color: UP_COLOUR }}>▲</span> Rising
        </li>
        <li className="flex items-center gap-1.5">
          <span style={{ color: DOWN_COLOUR }}>▼</span> Falling
        </li>
        <li className="flex items-center gap-1.5">
          <span style={{ color: FLAT_COLOUR }}>■</span> Flat, or first quarter
        </li>
      </ul>
    </div>
  );
}

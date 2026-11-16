"use client";

import { useState } from "react";

export interface TrendSeries {
  name: string;
  colour: string;
  // One value per label. null = no data that quarter: the line breaks there instead of dropping to 0.
  values: (number | null)[];
}

const WIDTH = 600;
const HEIGHT = 220;
const LEFT = 36;
const RIGHT = 16;
const TOP = 12;
const BOTTOM = 28;

// Lines over time on ONE axis (never two). Two series maximum in practice here: the headline score
// and punctuality are different questions, so they are two lines, not a blended one.
export default function TrendLines(props: { labels: string[]; series: TrendSeries[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  let top = 100;
  for (const s of props.series) {
    for (const v of s.values) {
      if (v !== null && v > top) {
        top = Math.ceil(v / 10) * 10;
      }
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

  // A line is drawn in pieces, one per run of quarters that have data, so a gap stays a gap.
  function pathsOf(values: (number | null)[]): string[] {
    const pieces: string[] = [];
    let current = "";
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (v === null) {
        if (current !== "") {
          pieces.push(current);
          current = "";
        }
      } else {
        current = current + (current === "" ? "M" : "L") + xOf(i) + " " + yOf(v) + " ";
      }
    }
    if (current !== "") {
      pieces.push(current);
    }
    return pieces;
  }

  const gridValues = [0, top / 2, top];

  return (
    <div>
      <div className="relative">
        <svg viewBox={"0 0 " + WIDTH + " " + HEIGHT} className="w-full" role="img" aria-label="Scores over the last quarters">
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

          {props.series.map(function (s) {
            return (
              <g key={s.name}>
                {pathsOf(s.values).map(function (d, i) {
                  return <path key={i} d={d} fill="none" stroke={s.colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />;
                })}
                {s.values.map(function (v, i) {
                  if (v === null) {
                    return null;
                  }
                  // The 2px ring in the card colour keeps a dot readable where two lines meet.
                  return <circle key={i} cx={xOf(i)} cy={yOf(v)} r={4} fill={s.colour} stroke="#0d1220" strokeWidth={2} />;
                })}
              </g>
            );
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
            {props.series.map(function (s) {
              const v = s.values[hovered];
              return (
                <p key={s.name} className="mt-1 flex items-center gap-1.5 text-gray-300">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: s.colour }} />
                  {s.name}: {v === null ? "No data yet" : Math.round(v * 100) / 100}
                </p>
              );
            })}
          </div>
        ) : null}
      </div>

      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-400">
        {props.series.map(function (s) {
          return (
            <li key={s.name} className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4" style={{ backgroundColor: s.colour }} />
              {s.name}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

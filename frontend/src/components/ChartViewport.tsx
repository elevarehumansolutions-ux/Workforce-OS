"use client";

import { useRef, useState } from "react";
import type { ReactNode } from "react";

// The window an organization chart is drawn in. A chart can be wider and taller than the
// screen, so this gives it: a tall area (about two thirds of the screen), zoom in and out,
// "Fit" (scale it to the width of the window), full screen, and dragging to move around it
// like a map. A click on a box or button still works: dragging only starts on empty space.
// The chart itself (the nested lists the .org-tree styles draw) is passed in as children.
export default function ChartViewport(props: { full: boolean; onToggleFull: () => void; children: ReactNode }) {
  const [zoom, setZoom] = useState(1);
  const viewport = useRef<HTMLDivElement | null>(null);
  const content = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  function changeZoom(delta: number) {
    setZoom(function (z) {
      return Math.max(0.3, Math.min(1.6, Math.round((z + delta) * 100) / 100));
    });
  }

  // Scale the chart down (never up) until its width matches the visible width.
  function fit() {
    const box = viewport.current;
    const chart = content.current;
    if (!box || !chart) return;
    const naturalWidth = chart.scrollWidth / zoom;
    if (naturalWidth <= 0) return;
    setZoom(Math.max(0.3, Math.min(1, (box.clientWidth - 16) / naturalWidth)));
  }

  const button = "rounded-md border border-white/10 px-2.5 py-1.5 text-xs text-gray-300 hover:bg-white/5";

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1">
        <button type="button" onClick={function () { changeZoom(-0.1); }} className={button} aria-label="Zoom out">−</button>
        <span className="w-12 text-center text-xs text-gray-400">{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={function () { changeZoom(0.1); }} className={button} aria-label="Zoom in">+</button>
        <button type="button" onClick={fit} className={button}>Fit</button>
        <button type="button" onClick={props.onToggleFull} className={button}>
          {props.full ? "Exit full screen" : "Full screen"}
        </button>
        <span className="ml-2 text-xs text-gray-600">Drag to move around</span>
      </div>
      <div
        ref={viewport}
        className={
          "cursor-grab overflow-auto rounded-lg border border-white/5 [color-scheme:dark] active:cursor-grabbing " +
          (props.full ? "h-[calc(100vh-12rem)]" : "h-[62vh]")
        }
        onMouseDown={function (e) {
          const box = viewport.current;
          if (!box || (e.target as HTMLElement).closest("button, input")) return;
          drag.current = { x: e.clientX, y: e.clientY, left: box.scrollLeft, top: box.scrollTop };
        }}
        onMouseMove={function (e) {
          const box = viewport.current;
          if (!box || !drag.current) return;
          box.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
          box.scrollTop = drag.current.top - (e.clientY - drag.current.y);
        }}
        onMouseUp={function () { drag.current = null; }}
        onMouseLeave={function () { drag.current = null; }}
      >
        <div ref={content} className="org-tree mx-auto w-max min-w-full p-4" style={{ zoom: zoom }}>
          <ul>{props.children}</ul>
        </div>
      </div>
    </div>
  );
}

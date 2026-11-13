"use client";

import { useEffect } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

// A window over the page. It closes with the X, a click on the dark area, or the Esc key.
export default function Modal({ title, onClose, children }: ModalProps) {
  useEffect(function () {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return function () {
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      {/* Clicks inside the window must not reach the dark area behind it, or they would close it. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={function (e) { e.stopPropagation(); }}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-indigo-400/30 bg-[#0a0e1a] p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg px-2 py-1 text-gray-400 hover:bg-white/5 hover:text-white"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

"use client";

import { useEffect } from "react";

// Registers the service worker that makes the app installable. It only runs
// in the production build, so development never serves stale cached files.
export default function PwaRegister() {
  useEffect(function () {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(function () {
      // The app works the same without it; it just can't be installed.
    });
  }, []);
  return null;
}

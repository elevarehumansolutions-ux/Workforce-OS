"use client";

import { useEffect } from "react";

// Registers the service worker that makes the app installable. It only runs
// in the production build. In development it does the opposite: it removes any
// service worker and cache left behind by an earlier production run, because
// development files keep the same names between edits and a cached copy would
// keep serving old code.
export default function PwaRegister() {
  useEffect(function () {
    if (!("serviceWorker" in navigator)) return;

    if (process.env.NODE_ENV !== "production") {
      navigator.serviceWorker
        .getRegistrations()
        .then(function (registrations) {
          let removed = false;
          for (const registration of registrations) {
            registration.unregister();
            removed = true;
          }
          if (typeof caches !== "undefined") {
            caches.keys().then(function (keys) {
              for (const key of keys) {
                if (key.indexOf("wos-") === 0) {
                  caches.delete(key);
                  removed = true;
                }
              }
            });
          }
          // One reload so the page runs fresh code instead of the cached copy.
          if (removed && navigator.serviceWorker.controller) window.location.reload();
        })
        .catch(function () {
          // Nothing to clean up.
        });
      return;
    }

    navigator.serviceWorker.register("/sw.js").catch(function () {
      // The app works the same without it; it just can't be installed.
    });
  }, []);
  return null;
}

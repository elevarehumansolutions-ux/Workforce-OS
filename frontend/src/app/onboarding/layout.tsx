"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { rememberOnboardingStep } from "@/lib/onboarding";

interface MeResponse {
  user: { id: string };
}

// Wraps every onboarding page. It notes which step the person is on, so that
// signing in later sends them back to it.
export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  useEffect(
    function () {
      if (!pathname || pathname.indexOf("/onboarding/") !== 0) return;
      let cancelled = false;
      apiFetch<MeResponse>("/auth/me", { method: "GET" })
        .then(function (me) {
          if (cancelled) return;
          rememberOnboardingStep(me.user.id, pathname);
        })
        .catch(function () {
          // Not signed in yet or offline: nothing to remember.
        });
      return function () {
        cancelled = true;
      };
    },
    [pathname]
  );

  return <>{children}</>;
}

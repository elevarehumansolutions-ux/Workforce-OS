import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, restoreSession } from "@/lib/api";
import { resumePath } from "@/lib/onboarding";

// For pages that only make sense when nobody is signed in (sign in, sign up). If the
// person already has a session (a valid refresh cookie), send them on to where they were
// going: the onboarding step they stopped at, or the dashboard. Returns true while it is
// still checking, so the page can show a short "checking" message instead of flashing the
// form at someone who is about to be redirected.
export function useRedirectIfSignedIn(): boolean {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(
    function () {
      let cancelled = false;
      async function check() {
        const signedIn = await restoreSession();
        if (cancelled) return;
        if (!signedIn) {
          setChecking(false);
          return;
        }
        try {
          const me = await apiFetch<{ user: { id: string } }>("/auth/me", { method: "GET" });
          if (cancelled) return;
          router.replace(resumePath(me.user.id) || "/dashboard");
        } catch {
          // The session could not be confirmed: show the form rather than a dead end.
          if (!cancelled) setChecking(false);
        }
      }
      check();
      return function () {
        cancelled = true;
      };
    },
    [router]
  );

  return checking;
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// The executive overview was a sample-data mock-up. The real one is the
// company performance screen; this keeps old links and bookmarks working.
export default function ExecutiveOverviewRedirectPage() {
  const router = useRouter();

  useEffect(
    function () {
      router.replace("/performance/company");
    },
    [router]
  );

  return null;
}

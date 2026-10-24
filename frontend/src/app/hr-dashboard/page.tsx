"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// The HR view now lives on the main dashboard, which shows the right
// sections for each role. This keeps old links and bookmarks working.
export default function HrDashboardRedirectPage() {
  const router = useRouter();

  useEffect(
    function () {
      router.replace("/dashboard");
    },
    [router]
  );

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#05070f] text-white">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
    </div>
  );
}

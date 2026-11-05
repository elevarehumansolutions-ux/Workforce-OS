"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// This was a sample-data mock-up of one department. The real department
// view works for every department; this keeps old links working.
export default function DepartmentDrilldownRedirectPage() {
  const router = useRouter();

  useEffect(
    function () {
      router.replace("/performance/department");
    },
    [router]
  );

  return null;
}

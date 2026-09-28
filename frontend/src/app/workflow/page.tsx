"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function WorkflowRedirectPage() {
  const router = useRouter();

  useEffect(function () {
    router.replace("/workflow/templates");
  }, [router]);

  return null;
}

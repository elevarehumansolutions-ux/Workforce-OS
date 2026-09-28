"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TasksRedirectPage() {
  const router = useRouter();

  useEffect(function () {
    router.replace("/tasks/assign-task");
  }, [router]);

  return null;
}

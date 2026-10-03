"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";

const PENDING_EMAIL_KEY = "elevare_pending_verification_email";
const POLL_INTERVAL_MS = 5000;

interface MeResponse {
  user: {
    id: string;
    email: string;
    full_name: string;
    account_status: string;
  };
  memberships: unknown[];
}

type ConfirmState = "verifying" | "success" | "error";

export default function VerifyEmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [confirmState, setConfirmState] = useState<ConfirmState>("verifying");
  const [confirmError, setConfirmError] = useState("");

  const [email] = useState<string>(function () {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(PENDING_EMAIL_KEY) || "";
  });
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Mode 1: a token in the URL means this tab was opened from the emailed link.
  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    async function confirm() {
      try {
        await apiFetch("/auth/verify-email", {
          method: "POST",
          body: { token },
          skipAuth: true,
        });
        if (cancelled) return;
        setConfirmState("success");
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(PENDING_EMAIL_KEY);
        }
        setTimeout(function () {
          if (cancelled) return;
          router.push(getAccessToken() ? "/onboarding/business-dna" : "/login?verified=1");
        }, 1800);
      } catch (err) {
        if (cancelled) return;
        setConfirmState("error");
        setConfirmError(
          err instanceof ApiError ? err.message : "This verification link is invalid or has expired."
        );
      }
    }
    confirm();
    return function () {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Mode 2: no token — poll GET /me so this tab notices verification the
  // moment the person clicks the link in another tab, no manual refresh needed.
  async function checkStatus(): Promise<boolean> {
    try {
      const me = await apiFetch<MeResponse>("/me", { method: "GET" });
      if (me.user.account_status === "verified") {
        if (pollRef.current) clearInterval(pollRef.current);
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(PENDING_EMAIL_KEY);
        }
        router.push("/onboarding/business-dna");
        return true;
      }
    } catch {
      // No session yet, or the request failed.
    }
    return false;
  }

  useEffect(() => {
    if (token) return;
    if (!getAccessToken()) return;
    pollRef.current = setInterval(checkStatus, POLL_INTERVAL_MS);
    return function () {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleManualCheck() {
    setChecking(true);
    const verified = await checkStatus();
    setChecking(false);
    if (!verified) {
      setResendMessage("Still not verified — check your inbox (and spam folder) for the link.");
    }
  }

  async function handleResend() {
    setResending(true);
    setResendMessage("");
    try {
      await apiFetch("/auth/resend-verification", {
        method: "POST",
        body: { email },
        skipAuth: true,
      });
      setResendMessage("Verification email sent. Check your inbox.");
    } catch (err) {
      setResendMessage(
        err instanceof ApiError ? err.message : "Couldn't resend right now. Please try again shortly."
      );
    } finally {
      setResending(false);
    }
  }

  const shell = function (children: React.ReactNode) {
    return (
      <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#05070f] px-6 text-white">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 78% 42%, rgba(99,102,241,0.16), transparent 55%), radial-gradient(circle at 15% 80%, rgba(99,102,241,0.06), transparent 50%)",
          }}
        />
        <div className="relative z-10 w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 text-center shadow-2xl backdrop-blur-sm">
          {children}
        </div>
      </div>
    );
  };

  if (token) {
    if (confirmState === "verifying") {
      return shell(
        <>
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-indigo-500/15">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          </div>
          <h1 className="mt-6 text-xl font-bold">Verifying your email…</h1>
          <p className="mt-2 text-sm text-gray-400">This will just take a moment.</p>
        </>
      );
    }
    if (confirmState === "success") {
      return shell(
        <>
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M5 13l4 4L19 7" stroke="#34d399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="mt-6 text-xl font-bold">Email verified</h1>
          <p className="mt-2 text-sm text-gray-400">Taking you to setup…</p>
        </>
      );
    }
    return shell(
      <>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/15">
          <span className="text-2xl text-red-400">!</span>
        </div>
        <h1 className="mt-6 text-xl font-bold">Verification failed</h1>
        <p className="mt-2 text-sm text-gray-400">{confirmError}</p>
        <button
          onClick={function () {
            router.push("/verify-email");
          }}
          className="mt-6 w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
        >
          Request a new link
        </button>
      </>
    );
  }

  return shell(
    <>
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-indigo-500/15">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M4 6h16v12H4z" stroke="#818cf8" strokeWidth="1.5" />
          <path d="M4 7l8 6 8-6" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <h1 className="mt-6 text-xl font-bold">Check your email</h1>
      <p className="mt-2 text-sm text-gray-400">
        We sent a verification link to{" "}
        <span className="font-medium text-gray-200">{email || "your email address"}</span>. Click it to
        activate your account — this page will move on automatically once it&apos;s confirmed.
      </p>

      {resendMessage ? (
        <div className="mt-5 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-xs text-gray-300">
          {resendMessage}
        </div>
      ) : null}

      <button
        onClick={handleManualCheck}
        disabled={checking}
        className="mt-6 w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {checking ? "Checking…" : "I've verified — Continue"}
      </button>

      <button
        onClick={handleResend}
        disabled={resending || !email}
        className="mt-3 w-full rounded-lg border border-white/10 bg-transparent py-3 text-sm font-semibold text-gray-300 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {resending ? "Resending…" : "Resend verification email"}
      </button>

      <p className="mt-6 text-center text-xs text-gray-500">
        Wrong account?{" "}
        <a href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">
          Sign in with a different one
        </a>
      </p>
    </>
  );
}

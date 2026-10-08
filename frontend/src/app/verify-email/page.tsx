"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
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

// The generic, account-existence-revealing-nothing message the backend's
// POST /auth/resend-verification always answers with (200, whether or not
// that address is actually registered) — shown verbatim so the UI doesn't
// leak anything the API deliberately doesn't.
const RESEND_GENERIC_MESSAGE = "If that address is registered, we've sent a new verification link.";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [confirmState, setConfirmState] = useState<ConfirmState>("verifying");
  const [confirmMessage, setConfirmMessage] = useState("");
  // The server's machine-readable error code for the failed confirm, so the
  // UI can offer the right next step (resend vs. log in) instead of one
  // generic "try again" for every failure mode.
  const [confirmCode, setConfirmCode] = useState("");

  // Starts empty on both the server render and the client's first render so
  // they match exactly — reading localStorage here would make the server
  // (no window) and the client (has the pending email saved by signup)
  // disagree on what to show, which crashes with a hydration error. It's
  // filled in right after mount instead, in the effect below.
  const [email, setEmail] = useState<string>("");
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(function () {
    // Runs synchronously on mount (not deferred into a promise) so the
    // email appears on the very next paint rather than flickering in late.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEmail(window.localStorage.getItem(PENDING_EMAIL_KEY) || "");
  }, []);

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
        if (err instanceof ApiError) {
          // The backend's `message` is already written to be shown as-is
          // (see backend/app/core/exceptions.py) — TOKEN_INVALID, TOKEN_
          // ALREADY_USED and VERIFICATION_TOKEN_EXPIRED each carry their
          // own accurate explanation, so there's no reason to paraphrase it.
          setConfirmMessage(err.message);
          setConfirmCode(err.code);
        } else {
          // No response at all (offline, DNS failure, server unreachable)
          // is a different situation from the server answering with an
          // error — don't claim the link itself is the problem.
          setConfirmMessage("Couldn't reach the server. Check your connection and try again.");
          setConfirmCode("");
        }
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
      const me = await apiFetch<MeResponse>("/auth/me", { method: "GET" });
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
    if (!email) return;
    setResending(true);
    setResendMessage("");
    try {
      await apiFetch("/auth/resend-verification", {
        method: "POST",
        body: { email },
        skipAuth: true,
      });
      // Always the same line, success or "no such account" — the backend
      // itself never distinguishes the two (200 either way), so echoing an
      // ApiError's message here would be the only way this page could leak
      // whether an email is registered, which is exactly what the generic
      // response is for.
      setResendMessage(RESEND_GENERIC_MESSAGE);
    } catch (err) {
      // A real failure to even make the request (network down, rate
      // limited) is worth surfacing distinctly — it's not the backend's
      // deliberately-vague "maybe sent" response.
      if (err instanceof ApiError) {
        setResendMessage(err.message);
      } else {
        setResendMessage("Couldn't reach the server. Check your connection and try again.");
      }
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

    // confirmState === "error" — the specific next step depends on *why*
    // it failed, not just that it did.
    const canResend = confirmCode === "TOKEN_INVALID" || confirmCode === "VERIFICATION_TOKEN_EXPIRED";
    const alreadyUsed = confirmCode === "TOKEN_ALREADY_USED";

    return shell(
      <>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/15">
          <span className="text-2xl text-red-400">!</span>
        </div>
        <h1 className="mt-6 text-xl font-bold">{alreadyUsed ? "Already verified" : "Verification failed"}</h1>
        <p className="mt-2 text-sm text-gray-400">{confirmMessage}</p>

        {alreadyUsed ? (
          <button
            onClick={function () {
              router.push("/login");
            }}
            className="mt-6 w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
          >
            Log in
          </button>
        ) : canResend ? (
          <>
            {!email ? (
              <input
                type="email"
                value={email}
                onChange={function (e) {
                  setEmail(e.target.value);
                }}
                placeholder="Your email address"
                className="mt-4 w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            ) : null}
            {resendMessage ? (
              <div className="mt-4 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-xs text-gray-300">
                {resendMessage}
              </div>
            ) : null}
            <button
              onClick={handleResend}
              disabled={resending || !email}
              className="mt-4 w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {resending ? "Sending…" : "Request a new verification email"}
            </button>
          </>
        ) : (
          <button
            onClick={function () {
              window.location.reload();
            }}
            className="mt-6 w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
          >
            Try again
          </button>
        )}
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
        <Link href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">
          Sign in with a different one
        </Link>
      </p>
    </>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}

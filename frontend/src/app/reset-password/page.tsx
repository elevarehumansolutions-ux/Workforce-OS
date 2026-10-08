"use client";

import { Suspense, useState, FormEvent } from "react";
import type { ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";

const NETWORK_ERROR_MESSAGE = "Couldn't reach the server. Check your connection and try again.";

// The same rules the backend enforces on a new password (see
// validate_password_strength in the auth schemas), checked here first so the
// person sees what's missing before submitting rather than after.
const SPECIAL_CHARACTERS = /[!@#$%^&*(),.?":{}|<>]/;

function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push("At least 8 characters");
  if (!/[A-Z]/.test(password)) problems.push("One uppercase letter");
  if (!/[a-z]/.test(password)) problems.push("One lowercase letter");
  if (!/\d/.test(password)) problems.push("One number");
  if (!SPECIAL_CHARACTERS.test(password)) problems.push("One special character, such as ! @ # $ %");
  return problems;
}

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [formError, setFormError] = useState("");
  // The server's error code for a rejected link, so the page can say
  // exactly what's wrong with it and offer the one next step that helps.
  const [linkErrorCode, setLinkErrorCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const problems = passwordProblems(password);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setFieldError("");

    if (problems.length > 0) {
      setFieldError("That password doesn't meet all the requirements below yet.");
      return;
    }
    if (password !== confirmPassword) {
      setFieldError("The two passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST",
        body: { token: token, new_password: password },
        skipAuth: true,
      });
      setDone(true);
      setTimeout(function () {
        router.push("/login?reset=1");
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        if (
          err.code === "TOKEN_INVALID" ||
          err.code === "TOKEN_ALREADY_USED" ||
          err.code === "VERIFICATION_TOKEN_EXPIRED"
        ) {
          setLinkErrorCode(err.code);
        } else if (err.fieldErrors.new_password) {
          setFieldError(err.fieldErrors.new_password);
        } else {
          setFormError(err.message);
        }
      } else {
        setFormError(NETWORK_ERROR_MESSAGE);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function shell(children: ReactNode) {
    return (
      <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#05070f] px-6 text-white">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 78% 42%, rgba(99,102,241,0.16), transparent 55%), radial-gradient(circle at 15% 80%, rgba(99,102,241,0.06), transparent 50%)",
          }}
        />
        <div className="relative z-10 w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
          {children}
        </div>
      </div>
    );
  }

  // No token in the link at all: nothing to submit against.
  if (!token) {
    return shell(
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/15">
          <span className="text-2xl text-red-400">!</span>
        </div>
        <h1 className="mt-6 text-xl font-bold">This reset link is incomplete</h1>
        <p className="mt-2 text-sm text-gray-400">
          Open the link from your email again, or ask for a new one.
        </p>
        <Link
          href="/forgot-password"
          className="mt-6 block w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
        >
          Request a new reset link
        </Link>
      </div>
    );
  }

  if (done) {
    return shell(
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M5 13l4 4L19 7" stroke="#34d399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h1 className="mt-6 text-xl font-bold">Password updated</h1>
        <p className="mt-2 text-sm text-gray-400">Taking you to sign in…</p>
      </div>
    );
  }

  if (linkErrorCode) {
    let heading = "This reset link isn't valid";
    let body = "It may have been copied incompletely. Request a new link and try again.";
    if (linkErrorCode === "TOKEN_ALREADY_USED") {
      heading = "This link has already been used";
      body = "Each reset link works once. If you still can't sign in, request a new one.";
    } else if (linkErrorCode === "VERIFICATION_TOKEN_EXPIRED") {
      heading = "This reset link has expired";
      body = "Reset links only work for a short time. Request a new one to continue.";
    }
    return shell(
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/15">
          <span className="text-2xl text-red-400">!</span>
        </div>
        <h1 className="mt-6 text-xl font-bold">{heading}</h1>
        <p className="mt-2 text-sm text-gray-400">{body}</p>
        <Link
          href="/forgot-password"
          className="mt-6 block w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
        >
          Request a new reset link
        </Link>
        <Link href="/login" className="mt-3 block text-sm font-medium text-indigo-400 hover:text-indigo-300">
          Back to sign in
        </Link>
      </div>
    );
  }

  return shell(
    <>
      <h1 className="text-2xl font-bold">Choose a new password</h1>
      <p className="mt-1 text-sm text-gray-400">
        Pick a password you haven&apos;t used here before. You&apos;ll be signed out everywhere else.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-5">
        {formError ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {formError}
          </div>
        ) : null}

        <div>
          <label htmlFor="new-password" className="mb-2 block text-sm font-medium text-gray-200">
            New password
          </label>
          <div className="relative">
            <input
              id="new-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={function (e) {
                setPassword(e.target.value);
              }}
              autoComplete="new-password"
              className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-4 pr-14 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
            <button
              type="button"
              onClick={function () {
                setShowPassword(!showPassword);
              }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300"
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          {password.length > 0 && problems.length > 0 ? (
            <ul className="mt-2 space-y-0.5 text-xs text-amber-300">
              {problems.map(function (problem) {
                return <li key={problem}>• {problem}</li>;
              })}
            </ul>
          ) : null}
        </div>

        <div>
          <label htmlFor="confirm-password" className="mb-2 block text-sm font-medium text-gray-200">
            Confirm new password
          </label>
          <input
            id="confirm-password"
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={function (e) {
              setConfirmPassword(e.target.value);
            }}
            autoComplete="new-password"
            className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
          />
          {fieldError ? <p className="mt-1 text-xs text-red-400">{fieldError}</p> : null}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Update password"}
        </button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}

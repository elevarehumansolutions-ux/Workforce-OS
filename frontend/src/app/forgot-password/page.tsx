"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";

// POST /auth/forgot-password always answers 200 with a generic message,
// whether or not the address is registered, so the page shows its own fixed
// line rather than anything account-specific.
const SENT_MESSAGE =
  "If an account with that email exists, we've sent a password reset link. Check your inbox, and your spam folder too.";
const NETWORK_ERROR_MESSAGE = "Couldn't reach the server. Check your connection and try again.";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setEmailError("");

    const trimmed = email.trim();
    if (!trimmed) {
      setEmailError("Email address is required.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setEmailError("Enter a valid email address.");
      return;
    }

    setSubmitting(true);
    try {
      await apiFetch("/auth/forgot-password", {
        method: "POST",
        body: { email: trimmed },
        skipAuth: true,
      });
      setSent(true);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors.email) {
          setEmailError(err.fieldErrors.email);
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
        {sent ? (
          <div className="text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-indigo-500/15">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M4 6h16v12H4z" stroke="#818cf8" strokeWidth="1.5" />
                <path d="M4 7l8 6 8-6" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h1 className="mt-6 text-xl font-bold">Check your email</h1>
            <p className="mt-2 text-sm text-gray-400">{SENT_MESSAGE}</p>
            <Link
              href="/login"
              className="mt-6 block w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Back to sign in
            </Link>
            <button
              type="button"
              onClick={function () {
                setSent(false);
              }}
              className="mt-3 text-sm font-medium text-indigo-400 hover:text-indigo-300"
            >
              Use a different email
            </button>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold">Forgot your password?</h1>
            <p className="mt-1 text-sm text-gray-400">
              Enter the email you signed up with and we&apos;ll send you a link to choose a new one.
            </p>

            <form onSubmit={handleSubmit} className="mt-6 space-y-5">
              {formError ? (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {formError}
                </div>
              ) : null}

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-gray-200">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={function (e) {
                    setEmail(e.target.value);
                  }}
                  placeholder="e.g. adewale.alabi@zenithtech.ng"
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
                {emailError ? <p className="mt-1 text-xs text-red-400">{emailError}</p> : null}
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Sending…" : "Send reset link"}
              </button>

              <p className="text-center text-sm text-gray-400">
                Remembered it?{" "}
                <Link href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">
                  Back to sign in
                </Link>
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

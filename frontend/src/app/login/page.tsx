"use client";

import { useState, FormEvent, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, setAccessToken, ApiError } from "@/lib/api";

interface LoginFormData {
  email: string;
  password: string;
  keepSignedIn: boolean;
}

interface AuthResponse {
  user: { id: string; email: string; full_name: string; account_status: string };
  organization: { id: string; name: string };
  membership: { id: string; role: string; is_owner: boolean };
  access_token: string;
  token_type: string;
  verification_token: string;
}

const PENDING_EMAIL_KEY = "elevare_pending_verification_email";

const NETWORK_ERROR_MESSAGE = "Couldn't reach the server. Check your connection and try again.";
const RESEND_GENERIC_MESSAGE = "If that address needs verifying, we've sent a new verification link.";

// The server's own messages for these are short and technical ("Invalid
// credentials", "Email verification required"), so each known error code gets
// wording written for the person reading it. Anything else falls back to the
// server's message as-is.
function friendlyLoginError(err: ApiError): string {
  switch (err.code) {
    case "INVALID_CREDENTIALS":
      return "That email and password don't match. Check them and try again.";
    case "EMAIL_VERIFICATION_REQUIRED":
      return "Your email address isn't verified yet. Open the verification link we emailed you, or request a new one below.";
    case "ACCOUNT_SUSPENDED":
      return "This account has been suspended. Contact your administrator for help.";
    case "ACCOUNT_BANNED":
      return "This account is no longer allowed to sign in. Contact support if you think that's a mistake.";
    case "ACCOUNT_DEACTIVATED":
      return "This account has been deactivated. Contact your administrator to have it restored.";
    case "NO_ACTIVE_MEMBERSHIP":
      return "Your access to this organization has been removed. Ask your HR administrator to reactivate you.";
    default:
      if (err.status === 429) {
        return "Too many attempts. Wait a moment and try again.";
      }
      return err.message;
  }
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const justVerified = searchParams.get("verified") === "1";
  const justReset = searchParams.get("reset") === "1";

  const [formData, setFormData] = useState<LoginFormData>({ email: "", password: "", keepSignedIn: false });
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!formData.email.trim()) {
      newErrors.email = "Email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = "Enter a valid email address.";
    }
    if (!formData.password) newErrors.password = "Password is required.";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setNeedsVerification(false);
    setResendMessage("");
    setSubmitting(true);
    try {
      const data = await apiFetch<AuthResponse>("/auth/login", {
        method: "POST",
        body: { email: formData.email, password: formData.password },
        skipAuth: true,
      });

      setAccessToken(data.access_token);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (Object.keys(err.fieldErrors).length > 0) {
          setErrors(err.fieldErrors);
        } else {
          setErrors({ form: friendlyLoginError(err) });
        }
        if (err.code === "EMAIL_VERIFICATION_REQUIRED") {
          setNeedsVerification(true);
        }
      } else {
        // No usable response at all: offline, server unreachable, or the
        // reply wasn't JSON. Either way it isn't the person's mistake.
        setErrors({ form: NETWORK_ERROR_MESSAGE });
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResendVerification() {
    const email = formData.email.trim();
    if (!email) return;
    setResending(true);
    setResendMessage("");
    try {
      await apiFetch("/auth/resend-verification", {
        method: "POST",
        body: { email: email },
        skipAuth: true,
      });
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(PENDING_EMAIL_KEY, email);
        } catch {
          // Storage can be unavailable (private window); the message below still shows.
        }
      }
      // Always the same line, whether or not the address exists — the
      // backend never reveals that, so neither does this page.
      setResendMessage(RESEND_GENERIC_MESSAGE);
    } catch (err) {
      setResendMessage(err instanceof ApiError ? err.message : NETWORK_ERROR_MESSAGE);
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-[#05070f] text-white">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 78% 42%, rgba(99,102,241,0.16), transparent 55%), radial-gradient(circle at 15% 80%, rgba(99,102,241,0.06), transparent 50%)",
        }}
      />

      <div className="relative z-10 flex items-center gap-3 px-8 pt-8 sm:px-16 sm:pt-10">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
            <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
          </svg>
        </div>
        <span className="text-lg font-bold">Elevare</span>
      </div>

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-96px)] w-full max-w-7xl flex-col items-center justify-center gap-16 px-8 py-12 sm:px-16 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-extrabold leading-tight sm:text-5xl">The Engine for West Africa&apos;s Teams</h1>
          <p className="mt-4 text-lg text-gray-400">Workforce Management System</p>
          <div className="mt-6 flex items-center gap-2 text-sm text-gray-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>Ready for the Nigeria Workforce OS MVP Onboarding</span>
          </div>
        </div>

        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
          <h2 className="text-2xl font-bold">Welcome back</h2>
          <p className="mt-1 text-sm text-gray-400">Sign in to your account to manage your organization</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-6">
            {justReset ? (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                Your password has been updated. Sign in with your new password.
              </div>
            ) : null}
            {justVerified && !justReset ? (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                Your email is verified. Sign in to continue.
              </div>
            ) : null}

            {errors.form ? (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {errors.form}
                {needsVerification ? (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleResendVerification}
                      disabled={resending || !formData.email.trim()}
                      className="rounded-lg border border-red-400/40 px-3 py-1.5 text-xs font-medium text-red-200 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {resending ? "Sending…" : "Send a new verification email"}
                    </button>
                    {resendMessage ? <p className="mt-2 text-xs text-red-200/90">{resendMessage}</p> : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-gray-200">Email Address</label>
              <input
                id="email"
                type="email"
                placeholder="e.g. adewale.alabi@zenithtech.ng"
                value={formData.email}
                onChange={function (e) {
                  setFormData({ ...formData, email: e.target.value });
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
              {errors.email ? <p className="mt-1 text-xs text-red-400">{errors.email}</p> : null}
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.keepSignedIn}
                  onChange={function (e) {
                    setFormData({ ...formData, keepSignedIn: e.target.checked });
                  }}
                  className="h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500"
                />
                <span>Keep me signed in</span>
              </label>
              <Link href="/forgot-password" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
                Forgot password?
              </Link>
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-gray-200">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="********"
                  value={formData.password}
                  onChange={function (e) {
                    setFormData({ ...formData, password: e.target.value });
                  }}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-4 pr-10 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
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
              {errors.password ? <p className="mt-1 text-xs text-red-400">{errors.password}</p> : null}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Signing in..." : "Sign In"}
            </button>

            <p className="text-center text-sm text-gray-400">
              Don&apos;t have an account?{" "}
              <Link href="/signup" className="font-medium text-indigo-400 hover:text-indigo-300">Create one</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams() needs a Suspense boundary in the App Router, same as
  // the verify-email page.
  return (
    <Suspense fallback={null}>
      <LoginContent />
    </Suspense>
  );
}

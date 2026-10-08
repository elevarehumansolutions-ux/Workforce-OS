"use client";

import { Suspense, useState, FormEvent } from "react";
import type { ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, setAccessToken, ApiError } from "@/lib/api";

const NETWORK_ERROR_MESSAGE = "Couldn't reach the server. Check your connection and try again.";

// Same strength rules as sign-up and password reset, so a password that
// works in one place works in all of them.
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

interface AcceptInviteResponse {
  access_token: string;
  organization: { id: string; name: string };
}

function AcceptInviteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  // Set when the server rejects the invite link itself, so the page can
  // explain exactly what is wrong with it.
  const [linkProblem, setLinkProblem] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [joined, setJoined] = useState(false);
  const [joinedOrg, setJoinedOrg] = useState("");

  const problems = passwordProblems(password);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError("");

    const newErrors: Record<string, string> = {};
    const trimmedName = fullName.trim();
    if (trimmedName.length < 6) {
      newErrors.full_name = "Enter your full name (at least 6 characters).";
    }
    if (problems.length > 0) {
      newErrors.password = "That password doesn't meet all the requirements below yet.";
    }
    if (password !== confirmPassword) {
      newErrors.confirm_password = "The two passwords don't match.";
    }
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    setSubmitting(true);
    try {
      const data = await apiFetch<AcceptInviteResponse>("/auth/accept-invite", {
        method: "POST",
        body: {
          token: token,
          full_name: trimmedName,
          password: password,
          confirm_password: confirmPassword,
        },
        skipAuth: true,
      });
      setAccessToken(data.access_token);
      setJoinedOrg(data.organization ? data.organization.name : "");
      setJoined(true);
      setTimeout(function () {
        router.push("/dashboard");
      }, 1500);
    } catch (err) {
      if (err instanceof ApiError) {
        if (
          err.code === "TOKEN_INVALID" ||
          err.code === "TOKEN_ALREADY_USED" ||
          err.code === "VERIFICATION_TOKEN_EXPIRED"
        ) {
          setLinkProblem(err.code);
        } else if (err.status === 409) {
          setLinkProblem("ACCOUNT_EXISTS");
        } else if (Object.keys(err.fieldErrors).length > 0) {
          setErrors(err.fieldErrors);
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
      <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#05070f] px-6 py-10 text-white">
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

  function problemScreen(heading: string, body: string, showLogin: boolean) {
    return shell(
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/15">
          <span className="text-2xl text-red-400">!</span>
        </div>
        <h1 className="mt-6 text-xl font-bold">{heading}</h1>
        <p className="mt-2 text-sm text-gray-400">{body}</p>
        {showLogin ? (
          <Link
            href="/login"
            className="mt-6 block w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
          >
            Go to sign in
          </Link>
        ) : null}
      </div>
    );
  }

  if (!token) {
    return problemScreen(
      "This invite link is incomplete",
      "Open the link from your invitation email again. If it still doesn't work, ask whoever invited you to send a new one.",
      false
    );
  }

  if (joined) {
    return shell(
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M5 13l4 4L19 7" stroke="#34d399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h1 className="mt-6 text-xl font-bold">You&apos;re in</h1>
        <p className="mt-2 text-sm text-gray-400">
          {joinedOrg ? "Welcome to " + joinedOrg + ". " : ""}Taking you to your dashboard…
        </p>
      </div>
    );
  }

  if (linkProblem === "TOKEN_ALREADY_USED") {
    return problemScreen(
      "This invite has already been used",
      "If that was you, sign in with the password you chose. Otherwise ask whoever invited you for a new invite.",
      true
    );
  }
  if (linkProblem === "VERIFICATION_TOKEN_EXPIRED") {
    return problemScreen(
      "This invite has expired",
      "Invites only work for a limited time. Ask whoever invited you to send a new one.",
      false
    );
  }
  if (linkProblem === "ACCOUNT_EXISTS") {
    return problemScreen(
      "You already have an account",
      "An account with this email already exists. Sign in, then ask whoever invited you to add you to their organization.",
      true
    );
  }
  if (linkProblem) {
    return problemScreen(
      "This invite link isn't valid",
      "It may have been copied incompletely. Ask whoever invited you to send a new one.",
      false
    );
  }

  const inputClass =
    "w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500";

  return shell(
    <>
      <h1 className="text-2xl font-bold">Join your team</h1>
      <p className="mt-1 text-sm text-gray-400">
        You&apos;ve been invited to Elevare. Set up your account to get started.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-5">
        {formError ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {formError}
          </div>
        ) : null}

        <div>
          <label htmlFor="full-name" className="mb-2 block text-sm font-medium text-gray-200">
            Full name
          </label>
          <input
            id="full-name"
            type="text"
            value={fullName}
            onChange={function (e) {
              setFullName(e.target.value);
            }}
            autoComplete="name"
            placeholder="e.g. Adewale Alabi"
            className={inputClass}
          />
          {errors.full_name ? <p className="mt-1 text-xs text-red-400">{errors.full_name}</p> : null}
        </div>

        <div>
          <label htmlFor="new-password" className="mb-2 block text-sm font-medium text-gray-200">
            Password
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
              className={inputClass + " pr-14"}
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
          {errors.password ? <p className="mt-1 text-xs text-red-400">{errors.password}</p> : null}
        </div>

        <div>
          <label htmlFor="confirm-password" className="mb-2 block text-sm font-medium text-gray-200">
            Confirm password
          </label>
          <input
            id="confirm-password"
            type={showPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={function (e) {
              setConfirmPassword(e.target.value);
            }}
            autoComplete="new-password"
            className={inputClass}
          />
          {errors.confirm_password ? <p className="mt-1 text-xs text-red-400">{errors.confirm_password}</p> : null}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Creating your account…" : "Join team"}
        </button>

        <p className="text-center text-sm text-gray-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">
            Sign in
          </Link>
        </p>
      </form>
    </>
  );
}

export default function AcceptInvitePage() {
  // useSearchParams() needs a Suspense boundary in the App Router.
  return (
    <Suspense fallback={null}>
      <AcceptInviteContent />
    </Suspense>
  );
}

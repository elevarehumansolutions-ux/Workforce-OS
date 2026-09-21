"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setAccessToken, ApiError } from "@/lib/api";

interface LoginFormData {
  email: string;
  password: string;
  keepSignedIn: boolean;
}

interface LoginResponse {
  accessToken: string;
  // refreshToken travels as an httpOnly cookie set by the server, not
  // returned in the body — nothing to do with it here.
}

export default function LoginPage() {
  const router = useRouter();
  const [formData, setFormData] = useState<LoginFormData>({
    email: "",
    password: "",
    keepSignedIn: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};

    if (!formData.email.trim()) {
      newErrors.email = "Email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = "Enter a valid email address.";
    }

    if (!formData.password) {
      newErrors.password = "Password is required.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    try {
      const data = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: { email: formData.email, password: formData.password },
        skipAuth: true,
      });

      setAccessToken(data.accessToken);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.details.length > 0) {
          const fieldErrors: Record<string, string> = {};
          err.details.forEach((d) => {
            fieldErrors[d.field] = d.message;
          });
          setErrors(fieldErrors);
        } else {
          setErrors({ form: err.message });
        }
      } else {
        setErrors({
          form:
            err instanceof Error
              ? err.message
              : "Something went wrong. Please try again.",
        });
      }
    } finally {
      setSubmitting(false);
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
          <h1 className="text-4xl font-extrabold leading-tight sm:text-5xl">
             The Engine for West <br />
    Africa&apos;s Teams
          </h1>
          <p className="mt-4 text-lg text-gray-400">Workforce Management System</p>
          <div className="mt-6 flex items-center gap-2 text-sm text-gray-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>Ready for the Nigeria Workforce OS MVP Onboarding</span>
          </div>
        </div>

        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
          <h2 className="text-2xl font-bold">Welcome back</h2>
          <p className="mt-1 text-sm text-gray-400">
            Sign in to your account to manage your organization
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-6">
            {errors.form && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {errors.form}
              </div>
            )}

            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-gray-200">
                Email Address
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="m3 7 9 6 9-6" />
                  </svg>
                </span>
                <input
                  id="email"
                  type="email"
                  placeholder="e.g. adewale.alabi@zenithtech.ng"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-10 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
              </div>
              {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email}</p>}
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.keepSignedIn}
                  onChange={(e) => setFormData({ ...formData, keepSignedIn: e.target.checked })}
                  className="h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500"
                />
                <span>Keep me signed in</span>
              </label>
              <a href="#" className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
                Forgot password?
              </a>
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-gray-200">
                Password
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="4" y="11" width="16" height="9" rx="2" />
                    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                  </svg>
                </span>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="********"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-10 pr-10 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  <EyeIcon open={showPassword} />
                </button>
              </div>
              {errors.password && <p className="mt-1 text-xs text-red-400">{errors.password}</p>}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Signing in…" : "Sign In"}
            </button>

            <p className="text-center text-sm text-gray-400">
              Don&apos;t have an account?{" "}
              <a href="/signup" className="font-medium text-indigo-400 hover:text-indigo-300">
                Create one
              </a>
            </p>
          </form>
        </div>
      </div>

      <div className="relative z-10 flex flex-col items-center gap-1 px-8 pb-8 sm:flex-row sm:items-end sm:justify-between sm:px-16">
        <div>
          <p className="text-sm text-gray-400">Elevare Workforce OS &middot; Enterprise Grade</p>
          <p className="text-xs text-gray-600">Compliant with local labour structures</p>
        </div>
        <p className="text-xs text-gray-600 sm:absolute sm:left-1/2 sm:-translate-x-1/2">
          Elevare Workforce OS &copy; 2026
        </p>
      </div>
    </div>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-10-8-10-8a19.7 19.7 0 0 1 5.06-5.94M9.9 4.24A10.4 10.4 0 0 1 12 4c7 0 10 8 10 8a19.7 19.7 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}
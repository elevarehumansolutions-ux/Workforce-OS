"use client";

import React, { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setAccessToken, ApiError } from "@/lib/api";

interface SignupFormData {
  fullName: string;
  workEmail: string;
  password: string;
  confirmPassword: string;
  agreeToTerms: boolean;
}

interface AuthResponse {
  user: {
    id: string;
    email: string;
    full_name: string;
    account_status: string;
  };
  organization: { id: string; name: string };
  membership: { id: string; role: string; is_owner: boolean };
  access_token: string;
  token_type: string;
  verification_token: string;
}

export default function SignupPage() {
  const router = useRouter();
  const [formData, setFormData] = useState<SignupFormData>({
    fullName: "",
    workEmail: "",
    password: "",
    confirmPassword: "",
    agreeToTerms: true,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    if (!formData.fullName.trim()) newErrors.fullName = "Full name is required.";
    if (!formData.workEmail.trim()) {
      newErrors.workEmail = "Work email is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.workEmail)) {
      newErrors.workEmail = "Enter a valid email address.";
    }
    if (!formData.password) {
      newErrors.password = "Password is required.";
    } else if (formData.password.length < 8) {
      newErrors.password = "Password must be at least 8 characters.";
    }
    if (formData.confirmPassword !== formData.password) {
      newErrors.confirmPassword = "Passwords do not match.";
    }
    if (!formData.agreeToTerms) {
      newErrors.agreeToTerms = "You must agree to the Terms of Service.";
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    try {
      const data = await apiFetch<AuthResponse>("/auth/register", {
        method: "POST",
        body: {
          full_name: formData.fullName,
          email: formData.workEmail,
          password: formData.password,
          confirm_password: formData.confirmPassword,
        },
        skipAuth: true,
      });

      setAccessToken(data.access_token);
      router.push("/onboarding/business-dna");
    } catch (err) {
      if (err instanceof ApiError) {
        if (Object.keys(err.fieldErrors).length > 0) {
          setErrors(err.fieldErrors);
        } else {
          setErrors({ form: err.message });
        }
      } else {
        setErrors({ form: err instanceof Error ? err.message : "Something went wrong. Please try again." });
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
        <div className="max-w-md">
          <h1 className="text-4xl font-extrabold leading-tight sm:text-5xl">Create your organization</h1>
          <p className="mt-4 text-lg text-gray-400">Set up your company&apos;s workspace in a few minutes</p>
          <div className="mt-6 flex items-center gap-2 text-sm text-gray-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>Start your West African Workforce OS journey</span>
          </div>
        </div>

        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm">
          <h2 className="text-2xl font-bold">Get started</h2>
          <p className="mt-1 text-sm text-gray-400">Create your admin account to begin setup</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-6">
            {errors.form ? (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {errors.form}
              </div>
            ) : null}

            <div>
              <label htmlFor="fullName" className="mb-2 block text-sm font-medium text-gray-200">Full Name</label>
              <input
                id="fullName"
                type="text"
                placeholder="e.g. Adewale Alabi"
                value={formData.fullName}
                onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                  setFormData({ ...formData, fullName: e.target.value });
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
              {errors.fullName ? <p className="mt-1 text-xs text-red-400">{errors.fullName}</p> : null}
            </div>

            <div>
              <label htmlFor="workEmail" className="mb-2 block text-sm font-medium text-gray-200">Work Email</label>
              <input
                id="workEmail"
                type="email"
                placeholder="e.g. adewale.alabi@zenithtech.ng"
                value={formData.workEmail}
                onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                  setFormData({ ...formData, workEmail: e.target.value });
                }}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
              {errors.workEmail ? <p className="mt-1 text-xs text-red-400">{errors.workEmail}</p> : null}
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-gray-200">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="********"
                  value={formData.password}
                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
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

            <div>
              <label htmlFor="confirmPassword" className="mb-2 block text-sm font-medium text-gray-200">Confirm Password</label>
              <div className="relative">
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? "text" : "password"}
                  placeholder="********"
                  value={formData.confirmPassword}
                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                    setFormData({ ...formData, confirmPassword: e.target.value });
                  }}
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-4 pr-10 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
                <button
                  type="button"
                  onClick={function () {
                    setShowConfirmPassword(!showConfirmPassword);
                  }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300"
                >
                  {showConfirmPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.confirmPassword ? <p className="mt-1 text-xs text-red-400">{errors.confirmPassword}</p> : null}
            </div>

            <div>
              <label className="flex items-start gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.agreeToTerms}
                  onChange={function (e: React.ChangeEvent<HTMLInputElement>) {
                    setFormData({ ...formData, agreeToTerms: e.target.checked });
                  }}
                  className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#0a0e1a] accent-indigo-500"
                />
                <span>
                  I agree to the <a href="#" className="text-indigo-400 hover:text-indigo-300">Terms of Service</a> and{" "}
                  <a href="#" className="text-indigo-400 hover:text-indigo-300">Privacy Policy</a>
                </span>
              </label>
              {errors.agreeToTerms ? <p className="mt-1 text-xs text-red-400">{errors.agreeToTerms}</p> : null}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-indigo-500 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Creating account..." : "Create Account"}
            </button>

            <p className="text-center text-sm text-gray-400">
              Already have an account?{" "}
              <a href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">Sign in</a>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

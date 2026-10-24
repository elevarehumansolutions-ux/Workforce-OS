"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";
import { INDUSTRY_OPTIONS, OTHER_INDUSTRY, resolveIndustry, splitIndustry } from "@/lib/industry";

interface BusinessDnaFormData {
  companyName: string;
  industry: string;
  customIndustry: string;
  productsDescription: string;
  capitalInvestment: string;
  timezone: string;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "AI Structure",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

const DEFAULT_TIMEZONE = "Africa/Lagos";

interface IntlWithSupportedValuesOf {
  supportedValuesOf?: (key: string) => string[];
}

function getTimezoneOptions(): string[] {
  const intlWithSupportedValuesOf = Intl as unknown as IntlWithSupportedValuesOf;
  if (typeof intlWithSupportedValuesOf.supportedValuesOf === "function") {
    try {
      return intlWithSupportedValuesOf.supportedValuesOf("timeZone");
    } catch {
      // fall through to the static fallback below
    }
  }
  return [DEFAULT_TIMEZONE, "Africa/Nairobi", "Europe/London", "America/New_York", "Asia/Dubai"];
}

interface MeResponse {
  user: { account_status: string };
}

interface BusinessDnaResponse {
  organization_name: string | null;
  timezone: string;
  industry: string | null;
  products_services_description: string | null;
  capital_investment_amount: string | number | null;
}

export default function BusinessDnaPage() {
  const router = useRouter();

  // Starts true on both the server render and the client's first render so
  // they match exactly (getAccessToken() reads localStorage, which only
  // exists in the browser — branching on it here would make the server and
  // client disagree on what to render first and crash with a hydration
  // error). It only flips after the effect below resolves, post-mount.
  const [loadingExisting, setLoadingExisting] = useState<boolean>(true);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const timezoneOptions = useState(getTimezoneOptions)[0];

  useEffect(function () {
    if (!getAccessToken()) return;
    apiFetch<MeResponse>("/auth/me", { method: "GET" })
      .then(function (me) {
        if (me.user.account_status !== "verified") {
          router.replace("/verify-email");
        }
      })
      .catch(function () {
        // If the check itself fails (e.g. offline), don't block the wizard.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [formData, setFormData] = useState<BusinessDnaFormData>({
    companyName: "",
    industry: INDUSTRY_OPTIONS[0],
    customIndustry: "",
    productsDescription: "",
    capitalInvestment: "",
    timezone: DEFAULT_TIMEZONE,
  });

  // Pre-fill from the org's existing Business DNA profile, if one was already
  // saved (e.g. the person left the wizard and came back). GET /business-dna
  // 404s until the first PUT — that's expected for a brand-new org, so we
  // treat it as "nothing saved yet" rather than an error.
  useEffect(function () {
    const token = getAccessToken();
    const request: Promise<BusinessDnaResponse> = token
      ? apiFetch<BusinessDnaResponse>("/business-dna", { method: "GET" })
      : Promise.reject(new Error("not signed in"));
    request
      .then(function (data) {
        setFormData({
          companyName: data.organization_name || "",
          industry: splitIndustry(data.industry).choice,
          customIndustry: splitIndustry(data.industry).custom,
          productsDescription: data.products_services_description || "",
          capitalInvestment:
            data.capital_investment_amount === null || data.capital_investment_amount === undefined
              ? ""
              : String(data.capital_investment_amount),
          timezone: data.timezone || DEFAULT_TIMEZONE,
        });
      })
      .catch(function () {
        // 404 (no profile yet) or any other failure: start from the blank
        // defaults above, with Africa/Lagos as the org's default timezone.
      })
      .finally(function () {
        setLoadingExisting(false);
      });
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError("");
    if (formData.industry === OTHER_INDUSTRY && !formData.customIndustry.trim()) {
      setSubmitError("Please type your industry, or choose one from the list.");
      return;
    }
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        organization_name: formData.companyName || null,
        timezone: formData.timezone || null,
        industry: resolveIndustry(formData.industry, formData.customIndustry) || null,
        products_services_description: formData.productsDescription || null,
        capital_investment_amount: formData.capitalInvestment
          ? Number(formData.capitalInvestment)
          : null,
      };
      await apiFetch("/business-dna", { method: "PUT", body: payload });

      // The first save makes the backend start drafting the company's departments,
      // positions and objectives; the next step is where HR reviews them.
      router.push("/onboarding/blueprint");
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? err.message
          : "Couldn't save your Business DNA profile. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <div className="flex items-center justify-between border-b border-white/10 px-8 py-4 sm:px-12">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <circle cx="9" cy="8" r="3" />
              <path d="M2 20c0-3 3-5 7-5s7 2 7 5" />
              <circle cx="17" cy="8" r="2.5" />
              <path d="M22 20c0-2.5-2-4-4.5-4.5" />
            </svg>
          </div>
          <span className="text-base font-bold">Elevare</span>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {ONBOARDING_STEPS.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                    i === 0 ? "bg-indigo-500 text-white" : "border border-white/20 text-gray-400"
                  }`}
                >
                  {i + 1}
                </span>
                <span className={`text-sm ${i === 0 ? "font-medium text-indigo-400" : "text-gray-500"}`}>
                  {step}
                </span>
              </div>
              {i < ONBOARDING_STEPS.length - 1 && <span className="h-px w-6 bg-white/10" />}
            </div>
          ))}
        </div>

        <div className="text-sm text-gray-400">
          Need help? <a href="#" className="text-indigo-400 hover:text-indigo-300">Contact Support</a>
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Tell us about your business</h1>
          <p className="mt-2 text-gray-400">
            Configure your enterprise profile to personalize your local OS environment
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8 shadow-2xl backdrop-blur-sm"
        >
          {loadingExisting ? (
            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-sm text-gray-400">
              Loading your saved profile…
            </div>
          ) : null}

          {submitError ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {submitError}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Company Name</label>
              <input
                type="text"
                value={formData.companyName}
                onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                placeholder="e.g. Zenith Technologies Ltd"
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Industry</label>
              <select
                value={formData.industry}
                onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
              >
                {INDUSTRY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              {formData.industry === OTHER_INDUSTRY ? (
                <div className="mt-3">
                  <input
                    type="text"
                    autoFocus
                    maxLength={100}
                    value={formData.customIndustry}
                    onChange={(e) => setFormData({ ...formData, customIndustry: e.target.value })}
                    placeholder="Type your industry, e.g. Real Estate"
                    aria-label="Your industry"
                    className="w-full rounded-lg border border-indigo-500/40 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                  />
                  <p className="mt-1.5 text-xs text-gray-500">Not in the list? Tell us what your company does.</p>
                </div>
              ) : null}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">
              Business DNA{" "}
              <span className="text-sm font-normal text-gray-500">(e.g. vision, mission and core values)</span>
            </label>
            <p className="mb-2 text-sm text-gray-500">
              Describe what the company does and stands for: your vision, mission, core values, and the products or services you offer.
            </p>
            <textarea
              rows={9}
              value={formData.productsDescription}
              onChange={(e) => setFormData({ ...formData, productsDescription: e.target.value })}
              placeholder={"e.g. Vision: To be Africa's leading technology solutions provider.\nMission: Empowering modern businesses through secure, innovative technology.\nCore values: Collaboration, Excellence, Integrity.\nWhat we do: Enterprise software, cloud infrastructure and managed IT services."}
              className="w-full resize-y rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">
                Capital Investment
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                  &#8358;
                </span>
                <input
                  type="number"
                  value={formData.capitalInvestment}
                  onChange={(e) => setFormData({ ...formData, capitalInvestment: e.target.value })}
                  placeholder="e.g. 50,000,000"
                  className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-8 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Only visible to HR Administrators and Executives.
              </p>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">
                Organization Timezone
              </label>
              <select
                value={formData.timezone}
                onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
              >
                {!timezoneOptions.includes(formData.timezone) ? (
                  <option value={formData.timezone}>{formData.timezone}</option>
                ) : null}
                {timezoneOptions.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs text-gray-500">
                Used to decide when the working day ends for attendance.
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <span className="text-sm text-gray-500">
              {submitting ? "Saving…" : "Saved to your organization when you continue"}
            </span>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Saving…" : "Continue"}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

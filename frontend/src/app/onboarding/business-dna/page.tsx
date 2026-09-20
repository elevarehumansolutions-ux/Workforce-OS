"use client";

import { useState, FormEvent, KeyboardEvent } from "react";

interface BusinessDnaFormData {
  companyName: string;
  industry: string;
  productsDescription: string;
  vision: string;
  mission: string;
  coreValues: string[];
  minInvestment: string;
  maxInvestment: string;
}

const ONBOARDING_STEPS = [
  "Business DNA",
  "Organization",
  "OKRs",
  "AI Suggestions",
  "KPIs",
  "Invite Team",
];

const INDUSTRY_OPTIONS = [
  "Information Technology",
  "Financial Services",
  "Manufacturing",
  "Healthcare",
  "Retail & E-commerce",
  "Agriculture",
  "Logistics & Transportation",
  "Other",
];

export default function BusinessDnaPage() {
  const [formData, setFormData] = useState<BusinessDnaFormData>({
    companyName: "",
    industry: INDUSTRY_OPTIONS[0],
    productsDescription: "",
    vision: "",
    mission: "",
    coreValues: [],
    minInvestment: "",
    maxInvestment: "",
  });
  const [newValueInput, setNewValueInput] = useState("");
  const [showAddValue, setShowAddValue] = useState(false);

  function addCoreValue() {
    const trimmed = newValueInput.trim();
    if (trimmed && !formData.coreValues.includes(trimmed)) {
      setFormData({ ...formData, coreValues: [...formData.coreValues, trimmed] });
    }
    setNewValueInput("");
    setShowAddValue(false);
  }

  function removeCoreValue(value: string) {
    setFormData({
      ...formData,
      coreValues: formData.coreValues.filter((v) => v !== value),
    });
  }

  function handleValueKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      addCoreValue();
    } else if (e.key === "Escape") {
      setNewValueInput("");
      setShowAddValue(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    console.log("Business DNA submitted:", formData);
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
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">
              Products / Services Description
            </label>
            <textarea
              rows={3}
              value={formData.productsDescription}
              onChange={(e) => setFormData({ ...formData, productsDescription: e.target.value })}
              placeholder="e.g. Enterprise software solutions, cloud infrastructure, and managed IT services..."
              className="w-full resize-none rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Vision</label>
              <textarea
                rows={3}
                value={formData.vision}
                onChange={(e) => setFormData({ ...formData, vision: e.target.value })}
                placeholder="e.g. To be Africa's leading technology solutions provider..."
                className="w-full resize-none rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-200">Mission</label>
              <textarea
                rows={3}
                value={formData.mission}
                onChange={(e) => setFormData({ ...formData, mission: e.target.value })}
                placeholder="e.g. Empowering modern businesses through secure, innovative technology..."
                className="w-full resize-none rounded-lg border border-white/10 bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">Core Values</label>
            <div className="flex flex-wrap items-center gap-2">
              {formData.coreValues.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => removeCoreValue(value)}
                  className="rounded-full border border-indigo-500/50 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300 hover:border-red-400/50 hover:bg-red-400/10 hover:text-red-300"
                  title="Click to remove"
                >
                  {value}
                </button>
              ))}

              {showAddValue ? (
                <input
                  autoFocus
                  type="text"
                  value={newValueInput}
                  onChange={(e) => setNewValueInput(e.target.value)}
                  onKeyDown={handleValueKeyDown}
                  onBlur={addCoreValue}
                  placeholder="Type and press Enter"
                  className="rounded-full border border-white/20 bg-[#0a0e1a] px-4 py-1.5 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setShowAddValue(true)}
                  className="rounded-full border border-white/20 px-4 py-1.5 text-sm font-medium text-gray-300 hover:border-white/40"
                >
                  + Add Value
                </button>
              )}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-200">
              Investment / Capital Value
            </label>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <span className="mb-1 block text-xs text-gray-500">Minimum</span>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                    &#8358;
                  </span>
                  <input
                    type="number"
                    value={formData.minInvestment}
                    onChange={(e) => setFormData({ ...formData, minInvestment: e.target.value })}
                    placeholder="e.g. 50,000,000"
                    className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-8 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
              <div>
                <span className="mb-1 block text-xs text-gray-500">Maximum</span>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                    &#8358;
                  </span>
                  <input
                    type="number"
                    value={formData.maxInvestment}
                    onChange={(e) => setFormData({ ...formData, maxInvestment: e.target.value })}
                    placeholder="e.g. 200,000,000"
                    className="w-full rounded-lg border border-white/10 bg-[#0a0e1a] py-3 pl-8 pr-4 text-sm text-white placeholder-gray-500 outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Used to size revenue targets for critical departments — a range is fine if you&apos;re not exact.
            </p>
          </div>

          <div className="flex items-center justify-between border-t border-white/10 pt-6">
            <span className="text-sm text-gray-500">Draft saved automatically</span>
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Continue
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
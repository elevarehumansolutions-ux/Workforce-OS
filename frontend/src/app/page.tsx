import Link from "next/link";

const NAV_LINKS = ["Product", "Pricing", "About"];

const TRUST_LOGOS = ["NORTHSTAR", "KORA GROUP", "BRIDGEWORKS", "LAGOS LABS", "MERIDIAN"];

const FEATURES = [
  {
    title: "Attendance Shift OS",
    description: "Clock in and out across locations, manage shifts, and track attendance in real time.",
  },
  {
    title: "AI-Powered Insights",
    description: "Surface critical-role suggestions and clear executive summaries from live workforce data.",
  },
  {
    title: "Workflow Automation",
    description: "Move approvals faster with accountable owners, notifications, and templated processes.",
  },
  {
    title: "Payroll & Compliance",
    description: "Run dependable payroll designed around local labour structures and operating realities.",
  },
];

const SIGNAL_ITEMS = [
  { title: "Dashboard", subtitle: "Decisions at a glance" },
  { title: "People", subtitle: "One source of truth" },
  { title: "Attendance", subtitle: "Live shift visibility" },
  { title: "Payroll", subtitle: "Accurate local runs" },
];

const ONBOARDING_STEPS = [
  {
    number: "01",
    title: "Sign Up",
    description: "Create your admin workspace and choose the plan that fits your team.",
  },
  {
    number: "02",
    title: "Onboard Your Org",
    description: "Map your Business DNA, Org Setup, and OKRs with a guided flow.",
    tags: ["Business DNA", "Org Setup", "OKRs"],
  },
  {
    number: "03",
    title: "Go Live",
    description: "Invite teams, activate attendance, and run your first connected workflows.",
  },
];

const LOCAL_REALITY_ITEMS = [
  {
    title: "Local labour structures",
    description: "Model policies and payroll around how your organization actually operates.",
  },
  {
    title: "Operational realities",
    description: "Keep multi-site, shift, field, and office teams visible in one system.",
  },
  {
    title: "Regional scale",
    description: "Standardize core operations while teams expand across West Africa.",
  },
];

function LogoMark() {
  return (
    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
        <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
      </svg>
    </div>
  );
}

function SiteHeader() {
  return (
    <header className="relative z-20 border-b border-white/5">
      <div className="mx-auto flex max-w-[1280px] items-center justify-between px-8 py-5">
        <div className="flex items-center gap-3">
          <LogoMark />
          <span className="text-base font-bold">Elevare</span>
        </div>

        <nav className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map(function (link) {
            return (
              <a key={link} href="#" className="text-sm text-gray-400 transition hover:text-gray-200">
                {link}
              </a>
            );
          })}
        </nav>

        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm font-medium text-gray-300 transition hover:text-white">
            Sign In
          </Link>
          <Link
            href="/signup"
            className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-600"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  );
}

function HeroMockup() {
  return (
    <div className="relative rounded-2xl border border-white/10 bg-[#0d1220] p-4 shadow-2xl shadow-indigo-500/10">
      <div className="mb-4 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="8" width="4" height="9" rx="1" fill="white" />
            <rect x="13" y="3" width="4" height="14" rx="1" fill="white" />
          </svg>
        </span>
        <span className="text-sm font-bold">
          Elevare<span className="font-normal text-gray-500"> Executive Overview</span>
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-white/10 bg-[#05070f] p-3">
          <p className="text-[10px] uppercase tracking-wide text-gray-500">Total People</p>
          <p className="mt-1 text-lg font-bold">248</p>
          <p className="mt-0.5 text-[10px] text-emerald-400">+13 this month</p>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#05070f] p-3">
          <p className="text-[10px] uppercase tracking-wide text-gray-500">Attendance</p>
          <p className="mt-1 text-lg font-bold">94.8%</p>
          <p className="mt-0.5 text-[10px] text-emerald-400">+2.4% vs last week</p>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#05070f] p-3">
          <p className="text-[10px] uppercase tracking-wide text-gray-500">Payroll</p>
          <p className="mt-1 text-lg font-bold">N28.4m</p>
          <p className="mt-0.5 text-[10px] text-amber-400">Ready for review</p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-white/10 bg-[#05070f] p-3">
          <p className="mb-2 text-[10px] uppercase tracking-wide text-gray-500">Workforce Performance</p>
          <div className="flex h-16 items-end gap-1.5">
            <div className="h-6 w-full rounded bg-white/10" />
            <div className="h-9 w-full rounded bg-white/10" />
            <div className="h-7 w-full rounded bg-white/10" />
            <div className="h-11 w-full rounded bg-white/10" />
            <div className="h-16 w-full rounded bg-indigo-500" />
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#05070f] p-3">
          <p className="text-[10px] uppercase tracking-wide text-gray-500">AI Priorities</p>
          <p className="mt-1 text-[11px] text-gray-400">3 critical roles need coverage this quarter</p>
          <div className="mt-3 rounded bg-indigo-500/15 px-2 py-1.5 text-[10px] font-medium text-indigo-300">
            Operations Lead is the highest-risk gap
          </div>
        </div>
      </div>
    </div>
  );
}

function HeroSection() {
  return (
    <section className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 78% 30%, rgba(99,102,241,0.16), transparent 55%), radial-gradient(circle at 10% 80%, rgba(99,102,241,0.06), transparent 50%)",
        }}
      />
      <div className="relative mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-16 px-8 py-24 lg:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400">Workforce Management System</p>
          <h1 className="mt-4 text-5xl font-extrabold leading-tight">The Engine for West Africa&apos;s Teams.</h1>
          <p className="mt-6 max-w-md text-lg text-gray-400">
            Attendance, performance, and payroll - unified in one platform built for how West African businesses actually operate.
          </p>

          <div className="mt-6 flex items-center gap-2 text-sm text-gray-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>Ready for the Nigeria Workforce OS MVP Onboarding.</span>
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className="rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
            >
              Start Free Trial
            </Link>
            <button
              type="button"
              className="rounded-lg border border-white/15 px-6 py-3 text-sm font-medium text-white transition hover:bg-white/5"
            >
              Book a Demo
            </button>
          </div>

          <p className="mt-4 text-xs text-gray-600">14-day trial - No credit card - Guided onboarding</p>
        </div>

        <HeroMockup />
      </div>
    </section>
  );
}

function TrustStrip() {
  return (
    <section className="border-y border-white/5 bg-[#070a12]">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-6 px-8 py-10">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Trusted by teams across Nigeria</p>
        <div className="flex flex-wrap items-center gap-10">
          {TRUST_LOGOS.map(function (name) {
            return (
              <span key={name} className="text-sm font-semibold tracking-wide text-gray-400">
                {name}
              </span>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section className="mx-auto max-w-[1280px] px-8 py-28">
      <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400">Elevare Workforce OS</p>
      <h2 className="mt-3 max-w-xl text-3xl font-bold sm:text-4xl">
        One operating system for the work behind your workforce.
      </h2>
      <p className="mt-4 max-w-xl text-gray-400">
        Replace fragmented tools and manual follow-ups with a focused system your people, managers, and executives can trust.
      </p>

      <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(function (feature) {
          return (
            <div
              key={feature.title}
              className="flex flex-col rounded-2xl border border-white/10 bg-[#0d1220]/80 p-6 transition hover:border-indigo-500/40 hover:bg-[#0d1220]"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 3" />
                </svg>
              </span>
              <h3 className="mt-4 text-base font-semibold">{feature.title}</h3>
              <p className="mt-2 text-sm text-gray-400">{feature.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SignalPanel() {
  return (
    <div className="rounded-2xl border border-white/10 bg-[#0d1220] p-6 shadow-xl">
      <h3 className="text-base font-semibold">People operations</h3>
      <p className="text-xs text-gray-500">Live organization health - This month</p>

      <div className="mt-5 grid grid-cols-2 gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500">Today&apos;s Attendance</p>
          <p className="mt-1 text-2xl font-bold">94.8%</p>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full w-[94.8%] rounded-full bg-indigo-500" />
          </div>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-500">Active People</p>
          <p className="mt-1 text-2xl font-bold">248</p>
          <div className="mt-2 flex -space-x-1">
            <span className="h-3 w-3 rounded-full bg-indigo-500" />
            <span className="h-3 w-3 rounded-full bg-emerald-400" />
            <span className="h-3 w-3 rounded-full bg-amber-400" />
            <span className="h-3 w-3 rounded-full bg-white/20" />
          </div>
        </div>
      </div>

      <div className="mt-6 space-y-3 border-t border-white/10 pt-5 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-gray-300">Payroll readiness</span>
          <span className="text-emerald-400">On track</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-300">Lagos HQ - 142 people</span>
          <span className="text-emerald-400">Ready</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-300">Abuja Operations - 64 people</span>
          <span className="text-amber-400">Review</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-300">Remote</span>
          <span className="text-gray-500">-</span>
        </div>
      </div>
    </div>
  );
}

function SignalSection() {
  return (
    <section className="bg-[#070a12]">
      <div className="mx-auto max-w-[1280px] px-8 py-28">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400">Elevare Workforce OS</p>
        <h2 className="mt-3 max-w-xl text-3xl font-bold sm:text-4xl">Every workforce signal, finally in one place.</h2>
        <p className="mt-4 max-w-xl text-gray-400">
          From the first clock-in to payroll review, Elevare keeps your operating picture current and your teams moving in the
          same direction.
        </p>

        <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-[320px_1fr]">
          <div className="flex flex-col gap-4">
            {SIGNAL_ITEMS.map(function (item) {
              return (
                <div
                  key={item.title}
                  className="flex items-center justify-between rounded-xl border border-white/10 bg-[#0d1220]/80 p-4 transition hover:border-white/20"
                >
                  <div>
                    <p className="text-sm font-semibold">{item.title}</p>
                    <p className="text-xs text-gray-500">{item.subtitle}</p>
                  </div>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-gray-500">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </div>
              );
            })}
          </div>

          <SignalPanel />
        </div>
      </div>
    </section>
  );
}

function OnboardingSection() {
  return (
    <section className="mx-auto max-w-[1280px] px-8 py-28">
      <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400">Elevare Workforce OS</p>
      <h2 className="mt-3 max-w-xl text-3xl font-bold sm:text-4xl">From sign-up to operating clarity.</h2>
      <p className="mt-4 max-w-xl text-gray-400">
        A structured onboarding sequence captures how your organization works before your team goes live.
      </p>

      <div className="relative mt-16 grid grid-cols-1 gap-10 md:grid-cols-3">
        <div className="absolute left-0 right-0 top-5 hidden h-px bg-white/10 md:block" />

        {ONBOARDING_STEPS.map(function (step) {
          return (
            <div key={step.number} className="relative">
              <span className="relative z-10 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-500 text-sm font-bold text-white">
                {step.number}
              </span>
              <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm text-gray-400">{step.description}</p>
              {step.tags ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {step.tags.map(function (tag) {
                    return (
                      <span key={tag} className="rounded-full bg-white/5 px-3 py-1 text-xs text-gray-400">
                        {tag}
                      </span>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LocalRealitySection() {
  return (
    <section className="bg-[#070a12]">
      <div className="mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-16 px-8 py-28 lg:grid-cols-2">
        <div className="flex items-center justify-center rounded-2xl border border-white/10 bg-[#0d1220] p-16">
          <svg width="140" height="140" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-indigo-400/40">
            <path d="M12 21s-7-6.5-7-11.5A7 7 0 0 1 19 9.5C19 14.5 12 21 12 21z" />
            <circle cx="12" cy="9.5" r="2.5" />
          </svg>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400">Built for Here</p>
          <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
            Local operational reality is the starting point - not an afterthought.
          </h2>
          <p className="mt-4 text-gray-400">
            Elevare reflects local labour structures, distributed operations, and the pace of scaling teams across Nigeria and the
            region.
          </p>

          <div className="mt-8 space-y-6">
            {LOCAL_REALITY_ITEMS.map(function (item) {
              return (
                <div key={item.title} className="flex gap-4">
                  <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-300">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="9" />
                      <path d="M12 7v5l3 3" />
                    </svg>
                  </span>
                  <div>
                    <p className="text-sm font-semibold">{item.title}</p>
                    <p className="mt-1 text-sm text-gray-400">{item.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function StatTestimonialSection() {
  return (
    <section className="mx-auto max-w-[1280px] px-8 py-28">
      <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
        <div>
          <p className="text-6xl font-extrabold text-indigo-400">60%</p>
          <p className="mt-3 text-lg font-semibold">Reduce onboarding time by 60%</p>
          <p className="mt-2 text-sm text-gray-500">Move from scattered spreadsheets to a guided, accountable launch.</p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#0d1220]/80 p-8">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" className="text-indigo-400/60">
            <path d="M9 7H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h3v3l4-4V8a1 1 0 0 0-1-1H9zM19 7h-5a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h3v3l4-4V8a1 1 0 0 0-1-1z" />
          </svg>
          <p className="mt-4 text-base text-gray-200">
            Elevare gave our leadership one reliable view of people operations. We onboarded managers faster and finally stopped
            chasing weekly updates.
          </p>
          <div className="mt-6">
            <p className="text-sm font-semibold">Amaka Nwosu</p>
            <p className="text-xs text-gray-500">COO, Meridian Commerce - Lagos</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCtaSection() {
  return (
    <section className="bg-indigo-500/10 border-y border-indigo-500/20">
      <div className="mx-auto flex max-w-[1280px] flex-col items-start justify-between gap-6 px-8 py-16 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-2xl font-bold sm:text-3xl">Ready to run your workforce better?</h2>
          <p className="mt-2 text-gray-400">Bring attendance, performance, payroll, and people operations into one clear system.</p>
        </div>
        <Link
          href="/signup"
          className="flex-shrink-0 rounded-lg bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
        >
          Get Started
        </Link>
      </div>
    </section>
  );
}

function SiteFooter() {
  const columns = [
    { title: "Product", links: ["Platform", "Attendance", "Payroll", "AI insights"] },
    { title: "Company", links: ["About", "Pricing", "Contact", "Careers"] },
    { title: "Legal", links: ["Privacy", "Terms", "Security", "Compliance"] },
  ];

  return (
    <footer className="mx-auto max-w-[1280px] px-8 py-16">
      <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="flex items-center gap-3">
            <LogoMark />
            <span className="text-base font-bold">Elevare</span>
          </div>
          <p className="mt-4 max-w-xs text-sm text-gray-500">
            The workforce operating system built for ambitious West African companies.
          </p>
          <p className="mt-4 text-xs text-gray-600">Compliant with local labour structures</p>
        </div>

        {columns.map(function (col) {
          return (
            <div key={col.title}>
              <p className="text-sm font-semibold">{col.title}</p>
              <div className="mt-4 flex flex-col gap-3">
                {col.links.map(function (link) {
                  return (
                    <a key={link} href="#" className="text-sm text-gray-500 transition hover:text-gray-300">
                      {link}
                    </a>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-12 border-t border-white/10 pt-8 text-xs text-gray-600">
        <p>Elevare Workforce OS © 2026</p>
        <p className="mt-1">Built for Nigeria - Ready for West Africa</p>
      </div>
    </footer>
  );
}

export default function HomePage() {
  return (
    <div className="min-h-screen w-full bg-[#05070f] text-white">
      <SiteHeader />
      <HeroSection />
      <TrustStrip />
      <FeaturesSection />
      <SignalSection />
      <OnboardingSection />
      <LocalRealitySection />
      <StatTestimonialSection />
      <FinalCtaSection />
      <SiteFooter />
    </div>
  );
}

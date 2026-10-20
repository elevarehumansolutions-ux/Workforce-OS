"use client";

import Link from "next/link";
import type { SectionProps } from "./types";

const ITEMS: { name: string; text: string; badge: string; planned: boolean }[] = [
  { name: "Payments (Paystack or Flutterwave)", text: "Subscription payments are handled by the Elevare team. Nothing to set up here.", badge: "Managed by Elevare", planned: false },
  { name: "Email delivery", text: "Password reset and invitation emails are sent by Elevare on your behalf.", badge: "Managed by Elevare", planned: false },
  { name: "AI assistant (Claude)", text: "Powers the role, KPI and suggestion features. Your usage is shown under Billing and AI usage.", badge: "Managed by Elevare", planned: false },
  { name: "Elevare Recruitment Platform", text: "Connecting hiring to your organization structure is planned for a later phase.", badge: "Planned", planned: true },
];

export default function IntegrationsSection(props: SectionProps) {
  void props;
  return (
    <div>
      <h3 className="text-base font-semibold text-white">Integrations</h3>
      <p className="mt-1 text-sm text-gray-500">The services Workforce OS works with. There is nothing for you to switch on or off yet.</p>
      <div className="mt-6 space-y-3">
        {ITEMS.map(function (i) {
          return (
            <div key={i.name} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-white">{i.name}</p>
                <p className="mt-1 text-sm text-gray-400">{i.text}</p>
              </div>
              <span className={"rounded px-2 py-0.5 text-xs font-medium " + (i.planned ? "bg-gray-500/20 text-gray-400" : "bg-emerald-500/15 text-emerald-400")}>
                {i.badge}
              </span>
            </div>
          );
        })}
      </div>
      <Link href="/settings/billing-ai-usage" className="mt-6 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300">
        Open Billing and AI usage
      </Link>
    </div>
  );
}

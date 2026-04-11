"use client";

import type { AlertRecord } from "@/lib/types";

interface AlertsFeedProps {
  alerts: AlertRecord[];
  onAcknowledge: (alertId: string) => void | Promise<void>;
}

const severityStyles: Record<AlertRecord["severity"], string> = {
  info: "border-sky-200 bg-sky-50",
  warning: "border-amber-200 bg-amber-50",
  critical: "border-rose-200 bg-rose-50",
};

export default function AlertsFeed({ alerts, onAcknowledge }: AlertsFeedProps) {
  return (
    <section className="panel-shell rounded-4xl p-6 sm:p-8">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h2 className="section-title">Alerts Feed</h2>
          <p className="section-copy">Latest reminders, unfamiliar faces, and high-priority SOS events.</p>
        </div>
        <div className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold tracking-[0.25em] text-white">
          {alerts.length} recent
        </div>
      </div>

      <div className="grid gap-4">
        {alerts.length === 0 ? (
          <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/70 p-6 text-slate-600">
            No alerts yet. The system will list new reminders and incidents here as they happen.
          </div>
        ) : null}

        {alerts.map((alert) => (
          <article
            key={alert.id}
            className={`rounded-[1.75rem] border p-5 ${severityStyles[alert.severity]}`}
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-slate-700">
                    {alert.severity}
                  </span>
                  <span className="text-sm text-slate-500">
                    {alert.created_at
                      ? new Date(alert.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
                      : "Just now"}
                  </span>
                  {alert.acknowledged ? (
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-white">
                      Acknowledged
                    </span>
                  ) : null}
                </div>

                <div>
                  <h3 className="text-2xl font-semibold text-slate-900">{alert.title}</h3>
                  <p className="mt-2 max-w-3xl text-base text-slate-700">
                    {alert.message || "No extra details were captured for this event."}
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-3 lg:min-w-[12rem]">
                {alert.image_url ? (
                  <img
                    src={alert.image_url}
                    alt={alert.title}
                    className="h-28 w-full rounded-[1.25rem] object-cover"
                  />
                ) : null}
                <button
                  type="button"
                  disabled={Boolean(alert.acknowledged)}
                  onClick={() => void onAcknowledge(alert.id)}
                  className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                  {alert.acknowledged ? "Acknowledged" : "Acknowledge"}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

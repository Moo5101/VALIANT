"use client";

import { useState } from "react";

import type { AlertRecord, Patient } from "@/lib/types";

interface StatusBannerProps {
  patient: Patient | null;
  alerts: AlertRecord[];
  apiBaseUrl: string;
}

function getSeverity(alerts: AlertRecord[]) {
  const latestAlert = alerts[0];
  if (!latestAlert) {
    return {
      label: "All Safe",
      copy: "No active hazards or unknown visitors have been detected recently.",
      tone: "bg-emerald-600 text-white",
      badge: "SAFE",
    };
  }

  if (latestAlert.severity === "critical") {
    return {
      label: "Danger - SOS Sent",
      copy: latestAlert.message ?? "A critical hazard has been detected and escalated.",
      tone: "bg-rose-700 text-white",
      badge: "SOS",
    };
  }

  if (latestAlert.severity === "warning") {
    return {
      label: "Warning",
      copy: latestAlert.message ?? "Attention is needed for a recent event.",
      tone: "bg-amber-500 text-slate-950",
      badge: "WARN",
    };
  }

  return {
    label: "Monitoring",
    copy: latestAlert.message ?? "The system is actively monitoring reminders and alerts.",
    tone: "bg-sky-600 text-white",
    badge: "INFO",
  };
}

export default function StatusBanner({ patient, alerts, apiBaseUrl }: StatusBannerProps) {
  const status = getSeverity(alerts);
  const [cameraAvailable, setCameraAvailable] = useState(true);
  const previewUrl = `${apiBaseUrl}/api/camera/stream`;

  return (
    <section className={`panel-shell overflow-hidden rounded-4xl ${status.tone}`}>
      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
        <div>
          <div className="inline-flex rounded-full border border-white/25 px-3 py-1 text-xs font-semibold tracking-[0.25em]">
            {status.badge}
          </div>
          <h2 className="mt-4 text-3xl font-semibold sm:text-4xl">{status.label}</h2>
          <p className="mt-3 max-w-3xl text-base sm:text-lg">
            {status.copy}
          </p>
          <p className="mt-6 text-sm uppercase tracking-[0.25em] opacity-80">
            Live coverage for {patient?.name ?? "the patient"}
          </p>
        </div>
        <div className="overflow-hidden rounded-[1.5rem] border border-white/20 bg-black/10">
          {cameraAvailable ? (
            <img
              src={previewUrl}
              alt="Live camera preview"
              className="h-72 w-full object-cover sm:h-80 lg:h-[24rem] xl:h-[26rem]"
              onLoad={() => setCameraAvailable(true)}
              onError={() => setCameraAvailable(false)}
            />
          ) : (
            <div className="flex h-72 items-center justify-center bg-black/20 px-6 text-center text-sm uppercase tracking-[0.25em] text-white/80 sm:h-80 lg:h-[24rem] xl:h-[26rem]">
              Camera preview unavailable
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

"use client";

import AppShell from "@/components/AppShell";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const bootstrapPatientId = process.env.NEXT_PUBLIC_PATIENT_ID ?? "";

export default function HomePage() {
  return (
    <AppShell apiBaseUrl={apiBaseUrl} bootstrapPatientId={bootstrapPatientId} />
  );
}

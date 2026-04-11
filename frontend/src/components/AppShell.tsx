"use client";

import { startTransition, useEffect, useState } from "react";

import AuthGate from "@/components/AuthGate";
import Dashboard from "@/components/Dashboard";
import { normalizePhone } from "@/lib/phone";
import type { Patient } from "@/lib/types";

const STORAGE_KEY = "alzheimer-dashboard-patient-id";

interface AppShellProps {
  apiBaseUrl: string;
  bootstrapPatientId?: string;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export default function AppShell({ apiBaseUrl, bootstrapPatientId = "" }: AppShellProps) {
  const [patientId, setPatientId] = useState<string>("");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;

    async function restoreSession() {
      const storedPatientId =
        window.localStorage.getItem(STORAGE_KEY) || bootstrapPatientId || "";

      if (!storedPatientId) {
        if (!isCancelled) {
          setBooting(false);
        }
        return;
      }

      try {
        const restoredPatient = await fetchJson<Patient>(
          `${apiBaseUrl}/api/session/activate/${storedPatientId}`,
          { method: "POST" },
        );
        if (isCancelled) {
          return;
        }
        window.localStorage.setItem(STORAGE_KEY, restoredPatient.id);
        startTransition(() => {
          setPatientId(restoredPatient.id);
          setPatient(restoredPatient);
          setError(null);
        });
      } catch {
        window.localStorage.removeItem(STORAGE_KEY);
      } finally {
        if (!isCancelled) {
          setBooting(false);
        }
      }
    }

    void restoreSession();

    return () => {
      isCancelled = true;
    };
  }, [apiBaseUrl, bootstrapPatientId]);

  async function handleSignIn(phone: string) {
    const normalizedPhone = normalizePhone(phone);
    if (!normalizedPhone) {
      setError("Enter a valid patient phone number to sign in.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const patientRecord = await fetchJson<Patient>(`${apiBaseUrl}/api/session/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ phone: normalizedPhone }),
      });
      window.localStorage.setItem(STORAGE_KEY, patientRecord.id);
      startTransition(() => {
        setPatientId(patientRecord.id);
        setPatient(patientRecord);
      });
    } catch {
      setError("No patient profile was found for that phone number.");
    } finally {
      setBusy(false);
    }
  }

  async function handleOnboard(payload: {
    name: string;
    phone: string;
    caregiver_name: string;
    caregiver_phone: string;
  }) {
    const normalizedPatientPhone = normalizePhone(payload.phone);
    const normalizedCaregiverPhone = normalizePhone(payload.caregiver_phone);
    if (!payload.name.trim()) {
      setError("Enter the patient name to create the profile.");
      return;
    }
    if (!normalizedPatientPhone || !normalizedCaregiverPhone) {
      setError("Enter valid patient and caregiver phone numbers.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const patientRecord = await fetchJson<Patient>(`${apiBaseUrl}/api/patient`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: payload.name.trim(),
          phone: normalizedPatientPhone,
          caregiver_name: payload.caregiver_name.trim(),
          caregiver_phone: normalizedCaregiverPhone,
        }),
      });
      window.localStorage.setItem(STORAGE_KEY, patientRecord.id);
      startTransition(() => {
        setPatientId(patientRecord.id);
        setPatient(patientRecord);
      });
    } catch {
      setError("The patient profile could not be created. Check the phone numbers and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    try {
      await fetchJson<{ cleared: boolean }>(`${apiBaseUrl}/api/session/clear`, {
        method: "POST",
      });
    } catch {
      // Keep the UI sign-out local even if the backend session clear fails.
    }
    window.localStorage.removeItem(STORAGE_KEY);
    startTransition(() => {
      setPatientId("");
      setPatient(null);
      setError(null);
    });
  }

  if (booting) {
    return (
      <main className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-6 py-10">
        <section className="panel-shell w-full rounded-4xl p-10 text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">Loading</p>
          <h1 className="mt-3 text-4xl font-semibold">Checking for an existing patient session.</h1>
        </section>
      </main>
    );
  }

  if (!patientId) {
    return (
      <main className="mx-auto min-h-screen max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <AuthGate busy={busy} error={error} onSignIn={handleSignIn} onOnboard={handleOnboard} />
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-5 sm:px-6 lg:px-10 lg:py-8">
      <Dashboard
        key={patientId}
        patientId={patientId}
        apiBaseUrl={apiBaseUrl}
        initialPatient={patient}
        initialMedicines={[]}
        initialFaces={[]}
        initialAlerts={[]}
        onSignOut={handleSignOut}
      />
    </main>
  );
}

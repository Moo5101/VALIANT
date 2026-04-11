"use client";

import { startTransition, useEffect, useRef, useState } from "react";

import AlertsFeed from "@/components/AlertsFeed";
import FacesPanel from "@/components/FacesPanel";
import MedicinePanel from "@/components/MedicinePanel";
import StatusBanner from "@/components/StatusBanner";
import { subscribeToAlerts } from "@/lib/supabase";
import type { AlertRecord, KnownFace, Medicine, Patient } from "@/lib/types";

interface DashboardProps {
  patientId: string;
  apiBaseUrl: string;
  initialPatient: Patient | null;
  initialMedicines: Medicine[];
  initialFaces: KnownFace[];
  initialAlerts: AlertRecord[];
  onSignOut: () => void;
}

async function fetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

async function fetchPatient(
  url: string,
  fallback: Patient | null,
): Promise<{ patient: Patient | null; missing: boolean }> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (response.status === 404) {
      return { patient: null, missing: true };
    }
    if (!response.ok) {
      return { patient: fallback, missing: false };
    }
    return { patient: (await response.json()) as Patient, missing: false };
  } catch {
    return { patient: fallback, missing: false };
  }
}

const VISIBLE_REFRESH_MS = 3000;
const HIDDEN_REFRESH_MS = 15000;

export default function Dashboard({
  patientId,
  apiBaseUrl,
  initialPatient,
  initialMedicines,
  initialFaces,
  initialAlerts,
  onSignOut,
}: DashboardProps) {
  const [patient, setPatient] = useState<Patient | null>(initialPatient);
  const [medicines, setMedicines] = useState<Medicine[]>(initialMedicines);
  const [faces, setFaces] = useState<KnownFace[]>(initialFaces);
  const [alerts, setAlerts] = useState<AlertRecord[]>(initialAlerts);
  const patientRef = useRef<Patient | null>(initialPatient);
  const medicinesRef = useRef<Medicine[]>(initialMedicines);
  const facesRef = useRef<KnownFace[]>(initialFaces);
  const alertsRef = useRef<AlertRecord[]>(initialAlerts);
  const onSignOutRef = useRef(onSignOut);

  useEffect(() => {
    patientRef.current = patient;
    medicinesRef.current = medicines;
    facesRef.current = faces;
    alertsRef.current = alerts;
  }, [patient, medicines, faces, alerts]);

  useEffect(() => {
    onSignOutRef.current = onSignOut;
  }, [onSignOut]);

  useEffect(() => {
    let isCancelled = false;
    let timeoutId: number | null = null;

    function scheduleRefresh(delay: number) {
      if (isCancelled) {
        return;
      }
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => {
        void refreshDashboard();
      }, delay);
    }

    async function refreshDashboard() {
      const [patientState, nextMedicines, nextFaces, nextAlerts] = await Promise.all([
        fetchPatient(`${apiBaseUrl}/api/patient/${patientId}`, patientRef.current),
        fetchJson<Medicine[]>(`${apiBaseUrl}/api/medicines/${patientId}`, medicinesRef.current),
        fetchJson<KnownFace[]>(`${apiBaseUrl}/api/faces/${patientId}`, facesRef.current),
        fetchJson<AlertRecord[]>(`${apiBaseUrl}/api/alerts/${patientId}`, alertsRef.current),
      ]);

      if (isCancelled) {
        return;
      }

      if (patientState.missing) {
        isCancelled = true;
        void onSignOutRef.current();
        return;
      }

      startTransition(() => {
        setPatient(patientState.patient);
        setMedicines(nextMedicines);
        setFaces(nextFaces);
        setAlerts(nextAlerts);
      });

      scheduleRefresh(document.visibilityState === "visible" ? VISIBLE_REFRESH_MS : HIDDEN_REFRESH_MS);
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        void refreshDashboard();
        return;
      }
      scheduleRefresh(HIDDEN_REFRESH_MS);
    }

    void refreshDashboard();
    const unsubscribe = subscribeToAlerts(patientId, () => {
      void refreshDashboard();
    });
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      isCancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      unsubscribe();
    };
  }, [patientId, apiBaseUrl]);

  async function acknowledgeAlert(alertId: string) {
    const response = await fetch(`${apiBaseUrl}/api/alerts/${alertId}/acknowledge`, {
      method: "PUT",
    });

    if (!response.ok) {
      return;
    }

    startTransition(() => {
      setAlerts((currentAlerts) =>
        currentAlerts.map((alert) =>
          alert.id === alertId ? { ...alert, acknowledged: true } : alert,
        ),
      );
    });
  }

  async function labelFace(faceId: string, label: string) {
    const trimmed = label.trim();
    if (!trimmed) {
      return;
    }

    const response = await fetch(`${apiBaseUrl}/api/faces/${faceId}/label`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ label: trimmed, is_familiar: true }),
    });

    if (!response.ok) {
      return;
    }

    startTransition(() => {
      setFaces((currentFaces) =>
        currentFaces.map((face) =>
          face.id === faceId ? { ...face, label: trimmed, is_familiar: true } : face,
        ),
      );
    });
  }

  return (
    <div className="space-y-6">
      <header className="panel-shell rounded-4xl p-6 sm:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-slate-500">Patient Safety Console</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
              {patient?.name ?? "Patient dashboard"}
            </h1>
            <p className="mt-3 max-w-3xl text-lg text-slate-600">
              Medicine reminders, familiar faces, and hazard alerts are tracked here for the patient and caregiver.
            </p>
          </div>
          <div className="grid gap-3 rounded-[1.5rem] border border-slate-200 bg-white/75 p-4 text-base text-slate-700 sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Patient Phone</p>
              <p className="mt-2 font-medium">{patient?.phone ?? "Not set"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Caregiver</p>
              <p className="mt-2 font-medium">
                {patient?.caregiver_name ?? "Caregiver"}
                <span className="block text-sm font-normal text-slate-500">
                  {patient?.caregiver_phone ?? "Not set"}
                </span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-full border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
          >
            Sign out
          </button>
        </div>
      </header>

      <StatusBanner patient={patient} alerts={alerts} apiBaseUrl={apiBaseUrl} />

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <MedicinePanel medicines={medicines} />
        <FacesPanel faces={faces} onLabelFace={labelFace} />
      </section>

      <AlertsFeed alerts={alerts} onAcknowledge={acknowledgeAlert} />
    </div>
  );
}

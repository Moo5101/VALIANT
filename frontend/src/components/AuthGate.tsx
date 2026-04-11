"use client";

import { useState } from "react";

interface OnboardingPayload {
  name: string;
  phone: string;
  patient_email: string;
  caregiver_name: string;
  caregiver_phone: string;
  caregiver_email: string;
}

interface AuthGateProps {
  busy: boolean;
  error: string | null;
  onSignIn: (phone: string) => Promise<void>;
  onOnboard: (payload: OnboardingPayload) => Promise<void>;
}

export default function AuthGate({ busy, error, onSignIn, onOnboard }: AuthGateProps) {
  const [mode, setMode] = useState<"sign-in" | "onboarding">("sign-in");
  const [signInPhone, setSignInPhone] = useState("");
  const [form, setForm] = useState<OnboardingPayload>({
    name: "",
    phone: "",
    patient_email: "",
    caregiver_name: "",
    caregiver_phone: "",
    caregiver_email: "",
  });

  return (
    <section className="panel-shell grid overflow-hidden rounded-4xl lg:grid-cols-[0.95fr_1.05fr]">
      <div className="bg-slate-900 px-8 py-10 text-white sm:px-10">
        <p className="text-sm uppercase tracking-[0.35em] text-white/60">Welcome</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
          Start the patient dashboard with a phone number.
        </h1>
        <p className="mt-5 max-w-xl text-lg text-white/75">
          The patient phone number and caregiver phone number are stored during onboarding so Twilio
          can send reminders, safety warnings, and SOS alerts. Patient and caregiver emails can also
          be stored for SendGrid-powered email delivery.
        </p>
        <div className="mt-8 grid gap-4 rounded-[1.75rem] border border-white/15 bg-white/5 p-5 text-sm text-white/80">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-white/50">Patient alerts</p>
            <p className="mt-2">Medicine reminders and immediate warnings go to the patient phone and email when available.</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-white/50">Caregiver alerts</p>
            <p className="mt-2">The caregiver phone and email receive the same alert stream with escalation context.</p>
          </div>
        </div>
      </div>

      <div className="px-6 py-8 sm:px-10 sm:py-10">
        <div className="inline-flex rounded-full border border-slate-200 bg-white/80 p-1">
          <button
            type="button"
            onClick={() => setMode("sign-in")}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
              mode === "sign-in" ? "bg-slate-900 text-white" : "text-slate-600"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode("onboarding")}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
              mode === "onboarding" ? "bg-slate-900 text-white" : "text-slate-600"
            }`}
          >
            Onboarding
          </button>
        </div>

        {error ? (
          <div className="mt-6 rounded-[1.25rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
            {error}
          </div>
        ) : null}

        {mode === "sign-in" ? (
          <form
            className="mt-8 space-y-5"
            onSubmit={async (event) => {
              event.preventDefault();
              await onSignIn(signInPhone);
            }}
          >
            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="signin-phone">
                Patient phone number
              </label>
              <p className="mt-1 text-sm text-slate-500">Use the same number saved during onboarding.</p>
              <input
                id="signin-phone"
                type="tel"
                value={signInPhone}
                onChange={(event) => setSignInPhone(event.target.value)}
                placeholder="+1 555 555 0123"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-[1.25rem] bg-slate-900 px-5 py-4 text-base font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busy ? "Signing in..." : "Open dashboard"}
            </button>
          </form>
        ) : (
          <form
            className="mt-8 grid gap-5"
            onSubmit={async (event) => {
              event.preventDefault();
              await onOnboard(form);
            }}
          >
            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="patient-name">
                Patient name
              </label>
              <input
                id="patient-name"
                type="text"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="John Carter"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="patient-phone">
                Patient phone number
              </label>
              <input
                id="patient-phone"
                type="tel"
                value={form.phone}
                onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
                placeholder="+1 555 555 0123"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="caregiver-name">
                Caregiver name
              </label>
              <input
                id="caregiver-name"
                type="text"
                value={form.caregiver_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, caregiver_name: event.target.value }))
                }
                placeholder="Emily Carter"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="patient-email">
                Patient email
              </label>
              <input
                id="patient-email"
                type="email"
                value={form.patient_email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, patient_email: event.target.value }))
                }
                placeholder="patient@example.com"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="caregiver-phone">
                Caregiver phone number
              </label>
              <input
                id="caregiver-phone"
                type="tel"
                value={form.caregiver_phone}
                onChange={(event) =>
                  setForm((current) => ({ ...current, caregiver_phone: event.target.value }))
                }
                placeholder="+1 555 555 0124"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700" htmlFor="caregiver-email">
                Caregiver email
              </label>
              <input
                id="caregiver-email"
                type="email"
                value={form.caregiver_email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, caregiver_email: event.target.value }))
                }
                placeholder="caregiver@example.com"
                className="mt-3 w-full rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none transition focus:border-slate-500"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 w-full rounded-[1.25rem] bg-slate-900 px-5 py-4 text-base font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {busy ? "Creating profile..." : "Create patient profile"}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

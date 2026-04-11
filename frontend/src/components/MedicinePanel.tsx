"use client";

import type { Medicine, Reminder } from "@/lib/types";

interface MedicinePanelProps {
  medicines: Medicine[];
}

const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function reminderTimeToDate(reminder: Reminder): Date | null {
  if (!reminder.reminder_time) {
    return null;
  }

  const [hour, minute] = reminder.reminder_time.split(":").map((value) => Number(value));
  const now = new Date();
  let bestCandidate: Date | null = null;

  for (let offset = 0; offset < 7; offset += 1) {
    const candidate = new Date(now);
    candidate.setDate(now.getDate() + offset);
    candidate.setHours(hour, minute, 0, 0);

    const day = dayNames[candidate.getDay()];
    const allowedDays = reminder.days_of_week && reminder.days_of_week.length > 0
      ? reminder.days_of_week
      : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    if (!allowedDays.includes(day)) {
      continue;
    }

    if (candidate >= now) {
      bestCandidate = candidate;
      break;
    }
  }

  return bestCandidate;
}

function getNextDose(reminders: Reminder[] | undefined) {
  if (!reminders || reminders.length === 0) {
    return null;
  }

  const candidates = reminders
    .map(reminderTimeToDate)
    .filter((value): value is Date => Boolean(value))
    .sort((left, right) => left.getTime() - right.getTime());

  return candidates[0] ?? null;
}

function toneForDose(nextDose: Date | null) {
  if (!nextDose) {
    return "border-slate-200 bg-slate-50 text-slate-700";
  }

  const minutesUntil = Math.round((nextDose.getTime() - Date.now()) / 60000);
  if (minutesUntil <= 60) {
    return "border-rose-200 bg-rose-50 text-rose-900";
  }
  if (minutesUntil <= 240) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

export default function MedicinePanel({ medicines }: MedicinePanelProps) {
  return (
    <section className="panel-shell rounded-4xl p-6 sm:p-8">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h2 className="section-title">Medicine Schedule</h2>
          <p className="section-copy">Gemini-detected bottles and their next reminder windows.</p>
        </div>
        <div className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold tracking-[0.25em] text-white">
          {medicines.length} tracked
        </div>
      </div>

      <div className="grid gap-4">
        {medicines.length === 0 ? (
          <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/70 p-6 text-slate-600">
            No medicine bottles have been saved yet. Hold a bottle in view of the camera to trigger label extraction and scheduling.
          </div>
        ) : null}

        {medicines.map((medicine) => {
          const nextDose = getNextDose(medicine.reminders);
          const tone = toneForDose(nextDose);

          return (
            <article
              key={medicine.id}
              className={`rounded-[1.75rem] border p-5 ${tone}`}
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.25em] opacity-70">Medication</p>
                  <h3 className="mt-2 text-2xl font-semibold">{medicine.name || "Unknown medicine"}</h3>
                  <p className="mt-2 text-base opacity-80">
                    {medicine.dosage || "Dosage pending"} {medicine.frequency ? `| ${medicine.frequency}` : ""}
                  </p>
                  <p className="mt-3 max-w-2xl text-sm opacity-75">
                    {medicine.instructions || "Instructions will appear here once the label parser extracts them."}
                  </p>
                </div>
                <div className="rounded-[1.25rem] bg-white/80 px-4 py-3 text-sm shadow-sm">
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Next dose</p>
                  <p className="mt-2 text-lg font-semibold text-slate-900">
                    {nextDose ? nextDose.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Not scheduled"}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

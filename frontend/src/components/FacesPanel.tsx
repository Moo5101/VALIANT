"use client";

import { useState } from "react";

import type { KnownFace } from "@/lib/types";

interface FacesPanelProps {
  faces: KnownFace[];
  onLabelFace: (faceId: string, label: string) => void | Promise<void>;
}

export default function FacesPanel({ faces, onLabelFace }: FacesPanelProps) {
  const [draftLabels, setDraftLabels] = useState<Record<string, string>>({});

  return (
    <section className="panel-shell rounded-4xl p-6 sm:p-8">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h2 className="section-title">Familiar Faces</h2>
          <p className="section-copy">Known visitors are auto-learned. Caregivers can promote unknown faces with a label.</p>
        </div>
        <div className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold tracking-[0.25em] text-white">
          {faces.length} seen
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {faces.length === 0 ? (
          <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white/70 p-6 text-slate-600 sm:col-span-2">
            No faces have been captured yet. Once faces are seen, they will appear here for labeling and familiarity tracking.
          </div>
        ) : null}

        {faces.map((face) => {
          const isUnknown = !face.is_familiar || !face.label;

          return (
            <article
              key={face.id}
              className={`overflow-hidden rounded-[1.75rem] border bg-white/80 ${
                isUnknown ? "border-amber-300" : "border-emerald-200"
              }`}
            >
              <div className="aspect-[4/3] bg-slate-200">
                {face.image_url ? (
                  <img
                    src={face.image_url}
                    alt={face.label || "Unknown face"}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm uppercase tracking-[0.35em] text-slate-500">
                    No image
                  </div>
                )}
              </div>
              <div className="space-y-3 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-semibold text-slate-900">
                      {face.label || "Unknown"}
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      {face.is_familiar ? "Familiar visitor" : "Needs caregiver review"}
                    </p>
                  </div>
                  <div
                    className={`rounded-full px-3 py-1 text-xs font-semibold tracking-[0.25em] ${
                      face.is_familiar ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"
                    }`}
                  >
                    {face.times_seen ?? 1} sightings
                  </div>
                </div>

                <label className="block">
                  <span className="mb-2 block text-xs uppercase tracking-[0.25em] text-slate-500">Label</span>
                  <div className="flex gap-2">
                    <input
                      value={draftLabels[face.id] ?? face.label ?? ""}
                      onChange={(event) =>
                        setDraftLabels((current) => ({
                          ...current,
                          [face.id]: event.target.value,
                        }))
                      }
                      placeholder="Name or relationship"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-base text-slate-900 outline-none transition focus:border-slate-500"
                    />
                    <button
                      type="button"
                      onClick={() => void onLabelFace(face.id, draftLabels[face.id] ?? face.label ?? "")}
                      className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
                    >
                      Save
                    </button>
                  </div>
                </label>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

"use client";

import { startTransition, useEffect, useState } from "react";

import type { CameraSource } from "@/lib/types";

interface CameraSourcesPanelProps {
  apiBaseUrl: string;
}

const POLL_INTERVAL_MS = 3000;

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function requiresLanHost(apiBaseUrl: string): boolean {
  try {
    const { hostname } = new URL(apiBaseUrl);
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
  } catch {
    return false;
  }
}

function formatLastSeen(lastSeen?: number | null): string {
  if (!lastSeen) {
    return "No frames yet";
  }

  const elapsedSeconds = Math.max(0, Math.round(Date.now() / 1000 - lastSeen));
  if (elapsedSeconds < 2) {
    return "Just now";
  }
  if (elapsedSeconds < 60) {
    return `${elapsedSeconds}s ago`;
  }

  const elapsedMinutes = Math.round(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes}m ago`;
  }

  const elapsedHours = Math.round(elapsedMinutes / 60);
  return `${elapsedHours}h ago`;
}

export default function CameraSourcesPanel({ apiBaseUrl }: CameraSourcesPanelProps) {
  const [sources, setSources] = useState<CameraSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectUrl, setConnectUrl] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    let cancelled = false;
    let intervalId: number | null = null;

    async function refreshSources(initialLoad: boolean) {
      try {
        const nextSources = await fetchJson<CameraSource[]>(`${apiBaseUrl}/api/camera/sources`);
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setSources(nextSources);
          setError(null);
        });
      } catch (refreshError) {
        if (!cancelled) {
          setError(refreshError instanceof Error ? refreshError.message : "Camera sources could not be loaded.");
        }
      } finally {
        if (initialLoad && !cancelled) {
          setLoading(false);
        }
      }
    }

    void refreshSources(true);
    intervalId = window.setInterval(() => {
      void refreshSources(false);
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [apiBaseUrl]);

  async function reloadSources() {
    const nextSources = await fetchJson<CameraSource[]>(`${apiBaseUrl}/api/camera/sources`);
    startTransition(() => {
      setSources(nextSources);
      setError(null);
    });
  }

  async function handleAddPhoneCamera() {
    setBusy(true);
    setError(null);

    try {
      const source = await fetchJson<CameraSource>(`${apiBaseUrl}/api/camera/sources`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });

      startTransition(() => {
        setConnectUrl(source.connect_url ?? "");
        setCopyState("idle");
      });

      if (source.connect_url) {
        window.open(source.connect_url, "_blank", "noopener,noreferrer");
      }

      await reloadSources();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "A phone camera could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveSource(source: CameraSource) {
    if (!source.disconnect_url) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await fetchJson<{ removed: boolean }>(source.disconnect_url, { method: "DELETE" });
      await reloadSources();
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : "The camera source could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyLink() {
    if (!connectUrl) {
      return;
    }

    try {
      await navigator.clipboard.writeText(connectUrl);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  const lanOnly = requiresLanHost(apiBaseUrl);

  return (
    <section className="panel-shell rounded-4xl p-6 sm:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.35em] text-slate-500">Camera Sources</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
            Monitor every angle from one dashboard.
          </h2>
          <p className="mt-3 max-w-3xl text-base text-slate-600 sm:text-lg">
            The main preview stays large while each camera source keeps its own live stream and detection overlay.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleAddPhoneCamera()}
          disabled={busy}
          className="rounded-full bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {busy ? "Working..." : "Add phone camera"}
        </button>
      </div>

      {lanOnly ? (
        <div className="mt-6 rounded-[1.5rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
          This dashboard is talking to the backend on <code>localhost</code>. That is fine for the laptop UI, but
          phone connect links only work if the backend <code>PUBLIC_API_BASE_URL</code> is set to a reachable LAN or
          Tailscale address and uvicorn is started with <code>--host 0.0.0.0</code>.
        </div>
      ) : null}

      {connectUrl ? (
        <div className="mt-6 rounded-[1.75rem] border border-slate-200 bg-white/80 p-4">
          <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Latest phone link</p>
          <p className="mt-3 break-all text-sm text-slate-700">{connectUrl}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <a
              href={connectUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
            >
              Open connect page
            </a>
            <button
              type="button"
              onClick={() => void handleCopyLink()}
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
            >
              {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy link"}
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-6 rounded-[1.5rem] border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-900">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="mt-6 rounded-[1.75rem] border border-slate-200 bg-white/70 px-5 py-8 text-center text-sm uppercase tracking-[0.25em] text-slate-500">
          Loading camera sources
        </div>
      ) : (
        <div className="mt-6 grid gap-4 xl:grid-cols-2">
          {sources.map((source) => {
            const online = source.status === "online";
            const showStream = Boolean(source.stream_url) && (source.has_frame || online);

            return (
              <article
                key={source.id}
                className="overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white/75 shadow-[0_18px_48px_rgba(15,23,42,0.08)]"
              >
                <div className="flex items-start justify-between gap-4 px-5 pb-4 pt-5">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                      {source.kind === "local" ? "Local camera" : "Phone camera"}
                    </p>
                    <h3 className="mt-2 text-xl font-semibold text-slate-900">{source.name}</h3>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                      source.status === "online"
                        ? "bg-emerald-100 text-emerald-800"
                        : source.status === "connecting"
                          ? "bg-amber-100 text-amber-900"
                          : "bg-slate-200 text-slate-700"
                    }`}
                  >
                    {source.status}
                  </span>
                </div>

                {showStream ? (
                  <img
                    src={source.stream_url}
                    alt={`${source.name} live preview`}
                    className="h-60 w-full bg-slate-950 object-cover"
                  />
                ) : (
                  <div className="flex h-60 items-center justify-center bg-slate-950 px-6 text-center text-sm uppercase tracking-[0.25em] text-white/70">
                    Waiting for a live feed
                  </div>
                )}

                <div className="grid gap-3 px-5 py-5 text-sm text-slate-600 sm:grid-cols-2">
                  <div className="rounded-[1.2rem] bg-slate-100 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Last seen</p>
                    <p className="mt-2 font-medium text-slate-900">{formatLastSeen(source.last_seen)}</p>
                  </div>
                  <div className="rounded-[1.2rem] bg-slate-100 px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Frame size</p>
                    <p className="mt-2 font-medium text-slate-900">
                      {source.width && source.height ? `${source.width} × ${source.height}` : "Pending"}
                    </p>
                  </div>
                </div>

                {source.connect_url ? (
                  <div className="flex flex-wrap gap-3 px-5 pb-5">
                    <a
                      href={source.connect_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
                    >
                      Open connect page
                    </a>
                    <button
                      type="button"
                      onClick={() => void handleRemoveSource(source)}
                      disabled={busy}
                      className="rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-800 transition hover:border-rose-400 hover:text-rose-900 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Remove source
                    </button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

import { createClient, type RealtimePostgresChangesPayload, type SupabaseClient } from "@supabase/supabase-js";

import type { AlertRecord } from "@/lib/types";

let browserClient: SupabaseClient | null = null;

export function getBrowserSupabaseClient(): SupabaseClient | null {
  if (typeof window === "undefined") {
    return null;
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return null;
  }

  if (!browserClient) {
    browserClient = createClient(url, anonKey);
  }

  return browserClient;
}

export function subscribeToAlerts(
  patientId: string,
  onChange: (payload: RealtimePostgresChangesPayload<AlertRecord>) => void,
): () => void {
  const client = getBrowserSupabaseClient();
  if (!client || !patientId) {
    return () => undefined;
  }

  const channel = client
    .channel(`alerts-${patientId}`)
    .on(
      "postgres_changes",
      {
        event: "*",
        schema: "public",
        table: "alerts",
        filter: `patient_id=eq.${patientId}`,
      },
      onChange,
    )
    .subscribe();

  return () => {
    void client.removeChannel(channel);
  };
}

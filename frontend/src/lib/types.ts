export type AlertSeverity = "info" | "warning" | "critical";

export interface Patient {
  id: string;
  name: string;
  phone: string;
  patient_email?: string | null;
  caregiver_name?: string | null;
  caregiver_phone: string;
  caregiver_email?: string | null;
  created_at?: string;
}

export interface Reminder {
  id: string;
  medicine_id: string;
  patient_id: string;
  reminder_time: string;
  days_of_week?: string[];
  is_active?: boolean;
  last_sent_at?: string | null;
  created_at?: string;
}

export interface Medicine {
  id: string;
  patient_id: string;
  name?: string | null;
  dosage?: string | null;
  frequency?: string | null;
  instructions?: string | null;
  image_url?: string | null;
  raw_ocr_text?: string | null;
  detected_at?: string;
  reminders?: Reminder[];
}

export interface KnownFace {
  id: string;
  patient_id: string;
  label?: string | null;
  image_url?: string | null;
  times_seen?: number;
  is_familiar?: boolean;
  first_seen_at?: string;
  last_seen_at?: string;
}

export interface AlertRecord {
  id: string;
  patient_id: string;
  type: "medicine_reminder" | "unfamiliar_face" | "hazard_sos";
  severity: AlertSeverity;
  title: string;
  message?: string | null;
  image_url?: string | null;
  sent_to_patient?: boolean;
  sent_to_caregiver?: boolean;
  acknowledged?: boolean;
  created_at?: string;
}

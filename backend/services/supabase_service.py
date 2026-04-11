from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np

from backend.config import Settings

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover - optional dependency at runtime
    Client = Any  # type: ignore[assignment]
    create_client = None


logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = settings.supabase_storage_bucket
        self.client: Client | None = None

        if settings.supabase_url and settings.supabase_admin_key and create_client:
            self.client = create_client(settings.supabase_url, settings.supabase_admin_key)
        else:
            logger.warning("Supabase is not configured. Backend will run in degraded mode.")

    @property
    def is_enabled(self) -> bool:
        return self.client is not None

    def get_patient(self, patient_id: UUID | str) -> dict[str, Any] | None:
        if not self.client:
            return None
        response = (
            self.client.table("patients")
            .select("*")
            .eq("id", str(patient_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def get_patient_by_phone(self, phone: str) -> dict[str, Any] | None:
        if not self.client or not phone:
            return None
        response = (
            self.client.table("patients")
            .select("*")
            .eq("phone", phone)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def upsert_patient(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.client:
            return payload

        patient_id = payload.get("id")
        if patient_id:
            response = self.client.table("patients").upsert(payload).execute()
            rows = response.data or []
            return rows[0] if rows else None

        existing = self.get_patient_by_phone(str(payload.get("phone") or ""))
        if existing:
            response = (
                self.client.table("patients")
                .update(payload)
                .eq("id", existing["id"])
                .execute()
            )
            rows = response.data or []
            return rows[0] if rows else existing

        response = self.client.table("patients").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def find_medicine_by_name(self, patient_id: UUID | str, name: str) -> dict[str, Any] | None:
        if not self.client or not name:
            return None
        response = (
            self.client.table("medicines")
            .select("*")
            .eq("patient_id", str(patient_id))
            .ilike("name", name)
            .order("detected_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def list_medicines_with_reminders(self, patient_id: UUID | str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        response = (
            self.client.table("medicines")
            .select("*, reminders(*)")
            .eq("patient_id", str(patient_id))
            .order("detected_at", desc=True)
            .execute()
        )
        return response.data or []

    def upsert_medicine(
        self,
        patient_id: UUID | str,
        medicine: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = {
            "patient_id": str(patient_id),
            "name": medicine.get("name"),
            "dosage": medicine.get("dosage"),
            "frequency": medicine.get("frequency"),
            "instructions": medicine.get("instructions"),
            "image_url": medicine.get("image_url"),
            "raw_ocr_text": medicine.get("raw_ocr_text"),
        }
        existing = None
        if payload["name"]:
            existing = self.find_medicine_by_name(patient_id, str(payload["name"]))
        if not self.client:
            return existing or payload
        if existing:
            payload = {
                "patient_id": str(patient_id),
                "name": payload.get("name") or existing.get("name"),
                "dosage": payload.get("dosage") or existing.get("dosage"),
                "frequency": payload.get("frequency") or existing.get("frequency"),
                "instructions": payload.get("instructions") or existing.get("instructions"),
                "image_url": payload.get("image_url") or existing.get("image_url"),
                "raw_ocr_text": payload.get("raw_ocr_text")
                if len(str(payload.get("raw_ocr_text") or "")) >= len(str(existing.get("raw_ocr_text") or ""))
                else existing.get("raw_ocr_text"),
            }
            response = (
                self.client.table("medicines")
                .update(payload)
                .eq("id", existing["id"])
                .execute()
            )
            rows = response.data or []
            return rows[0] if rows else existing
        response = self.client.table("medicines").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def create_reminder(
        self,
        medicine_id: UUID | str,
        patient_id: UUID | str,
        reminder_time: str,
        days_of_week: list[str] | None = None,
        is_active: bool = True,
    ) -> dict[str, Any] | None:
        payload = {
            "medicine_id": str(medicine_id),
            "patient_id": str(patient_id),
            "reminder_time": reminder_time,
            "days_of_week": days_of_week or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "is_active": is_active,
        }
        if not self.client:
            return payload
        response = self.client.table("reminders").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def delete_existing_reminders_for_medicine(self, medicine_id: UUID | str) -> None:
        if not self.client:
            return
        self.client.table("reminders").delete().eq("medicine_id", str(medicine_id)).execute()

    def get_active_reminders(self) -> list[dict[str, Any]]:
        if not self.client:
            return []
        response = (
            self.client.table("reminders")
            .select("*, medicines(name, dosage), patients(name, phone, caregiver_phone)")
            .eq("is_active", True)
            .execute()
        )
        return response.data or []

    def get_reminder(self, reminder_id: UUID | str) -> dict[str, Any] | None:
        if not self.client:
            return None
        response = (
            self.client.table("reminders")
            .select("*, medicines(name, dosage), patients(name, phone, caregiver_phone)")
            .eq("id", str(reminder_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def mark_reminder_sent(self, reminder_id: UUID | str) -> None:
        if not self.client:
            return
        self.client.table("reminders").update({"last_sent_at": datetime.utcnow().isoformat()}).eq(
            "id",
            str(reminder_id),
        ).execute()

    def get_known_faces(self, patient_id: UUID | str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        response = (
            self.client.table("known_faces")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("last_seen_at", desc=True)
            .execute()
        )
        return response.data or []

    def get_face(self, face_id: UUID | str) -> dict[str, Any] | None:
        if not self.client:
            return None
        response = (
            self.client.table("known_faces")
            .select("*")
            .eq("id", str(face_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def upsert_face(
        self,
        patient_id: UUID | str,
        face_encoding: bytes,
        image_url: str | None = None,
        label: str | None = None,
        times_seen: int = 1,
        is_familiar: bool = False,
        face_id: UUID | str | None = None,
    ) -> dict[str, Any] | None:
        payload = {
            "patient_id": str(patient_id),
            "label": label,
            "face_encoding": self.to_bytea_literal(face_encoding),
            "image_url": image_url,
            "times_seen": times_seen,
            "is_familiar": is_familiar,
            "last_seen_at": datetime.utcnow().isoformat(),
        }
        if not self.client:
            payload["id"] = str(face_id) if face_id else None
            return payload
        table = self.client.table("known_faces")
        if face_id:
            response = table.update(payload).eq("id", str(face_id)).execute()
        else:
            response = table.insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def update_face(
        self,
        face_id: UUID | str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.client:
            payload = {"id": str(face_id)}
            payload.update(updates)
            return payload
        response = self.client.table("known_faces").update(updates).eq("id", str(face_id)).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def create_alert(
        self,
        patient_id: UUID | str,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        image_url: str | None = None,
        sent_to_patient: bool = False,
        sent_to_caregiver: bool = False,
    ) -> dict[str, Any] | None:
        payload = {
            "patient_id": str(patient_id),
            "type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "image_url": image_url,
            "sent_to_patient": sent_to_patient,
            "sent_to_caregiver": sent_to_caregiver,
        }
        if not self.client:
            return payload
        response = self.client.table("alerts").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def list_alerts(
        self,
        patient_id: UUID | str,
        limit: int = 25,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not self.client:
            return []
        response = (
            self.client.table("alerts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .range(offset, max(offset + limit - 1, offset))
            .execute()
        )
        return response.data or []

    def acknowledge_alert(self, alert_id: UUID | str) -> dict[str, Any] | None:
        if not self.client:
            return {"id": str(alert_id), "acknowledged": True}
        response = (
            self.client.table("alerts")
            .update({"acknowledged": True})
            .eq("id", str(alert_id))
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def upload_image(
        self,
        image_bytes: bytes,
        object_path: str,
        content_type: str = "image/jpeg",
    ) -> str | None:
        if not self.client:
            return None
        try:
            self.client.storage.from_(self.bucket).upload(
                path=object_path,
                file=image_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Supabase image upload failed for %s: %s", object_path, exc)
            return None
        return f"{self.settings.supabase_url}/storage/v1/object/public/{self.bucket}/{object_path}"

    @staticmethod
    def to_bytea_literal(payload: bytes | np.ndarray) -> str:
        raw = payload.tobytes() if isinstance(payload, np.ndarray) else payload
        return "\\x" + raw.hex()

    @staticmethod
    def from_bytea_literal(value: str | bytes | None) -> bytes:
        if value is None:
            return b""
        if isinstance(value, bytes):
            return value
        return bytes.fromhex(value[2:] if value.startswith("\\x") else value)

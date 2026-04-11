from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import cv2
import numpy as np

from backend.config import Settings
from backend.processing.detector import Detection, Detector
from backend.processing.face_manager import FaceManager, FaceResult
from backend.processing.medicine_ocr import MedicineInfo, MedicineOCR
from backend.services.scheduler import ReminderScheduler
from backend.services.supabase_service import SupabaseService
from backend.services.twilio_service import TwilioService


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessingResult:
    detections: list[Detection]
    medicines: list[dict[str, object]]
    faces: list[FaceResult]
    alerts: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "detections": [item.to_dict() for item in self.detections],
            "medicines": self.medicines,
            "faces": [item.to_dict() for item in self.faces],
            "alerts": self.alerts,
        }


class ProcessingPipeline:
    def __init__(
        self,
        settings: Settings,
        detector: Detector,
        medicine_ocr: MedicineOCR,
        face_manager: FaceManager,
        supabase: SupabaseService,
        twilio: TwilioService,
        scheduler: ReminderScheduler | None = None,
    ) -> None:
        self.settings = settings
        self.detector = detector
        self.medicine_ocr = medicine_ocr
        self.face_manager = face_manager
        self.supabase = supabase
        self.twilio = twilio
        self.scheduler = scheduler
        self.cooldowns: dict[str, float] = {}
        self.last_face_scan_at: dict[str, float] = {}

    def process_frame(self, frame: np.ndarray, patient_id: str) -> ProcessingResult:
        detections = self.detector.detect_objects(frame)
        patient: dict[str, object] | None = None
        patient_name = "the patient"
        medicines: list[dict[str, object]] = []
        alerts: list[dict[str, object]] = []
        faces: list[FaceResult] = []

        medicine_detections = sorted(
            [item for item in detections if item.category == "medicine"],
            key=lambda item: item.confidence,
            reverse=True,
        )
        for detection in medicine_detections[: self.settings.max_medicine_detections_per_frame]:
            medicine = self._handle_medicine_detection(patient_id, detection)
            if medicine:
                medicines.append(medicine)

        hazard_detections = [item for item in detections if item.category == "hazard"]
        for detection in hazard_detections:
            if patient is None:
                patient = self.supabase.get_patient(patient_id)
                patient_name = patient.get("name", "the patient") if patient else "the patient"
            alert = self._handle_hazard_detection(patient_id, patient, patient_name, detection)
            if alert:
                alerts.append(alert)

        if self._should_process_faces(patient_id):
            faces = self.face_manager.process_faces(frame, patient_id)
            for face in faces:
                if patient is None:
                    patient = self.supabase.get_patient(patient_id)
                    patient_name = patient.get("name", "the patient") if patient else "the patient"
                alert = self._handle_unfamiliar_face(patient_id, patient, patient_name, face)
                if alert:
                    alerts.append(alert)

        return ProcessingResult(detections=detections, medicines=medicines, faces=faces, alerts=alerts)

    def _handle_medicine_detection(
        self,
        patient_id: str,
        detection: Detection,
    ) -> dict[str, object] | None:
        scan_key = self._medicine_scan_key(patient_id, detection.cropped_image)
        if scan_key and self._in_cooldown(scan_key, max(self.settings.medicine_scan_interval, 0.25)):
            return None
        if not self._is_medicine_crop_usable(detection.cropped_image):
            return None

        medicine_info = self.medicine_ocr.read_medicine_label(detection.cropped_image)
        if not medicine_info or not medicine_info.name:
            return None
        medicine_info.name = self._normalize_medicine_name(medicine_info.name)
        if not self._is_plausible_medicine_info(medicine_info):
            return None
        existing_medicine = self._find_existing_medicine(patient_id, medicine_info.name)
        if existing_medicine and existing_medicine.get("name"):
            medicine_info.name = self._normalize_medicine_name(str(existing_medicine.get("name") or medicine_info.name))
        cooldown_key = f"medicine:{patient_id}:{self._medicine_name_key(medicine_info.name)}"
        if self._in_cooldown(cooldown_key, self.settings.medicine_cooldown_seconds):
            return None

        image_url = self._upload_detection_crop("medicines", detection.cropped_image)
        medicine_record = self.supabase.upsert_medicine(
            patient_id,
            {
                **medicine_info.to_dict(),
                "image_url": image_url,
            },
        )
        if not medicine_record:
            return None

        reminder_frequency = medicine_info.frequency or str(medicine_record.get("frequency") or "")
        reminder_times = self._derive_reminder_times(reminder_frequency)
        self.supabase.delete_existing_reminders_for_medicine(medicine_record["id"])
        reminders: list[dict[str, object]] = []
        for reminder_time in reminder_times:
            reminder = self.supabase.create_reminder(
                medicine_id=medicine_record["id"],
                patient_id=patient_id,
                reminder_time=reminder_time,
            )
            if reminder:
                reminders.append(reminder)
                if self.scheduler:
                    self.scheduler.add_reminder(reminder)

        payload = dict(medicine_record)
        payload["reminders"] = reminders
        return payload

    def _handle_hazard_detection(
        self,
        patient_id: str,
        patient: dict[str, object] | None,
        patient_name: str,
        detection: Detection,
    ) -> dict[str, object] | None:
        hazard_label = self._normalize_hazard_label(detection.label)
        cooldown_key = f"hazard:{patient_id}:{hazard_label}"
        if self._in_cooldown(cooldown_key, self.settings.alert_cooldown_seconds):
            return None

        image_url = self._upload_detection_crop("hazards", detection.cropped_image)
        patient_body, caregiver_body = self._hazard_messages(hazard_label, patient_name)
        alert = self.supabase.create_alert(
            patient_id=patient_id,
            alert_type="hazard_sos",
            severity="critical",
            title=f"{hazard_label.title()} detected",
            message=caregiver_body,
            image_url=image_url,
            sent_to_patient=bool(patient and patient.get("phone")),
            sent_to_caregiver=bool(patient and patient.get("caregiver_phone")),
        )

        if patient:
            patient_phone = str(patient.get("phone") or "")
            caregiver_phone = str(patient.get("caregiver_phone") or "")
            self.twilio.send_sms(
                patient_phone,
                patient_body,
                cooldown_key=f"{cooldown_key}:patient",
            )
            if image_url:
                self.twilio.send_mms(
                    caregiver_phone,
                    caregiver_body,
                    image_url,
                    cooldown_key=f"{cooldown_key}:caregiver",
                )
            else:
                self.twilio.send_sms(
                    caregiver_phone,
                    caregiver_body,
                    cooldown_key=f"{cooldown_key}:caregiver",
                )

        return alert

    def _handle_unfamiliar_face(
        self,
        patient_id: str,
        patient: dict[str, object] | None,
        patient_name: str,
        face: FaceResult,
    ) -> dict[str, object] | None:
        if not face.unfamiliar:
            return None
        cooldown_key = f"face:{patient_id}:{face.face_id}"
        if self._in_cooldown(cooldown_key, self.settings.face_alert_cooldown_seconds):
            return None

        patient_body = "Unknown person detected nearby"
        caregiver_body = f"Unknown person detected near {patient_name}"
        alert = self.supabase.create_alert(
            patient_id=patient_id,
            alert_type="unfamiliar_face",
            severity="warning",
            title="Unknown person detected nearby",
            message=caregiver_body,
            image_url=face.image_url,
            sent_to_patient=bool(patient and patient.get("phone")),
            sent_to_caregiver=bool(patient and patient.get("caregiver_phone")),
        )

        if patient:
            self.twilio.send_sms(
                str(patient.get("phone") or ""),
                patient_body,
                cooldown_key=f"{cooldown_key}:patient",
            )
            self.twilio.send_sms(
                str(patient.get("caregiver_phone") or ""),
                caregiver_body,
                cooldown_key=f"{cooldown_key}:caregiver",
            )
        return alert

    def _upload_detection_crop(self, prefix: str, image: np.ndarray | None) -> str | None:
        if image is None or not image.size:
            return None
        success, encoded = cv2.imencode(".jpg", image)
        if not success:
            return None
        object_path = f"{prefix}/{datetime.utcnow().strftime('%Y%m%d')}/{uuid4()}.jpg"
        return self.supabase.upload_image(encoded.tobytes(), object_path)

    def _in_cooldown(self, key: str, seconds: float) -> bool:
        now = time.time()
        previous = self.cooldowns.get(key)
        if previous and now - previous < seconds:
            return True
        self.cooldowns[key] = now
        return False

    def _should_process_faces(self, patient_id: str) -> bool:
        now = time.time()
        previous = self.last_face_scan_at.get(patient_id, 0.0)
        if previous and now - previous < self.settings.face_process_interval:
            return False
        self.last_face_scan_at[patient_id] = now
        return True

    @staticmethod
    def _normalize_hazard_label(label: str) -> str:
        lower = label.lower()
        if lower in {"knife", "scissors"}:
            return "sharp object"
        weapon_keywords = ("gun", "weapon", "pistol", "handgun", "rifle", "firearm", "shotgun")
        if any(keyword in lower for keyword in weapon_keywords):
            return "weapon"
        if "fire" in lower:
            return "fire"
        return lower

    @staticmethod
    def _hazard_messages(hazard_label: str, patient_name: str) -> tuple[str, str]:
        if hazard_label == "fire":
            return (
                "Warning: fire detected",
                f"SOS: Fire detected near {patient_name}. 911 should be called.",
            )
        if hazard_label == "weapon":
            return (
                "Warning: weapon detected",
                f"SOS: Weapon detected near {patient_name}. 911 should be called.",
            )
        return (
            "Warning: sharp object detected",
            f"SOS: Sharp object near {patient_name}. 911 should be called.",
        )

    @staticmethod
    def _derive_reminder_times(frequency: str) -> list[str]:
        normalized = (frequency or "").strip().lower()
        explicit_times = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", normalized)
        if explicit_times:
            return [f"{int(hour):02d}:{int(minute):02d}:00" for hour, minute in explicit_times]
        if "three" in normalized or "3" in normalized:
            return ["08:00:00", "14:00:00", "20:00:00"]
        if "twice" in normalized or "2" in normalized:
            return ["09:00:00", "21:00:00"]
        if "morning" in normalized:
            return ["09:00:00"]
        if "evening" in normalized or "bedtime" in normalized:
            return ["20:00:00"]
        if "every 8 hours" in normalized:
            return ["06:00:00", "14:00:00", "22:00:00"]
        if "every 12 hours" in normalized:
            return ["08:00:00", "20:00:00"]
        return ["09:00:00"]

    @staticmethod
    def _medicine_scan_key(patient_id: str, image: np.ndarray | None) -> str | None:
        if image is None or not image.size:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        reduced = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA)
        digest = hashlib.sha1(reduced.tobytes()).hexdigest()[:16]
        return f"medicine-scan:{patient_id}:{digest}"

    @staticmethod
    def _normalize_medicine_name(name: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9/+(). -]+", " ", name)
        normalized = re.sub(r"\s+", " ", normalized).strip(" -")
        return normalized

    @classmethod
    def _medicine_name_key(cls, name: str) -> str:
        normalized = cls._normalize_medicine_name(name).lower()
        normalized = re.sub(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?)\b", " ", normalized)
        normalized = re.sub(r"\b(?:tablet|tablets|tab|tabs|capsule|capsules|caplet|caplets|usp|rx|only)\b", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @classmethod
    def _looks_like_same_medicine(cls, left: str, right: str) -> bool:
        left_key = cls._medicine_name_key(left)
        right_key = cls._medicine_name_key(right)
        if not left_key or not right_key:
            return False
        if left_key == right_key:
            return True
        return left_key in right_key or right_key in left_key

    def _find_existing_medicine(self, patient_id: str, name: str) -> dict[str, object] | None:
        existing = self.supabase.find_medicine_by_name(patient_id, name)
        if existing:
            return existing
        candidate_key = self._medicine_name_key(name)
        if not candidate_key:
            return None
        for record in self.supabase.list_medicines_with_reminders(patient_id):
            record_name = str(record.get("name") or "")
            if self._looks_like_same_medicine(record_name, name):
                return record
        return None

    def _is_medicine_crop_usable(self, image: np.ndarray | None) -> bool:
        if image is None or not image.size:
            return False
        focus_score = self._focus_score(image)
        if focus_score >= self.settings.medicine_focus_threshold:
            return True
        logger.info(
            "Skipping medicine label extraction due to blurry crop (focus %.1f < %.1f)",
            focus_score,
            self.settings.medicine_focus_threshold,
        )
        return False

    @staticmethod
    def _focus_score(image: np.ndarray) -> float:
        if image is None or not image.size:
            return 0.0
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @classmethod
    def _is_plausible_medicine_info(cls, medicine_info: MedicineInfo) -> bool:
        name = cls._normalize_medicine_name(medicine_info.name)
        if len(name) < 3 or len(name) > 48:
            return False
        if len(name.split()) > 6:
            return False
        if not re.search(r"[A-Za-z]{3,}", name):
            return False
        blocked_tokens = {
            "pharmacy",
            "patient",
            "instructions",
            "directions",
            "refill",
            "prescriber",
            "doctor",
            "label",
            "needed",
        }
        lowered_name = name.lower()
        if any(token in lowered_name for token in blocked_tokens):
            return False
        has_structured_signal = bool(medicine_info.dosage or medicine_info.frequency or medicine_info.instructions)
        has_medicine_marker = any(
            marker in medicine_info.raw_ocr_text.lower()
            for marker in ("mg", "mcg", "ml", "tablet", "capsule", "dose", "rx")
        )
        return has_structured_signal or has_medicine_marker

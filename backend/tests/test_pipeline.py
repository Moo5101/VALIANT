from __future__ import annotations

import unittest

import cv2
import numpy as np

from backend.config import get_settings
from backend.processing.detector import Detection
from backend.processing.medicine_ocr import MedicineInfo
from backend.processing.pipeline import ProcessingPipeline


class _StubDetector:
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections

    def detect_objects(self, frame: np.ndarray) -> list[Detection]:
        return list(self._detections)


class _StubMedicineOCR:
    def __init__(self, info: MedicineInfo) -> None:
        self._info = info
        self.calls = 0

    def read_medicine_label(self, cropped_image: np.ndarray | None) -> MedicineInfo | None:
        self.calls += 1
        return self._info if cropped_image is not None else None


class _StubFaceManager:
    def process_faces(self, frame: np.ndarray, patient_id: str) -> list[object]:
        return []


class _StubTwilio:
    def send_sms(self, *args: object, **kwargs: object) -> None:
        return None

    def send_mms(self, *args: object, **kwargs: object) -> None:
        return None


class _StubEmailService:
    def send_email(self, *args: object, **kwargs: object) -> None:
        return None


class _StubScheduler:
    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []

    def add_reminder(self, reminder: dict[str, object]) -> None:
        self.added.append(reminder)


class _StubSupabase:
    def __init__(self) -> None:
        self.medicines: list[dict[str, object]] = []
        self.reminders: list[dict[str, object]] = []

    def get_patient(self, patient_id: str) -> dict[str, str]:
        return {
            "id": patient_id,
            "name": "Test Patient",
            "phone": "+15555550101",
            "patient_email": "patient@example.com",
            "caregiver_phone": "+15555550102",
            "caregiver_email": "caregiver@example.com",
        }

    def find_medicine_by_name(self, patient_id: str, name: str) -> dict[str, object] | None:
        for medicine in self.medicines:
            if medicine.get("patient_id") == patient_id and medicine.get("name") == name:
                return medicine
        return None

    def list_medicines_with_reminders(self, patient_id: str) -> list[dict[str, object]]:
        return [medicine for medicine in self.medicines if medicine.get("patient_id") == patient_id]

    def upload_image(self, payload: bytes, object_path: str) -> str:
        return f"https://example.test/{object_path}"

    def upsert_medicine(self, patient_id: str, medicine: dict[str, object]) -> dict[str, object]:
        existing = self.find_medicine_by_name(patient_id, str(medicine.get("name") or ""))
        if existing:
            existing.update({key: value for key, value in medicine.items() if value not in ("", None)})
            return existing
        record = {"id": f"med-{len(self.medicines) + 1}", "patient_id": patient_id, **medicine}
        self.medicines.append(record)
        return record

    def delete_existing_reminders_for_medicine(self, medicine_id: str) -> None:
        return None

    def create_reminder(
        self,
        medicine_id: str,
        patient_id: str,
        reminder_time: str,
        days_of_week: list[str] | None = None,
        is_active: bool = True,
    ) -> dict[str, object]:
        record = {
            "id": f"rem-{len(self.reminders) + 1}",
            "medicine_id": medicine_id,
            "patient_id": patient_id,
            "reminder_time": reminder_time,
            "days_of_week": days_of_week or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "is_active": is_active,
        }
        self.reminders.append(record)
        return record

    def create_alert(self, **kwargs: object) -> dict[str, object]:
        return dict(kwargs)


class PipelineTests(unittest.TestCase):
    @staticmethod
    def _textured_frame(size: int = 160) -> np.ndarray:
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        for offset in range(0, size, 16):
            color = 255 if (offset // 16) % 2 == 0 else 80
            frame[:, offset:offset + 8] = color
            frame[offset:offset + 8, :] = 255 - color
        cv2.putText(frame, "RX", (20, size // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2, cv2.LINE_AA)
        return frame

    def test_medicine_detection_creates_reminders_and_scheduler_jobs(self) -> None:
        frame = self._textured_frame()
        detection = Detection(
            category="medicine",
            label="bottle",
            confidence=0.91,
            bbox=(10, 10, 120, 140),
            source="yolo",
            cropped_image=frame.copy(),
        )
        medicine_info = MedicineInfo(
            name="Amoxicillin",
            dosage="500 mg",
            frequency="twice daily",
            instructions="take with food",
            raw_ocr_text="Amoxicillin 500 mg take with food twice daily",
        )
        supabase = _StubSupabase()
        scheduler = _StubScheduler()
        pipeline = ProcessingPipeline(
            settings=get_settings(),
            detector=_StubDetector([detection]),
            medicine_ocr=_StubMedicineOCR(medicine_info),
            face_manager=_StubFaceManager(),
            supabase=supabase,
            twilio=_StubTwilio(),
            email_service=_StubEmailService(),
            scheduler=scheduler,
        )

        result = pipeline.process_frame(frame, "patient-1")

        self.assertEqual(len(result.medicines), 1)
        self.assertEqual(len(supabase.medicines), 1)
        self.assertEqual([item["reminder_time"] for item in supabase.reminders], ["09:00:00", "21:00:00"])
        self.assertEqual(len(scheduler.added), 2)

    def test_blurry_medicine_crop_is_skipped_before_ocr(self) -> None:
        sharp_frame = self._textured_frame()
        blurry_crop = cv2.GaussianBlur(sharp_frame, (21, 21), 0)
        detection = Detection(
            category="medicine",
            label="bottle",
            confidence=0.91,
            bbox=(10, 10, 120, 140),
            source="yolo",
            cropped_image=blurry_crop,
        )
        medicine_info = MedicineInfo(
            name="Amoxicillin",
            dosage="500 mg",
            frequency="twice daily",
            instructions="take with food",
            raw_ocr_text="Amoxicillin 500 mg take with food twice daily",
        )
        ocr = _StubMedicineOCR(medicine_info)
        supabase = _StubSupabase()
        pipeline = ProcessingPipeline(
            settings=get_settings().model_copy(update={"medicine_focus_threshold": 400.0}),
            detector=_StubDetector([detection]),
            medicine_ocr=ocr,
            face_manager=_StubFaceManager(),
            supabase=supabase,
            twilio=_StubTwilio(),
            email_service=_StubEmailService(),
            scheduler=_StubScheduler(),
        )

        result = pipeline.process_frame(sharp_frame, "patient-1")

        self.assertEqual(ocr.calls, 0)
        self.assertEqual(result.medicines, [])
        self.assertEqual(supabase.medicines, [])

    def test_similar_medicine_names_update_existing_record_instead_of_creating_duplicates(self) -> None:
        frame = self._textured_frame()
        detection = Detection(
            category="medicine",
            label="bottle",
            confidence=0.91,
            bbox=(10, 10, 120, 140),
            source="yolo",
            cropped_image=frame.copy(),
        )
        supabase = _StubSupabase()
        scheduler = _StubScheduler()
        first_ocr = _StubMedicineOCR(
            MedicineInfo(
                name="Nateglinide Tablets USP",
                dosage="60 mg",
                frequency="daily",
                instructions="take by mouth",
                raw_ocr_text="Nateglinide Tablets USP 60 mg daily",
            )
        )
        settings = get_settings().model_copy(
            update={
                "medicine_cooldown_seconds": 0,
                "medicine_scan_interval": 0,
            },
        )
        pipeline = ProcessingPipeline(
            settings=settings,
            detector=_StubDetector([detection]),
            medicine_ocr=first_ocr,
            face_manager=_StubFaceManager(),
            supabase=supabase,
            twilio=_StubTwilio(),
            email_service=_StubEmailService(),
            scheduler=scheduler,
        )

        pipeline.process_frame(frame, "patient-1")
        pipeline.cooldowns.clear()
        pipeline.medicine_ocr = _StubMedicineOCR(
            MedicineInfo(
                name="Nateglinide",
                dosage="60 mg",
                frequency="",
                instructions="",
                raw_ocr_text="Nateglinide 60 mg",
            )
        )
        second_result = pipeline.process_frame(frame, "patient-1")

        self.assertEqual(len(supabase.medicines), 1)
        self.assertEqual(supabase.medicines[0]["name"], "Nateglinide Tablets USP")
        self.assertEqual(len(second_result.medicines), 1)


if __name__ == "__main__":
    unittest.main()

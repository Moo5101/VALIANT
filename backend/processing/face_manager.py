from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import cv2
import numpy as np

from backend.config import Settings
from backend.services.supabase_service import SupabaseService

try:
    import face_recognition
except Exception:  # pragma: no cover - optional dependency at runtime
    face_recognition = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FaceResult:
    face_id: str
    label: str | None
    is_familiar: bool
    unfamiliar: bool
    image_url: str | None
    bbox: tuple[int, int, int, int]
    times_seen: int

    def to_dict(self) -> dict[str, object]:
        return {
            "face_id": self.face_id,
            "label": self.label,
            "is_familiar": self.is_familiar,
            "unfamiliar": self.unfamiliar,
            "image_url": self.image_url,
            "bbox": list(self.bbox),
            "times_seen": self.times_seen,
        }


class FaceManager:
    def __init__(self, settings: Settings, supabase: SupabaseService) -> None:
        self.settings = settings
        self.supabase = supabase
        self.cache: dict[str, dict[str, object]] = {}
        self.last_refresh_at = datetime.min

    def load_known_faces(self, patient_id: str) -> None:
        self.cache = {}
        for record in self.supabase.get_known_faces(patient_id):
            normalized = dict(record)
            normalized["encoding_vector"] = self._decode_encoding(record.get("face_encoding"))
            self.cache[str(record["id"])] = normalized
        self.last_refresh_at = datetime.utcnow()

    def process_faces(self, frame: np.ndarray, patient_id: str) -> list[FaceResult]:
        if not face_recognition:
            logger.warning("face_recognition is unavailable. Face processing skipped.")
            return []

        self._refresh_if_needed(patient_id)
        scale = self.settings.face_scale_factor if 0 < self.settings.face_scale_factor <= 1 else 1.0
        if scale < 1.0:
            processed_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        else:
            processed_frame = frame
        rgb_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(
            rgb_frame,
            number_of_times_to_upsample=self.settings.face_detection_upsample,
            model="hog",
        )
        encodings = face_recognition.face_encodings(rgb_frame, locations, model="small")
        results: list[FaceResult] = []
        has_familiar_faces = any(bool(record.get("is_familiar")) for record in self.cache.values())

        for (top, right, bottom, left), encoding in zip(locations, encodings):
            if scale < 1.0:
                bbox = (
                    int(left / scale),
                    int(top / scale),
                    int(right / scale),
                    int(bottom / scale),
                )
            else:
                bbox = (left, top, right, bottom)
            cropped_face = self._crop(frame, bbox)
            match = self._find_match(encoding)

            if match:
                updated_result = self._update_known_face(match, encoding, cropped_face)
                results.append(
                    FaceResult(
                        face_id=str(updated_result["id"]),
                        label=updated_result.get("label"),
                        is_familiar=bool(updated_result.get("is_familiar")),
                        unfamiliar=False,
                        image_url=updated_result.get("image_url"),
                        bbox=bbox,
                        times_seen=int(updated_result.get("times_seen", 1)),
                    )
                )
                continue

            new_record = self._create_unknown_face(patient_id, encoding, cropped_face)
            if not new_record:
                continue
            results.append(
                FaceResult(
                    face_id=str(new_record["id"]),
                    label=new_record.get("label"),
                    is_familiar=bool(new_record.get("is_familiar")),
                    unfamiliar=has_familiar_faces,
                    image_url=new_record.get("image_url"),
                    bbox=bbox,
                    times_seen=int(new_record.get("times_seen", 1)),
                )
            )

        return results

    def _update_known_face(
        self,
        record: dict[str, object],
        encoding: np.ndarray,
        cropped_face: np.ndarray | None,
    ) -> dict[str, object]:
        record_id = str(record["id"])
        times_seen = int(record.get("times_seen", 1)) + 1
        is_familiar = bool(record.get("is_familiar")) or times_seen >= self.settings.familiar_threshold
        updates: dict[str, object] = {
            "times_seen": times_seen,
            "is_familiar": is_familiar,
            "last_seen_at": datetime.utcnow().isoformat(),
        }
        if not record.get("image_url") and cropped_face is not None:
            image_url = self._upload_face_image(cropped_face)
            if image_url:
                updates["image_url"] = image_url
        persisted = self.supabase.update_face(record_id, updates) or {"id": record_id, **record, **updates}
        normalized = dict(record)
        normalized.update(persisted)
        normalized["encoding_vector"] = encoding.astype(np.float64)
        self.cache[record_id] = normalized
        return normalized

    def _create_unknown_face(
        self,
        patient_id: str,
        encoding: np.ndarray,
        cropped_face: np.ndarray | None,
    ) -> dict[str, object] | None:
        image_url = self._upload_face_image(cropped_face) if cropped_face is not None else None
        persisted = self.supabase.upsert_face(
            patient_id=patient_id,
            face_encoding=encoding.astype(np.float64).tobytes(),
            image_url=image_url,
            label=None,
            times_seen=1,
            is_familiar=False,
        )
        if not persisted:
            return None
        normalized = dict(persisted)
        normalized["encoding_vector"] = encoding.astype(np.float64)
        self.cache[str(normalized["id"])] = normalized
        return normalized

    def _find_match(self, encoding: np.ndarray) -> dict[str, object] | None:
        if not self.cache:
            return None
        best_record: dict[str, object] | None = None
        best_distance = float("inf")
        for record in self.cache.values():
            vector = record.get("encoding_vector")
            if not isinstance(vector, np.ndarray) or vector.size == 0:
                continue
            distance = float(np.linalg.norm(vector - encoding))
            if distance < best_distance:
                best_distance = distance
                best_record = record
        if best_record and best_distance <= self.settings.face_match_threshold:
            return best_record
        return None

    def _refresh_if_needed(self, patient_id: str) -> None:
        if datetime.utcnow() - self.last_refresh_at > timedelta(seconds=60):
            self.load_known_faces(patient_id)

    def _upload_face_image(self, cropped_face: np.ndarray) -> str | None:
        success, encoded = cv2.imencode(".jpg", cropped_face)
        if not success:
            return None
        object_path = f"faces/{datetime.utcnow().strftime('%Y%m%d')}/{uuid4()}.jpg"
        return self.supabase.upload_image(encoded.tobytes(), object_path)

    @staticmethod
    def _decode_encoding(value: object) -> np.ndarray:
        raw = SupabaseService.from_bytea_literal(value if isinstance(value, (str, bytes)) else None)
        if not raw:
            return np.array([], dtype=np.float64)
        vector = np.frombuffer(raw, dtype=np.float64)
        if vector.size == 128:
            return vector
        vector32 = np.frombuffer(raw, dtype=np.float32)
        return vector32.astype(np.float64) if vector32.size == 128 else np.array([], dtype=np.float64)

    @staticmethod
    def _crop(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray | None:
        left, top, right, bottom = bbox
        cropped = frame[max(top, 0):max(bottom, 0), max(left, 0):max(right, 0)]
        return cropped.copy() if cropped.size else None

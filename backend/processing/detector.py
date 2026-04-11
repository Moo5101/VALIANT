from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np

from backend.config import Settings

try:
    from inference_sdk import InferenceHTTPClient
except Exception:  # pragma: no cover - optional dependency at runtime
    InferenceHTTPClient = None  # type: ignore[assignment]

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional dependency at runtime
    YOLO = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

COCO_CLASS_MAP: dict[int, tuple[str, str]] = {
    0: ("person", "person"),
    39: ("medicine", "bottle"),
    43: ("hazard", "knife"),
    76: ("hazard", "scissors"),
}


@dataclass(slots=True)
class Detection:
    category: str
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    source: str
    cropped_image: np.ndarray | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "bbox": list(self.bbox),
            "source": self.source,
        }


class Detector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.frame_counter = 0
        self._yolo_model = None
        self._roboflow_client = None
        self._yolo_class_ids = sorted(COCO_CLASS_MAP)
        self._roboflow_backoff_until = 0.0

    def startup(self) -> None:
        self._ensure_yolo_model()
        self._ensure_roboflow_client()

    def detect_objects(self, frame: np.ndarray) -> list[Detection]:
        self.frame_counter += 1
        detections: list[Detection] = []
        detections.extend(self._detect_yolo(frame))
        if (
            self.frame_counter % max(self.settings.roboflow_every_n_frames, 1) == 0
            and time.time() >= self._roboflow_backoff_until
        ):
            detections.extend(self._detect_roboflow(frame))
        return detections

    def _detect_yolo(self, frame: np.ndarray) -> list[Detection]:
        self._ensure_yolo_model()
        if not self._yolo_model:
            return []

        detections: list[Detection] = []
        started_at = time.perf_counter()
        try:
            predict_kwargs: dict[str, object] = {
                "source": frame,
                "verbose": False,
                "imgsz": self.settings.yolo_image_size,
                "conf": min(
                    self.settings.yolo_confidence_threshold,
                    self.settings.medicine_confidence_threshold,
                ),
                "classes": self._yolo_class_ids,
                "max_det": self.settings.yolo_max_det,
                "stream": False,
            }
            if self.settings.yolo_half:
                predict_kwargs["half"] = True
            results = self._yolo_model.predict(**predict_kwargs)
        except Exception as exc:  # pragma: no cover - runtime model issue
            logger.warning("YOLO inference failed: %s", exc)
            return []

        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0].item())
                if class_id not in COCO_CLASS_MAP:
                    continue
                confidence = float(box.conf[0].item())
                category, label = COCO_CLASS_MAP[class_id]
                if confidence < self._confidence_threshold(category):
                    continue
                x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                bbox = self._clip_bbox(frame, (x1, y1, x2, y2))
                crop_bbox = self._expand_bbox(frame, bbox, self._crop_padding(category))
                detections.append(
                    Detection(
                        category=category,
                        label=label,
                        confidence=confidence,
                        bbox=bbox,
                        source="yolo",
                        cropped_image=self._crop(frame, crop_bbox),
                    )
                )
        logger.debug("YOLO returned %s detections in %.3fs", len(detections), time.perf_counter() - started_at)
        return detections

    def _detect_roboflow(self, frame: np.ndarray) -> list[Detection]:
        self._ensure_roboflow_client()
        if not self._roboflow_client:
            return []

        detections: list[Detection] = []
        for model_id, hazard_label in (
            (self.settings.roboflow_fire_model_id, "fire"),
            (self.settings.roboflow_gun_model_id, "gun"),
        ):
            try:
                result = self._roboflow_client.infer(frame, model_id=model_id)
            except Exception as exc:  # pragma: no cover - network side effect
                logger.warning("Roboflow inference failed for %s: %s", model_id, exc)
                message = str(exc).lower()
                if "403" in message or "forbidden" in message:
                    self._roboflow_backoff_until = time.time() + 3600
                    logger.warning("Roboflow disabled for one hour after authorization failure.")
                else:
                    self._roboflow_backoff_until = time.time() + 60
                continue

            predictions = self._extract_predictions(result)
            for prediction in predictions:
                confidence = float(prediction.get("confidence", 0.0))
                if confidence < self.settings.roboflow_hazard_confidence_threshold:
                    continue
                bbox = self._bbox_from_center_width_height(
                    frame,
                    float(prediction.get("x", 0.0)),
                    float(prediction.get("y", 0.0)),
                    float(prediction.get("width", 0.0)),
                    float(prediction.get("height", 0.0)),
                )
                label = str(prediction.get("class") or hazard_label)
                detections.append(
                    Detection(
                        category="hazard",
                        label=label,
                        confidence=confidence,
                        bbox=bbox,
                        source="roboflow",
                        cropped_image=self._crop(frame, bbox),
                    )
                )
        return detections

    def _ensure_yolo_model(self) -> None:
        if self._yolo_model is not None or not YOLO:
            return
        try:
            self._yolo_model = YOLO(self.settings.yolo_model)
            warmup_frame = np.zeros(
                (self.settings.yolo_image_size, self.settings.yolo_image_size, 3),
                dtype=np.uint8,
            )
            warmup_kwargs: dict[str, object] = {
                "source": warmup_frame,
                "verbose": False,
                "imgsz": self.settings.yolo_image_size,
                "classes": self._yolo_class_ids,
                "max_det": 1,
                "stream": False,
            }
            if self.settings.yolo_half:
                warmup_kwargs["half"] = True
            self._yolo_model.predict(**warmup_kwargs)
        except Exception as exc:  # pragma: no cover - runtime model load issue
            logger.warning("YOLO model could not be loaded: %s", exc)
            self._yolo_model = None

    def _ensure_roboflow_client(self) -> None:
        if self._roboflow_client is not None or not InferenceHTTPClient or not self.settings.roboflow_api_key:
            return
        try:
            self._roboflow_client = InferenceHTTPClient(
                api_url=self.settings.roboflow_api_url,
                api_key=self.settings.roboflow_api_key,
            )
        except Exception as exc:  # pragma: no cover - runtime client init issue
            logger.warning("Roboflow client could not be initialized: %s", exc)
            self._roboflow_client = None

    @staticmethod
    def _extract_predictions(result: object) -> list[dict[str, object]]:
        if isinstance(result, dict):
            predictions = result.get("predictions")
            if isinstance(predictions, list):
                return [prediction for prediction in predictions if isinstance(prediction, dict)]
        if isinstance(result, list):
            flattened: list[dict[str, object]] = []
            for item in result:
                flattened.extend(Detector._extract_predictions(item))
            return flattened
        return []

    @staticmethod
    def _clip_bbox(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        return (
            max(0, min(x1, width - 1)),
            max(0, min(y1, height - 1)),
            max(0, min(x2, width)),
            max(0, min(y2, height)),
        )

    @classmethod
    def _expand_bbox(
        cls,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
        padding_ratio: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = bbox
        width = max(x2 - x1, 1)
        height = max(y2 - y1, 1)
        padding_x = int(width * padding_ratio)
        padding_y = int(height * padding_ratio)
        return cls._clip_bbox(frame, (x1 - padding_x, y1 - padding_y, x2 + padding_x, y2 + padding_y))

    @classmethod
    def _bbox_from_center_width_height(
        cls,
        frame: np.ndarray,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
    ) -> tuple[int, int, int, int]:
        x1 = int(center_x - width / 2)
        y1 = int(center_y - height / 2)
        x2 = int(center_x + width / 2)
        y2 = int(center_y + height / 2)
        return cls._clip_bbox(frame, (x1, y1, x2, y2))

    @staticmethod
    def _crop(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray | None:
        x1, y1, x2, y2 = bbox
        cropped = frame[y1:y2, x1:x2]
        return cropped.copy() if cropped.size else None

    def _confidence_threshold(self, category: str) -> float:
        if category == "medicine":
            return self.settings.medicine_confidence_threshold
        if category == "person":
            return self.settings.person_confidence_threshold
        return self.settings.hazard_confidence_threshold

    def _crop_padding(self, category: str) -> float:
        if category == "medicine":
            return self.settings.medicine_crop_padding
        return 0.08

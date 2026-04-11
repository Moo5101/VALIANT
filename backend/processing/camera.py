from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator

import cv2
import numpy as np

from backend.config import Settings
from backend.processing.pipeline import ProcessingPipeline


logger = logging.getLogger(__name__)


class CameraProcessor:
    def __init__(self, settings: Settings, pipeline: ProcessingPipeline) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.stop_event = threading.Event()
        self.capture_thread: threading.Thread | None = None
        self.process_thread: threading.Thread | None = None
        self.latest_frame: np.ndarray | None = None
        self.latest_frame_jpeg: bytes | None = None
        self.latest_frame_seq = 0
        self.latest_preview_seq = 0
        self.latest_overlay_items: list[dict[str, object]] = []
        self.latest_overlay_source_shape: tuple[int, int] | None = None
        self.patient_id: str | None = None
        self.lock = threading.Lock()
        self.frame_ready = threading.Condition(self.lock)

    def start(self, patient_id: str | None) -> None:
        if self.capture_thread and self.capture_thread.is_alive():
            return
        self.patient_id = patient_id
        self.stop_event.clear()
        self.capture_thread = threading.Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, name="camera-process", daemon=True)
        self.capture_thread.start()
        self.process_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.frame_ready:
            self.frame_ready.notify_all()
        for thread in (self.capture_thread, self.process_thread):
            if thread and thread.is_alive():
                thread.join(timeout=5)

    def set_patient_id(self, patient_id: str | None) -> None:
        with self.frame_ready:
            self.patient_id = patient_id
            if patient_id is None:
                self.latest_overlay_items = []
                self.latest_overlay_source_shape = None
            self.frame_ready.notify_all()

    def get_latest_frame_jpeg(self) -> bytes | None:
        with self.lock:
            return self.latest_frame_jpeg

    def iter_mjpeg_stream(self) -> Iterator[bytes]:
        last_preview_seq = 0
        throttle_seconds = 1 / max(self.settings.camera_preview_fps, 1.0)
        while not self.stop_event.is_set():
            payload: bytes | None = None
            with self.lock:
                if self.latest_frame_jpeg and self.latest_preview_seq != last_preview_seq:
                    payload = self.latest_frame_jpeg
                    last_preview_seq = self.latest_preview_seq
            if payload is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-cache\r\n\r\n"
                    + payload
                    + b"\r\n"
                )
            time.sleep(throttle_seconds)

    def _capture_loop(self) -> None:
        capture = cv2.VideoCapture(self.settings.camera_index)
        self._configure_capture(capture)
        if not capture.isOpened():
            logger.warning("Webcam %s could not be opened.", self.settings.camera_index)
            return

        last_preview_encode_at = 0.0
        try:
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    time.sleep(0.1)
                    continue

                now = time.time()
                preview_bytes: bytes | None = None
                if now - last_preview_encode_at >= 1 / max(self.settings.camera_preview_fps, 1.0):
                    with self.lock:
                        overlay_items = [dict(item) for item in self.latest_overlay_items]
                        overlay_source_shape = self.latest_overlay_source_shape
                    preview_bytes = self._encode_preview(
                        frame,
                        overlay_items=overlay_items,
                        overlay_source_shape=overlay_source_shape,
                    )
                    last_preview_encode_at = now

                with self.frame_ready:
                    self.latest_frame = frame
                    self.latest_frame_seq += 1
                    if preview_bytes is not None:
                        self.latest_frame_jpeg = preview_bytes
                        self.latest_preview_seq += 1
                    self.frame_ready.notify_all()
        finally:
            capture.release()

    def _process_loop(self) -> None:
        last_processed_seq = 0
        last_processed_at = 0.0
        while not self.stop_event.is_set():
            with self.frame_ready:
                self.frame_ready.wait_for(
                    lambda: self.stop_event.is_set()
                    or (self.latest_frame is not None and self.latest_frame_seq != last_processed_seq),
                    timeout=0.25,
                )
                if self.stop_event.is_set():
                    return

                patient_id = self.patient_id
                frame_seq = self.latest_frame_seq
                frame = self.latest_frame.copy() if self.latest_frame is not None else None

            if frame is None:
                continue
            if not patient_id:
                last_processed_seq = frame_seq
                continue

            elapsed = time.time() - last_processed_at
            if elapsed < self.settings.frame_interval:
                time.sleep(self.settings.frame_interval - elapsed)
                continue

            last_processed_seq = frame_seq
            last_processed_at = time.time()
            try:
                result = self.pipeline.process_frame(frame, patient_id)
                self._update_overlay_state(frame, result)
            except Exception as exc:  # pragma: no cover - runtime camera loop issue
                logger.exception("Frame processing failed: %s", exc)

    def _configure_capture(self, capture: cv2.VideoCapture) -> None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
        capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self.settings.camera_buffer_size)

    def _update_overlay_state(self, frame: np.ndarray, result: object) -> None:
        overlay_items: list[dict[str, object]] = []

        detections = getattr(result, "detections", []) or []
        for detection in detections:
            category = getattr(detection, "category", None)
            if category == "medicine":
                overlay_items.append(
                    {
                        "bbox": tuple(getattr(detection, "bbox", (0, 0, 0, 0))),
                        "label": "Medicine",
                        "color": (94, 197, 34),
                    }
                )
                continue
            if category == "hazard":
                overlay_items.append(
                    {
                        "bbox": tuple(getattr(detection, "bbox", (0, 0, 0, 0))),
                        "label": self._hazard_overlay_label(str(getattr(detection, "label", "") or "")),
                        "color": (45, 52, 209),
                    }
                )

        faces = getattr(result, "faces", []) or []
        for face in faces:
            label = getattr(face, "label", None) or ("Unknown face" if getattr(face, "unfamiliar", False) else "Face")
            overlay_items.append(
                {
                    "bbox": tuple(getattr(face, "bbox", (0, 0, 0, 0))),
                    "label": str(label),
                    "color": (11, 158, 245) if getattr(face, "unfamiliar", False) else (246, 130, 59),
                }
            )

        with self.lock:
            self.latest_overlay_items = overlay_items
            self.latest_overlay_source_shape = frame.shape[:2]

    @staticmethod
    def _encode_preview(
        frame: np.ndarray,
        overlay_items: list[dict[str, object]] | None = None,
        overlay_source_shape: tuple[int, int] | None = None,
    ) -> bytes | None:
        height, width = frame.shape[:2]
        preview = frame.copy()
        if width > 960:
            scale = 960 / width
            preview = cv2.resize(preview, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if overlay_items:
            CameraProcessor._draw_overlay_items(
                preview,
                overlay_items,
                overlay_source_shape or frame.shape[:2],
            )
        ok, buffer = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buffer.tobytes() if ok else None

    @staticmethod
    def _draw_overlay_items(
        preview: np.ndarray,
        overlay_items: list[dict[str, object]],
        overlay_source_shape: tuple[int, int],
    ) -> None:
        source_height, source_width = overlay_source_shape
        preview_height, preview_width = preview.shape[:2]
        scale_x = preview_width / max(source_width, 1)
        scale_y = preview_height / max(source_height, 1)

        for item in overlay_items:
            raw_bbox = item.get("bbox")
            if not isinstance(raw_bbox, tuple) or len(raw_bbox) != 4:
                continue
            x1, y1, x2, y2 = raw_bbox
            max_left = max(preview_width - 2, 0)
            max_top = max(preview_height - 2, 0)
            left = max(0, min(int(round(x1 * scale_x)), max_left))
            top = max(0, min(int(round(y1 * scale_y)), max_top))
            right = min(preview_width - 1, max(left + 1, int(round(x2 * scale_x))))
            bottom = min(preview_height - 1, max(top + 1, int(round(y2 * scale_y))))

            color = item.get("color")
            if not isinstance(color, tuple) or len(color) != 3:
                color = (255, 255, 255)
            label = str(item.get("label") or "").strip()

            cv2.rectangle(preview, (left, top), (right, bottom), color, 2)

            if not label:
                continue

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.52
            thickness = 1
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            banner_top = max(0, top - text_height - baseline - 10)
            banner_bottom = min(preview_height - 1, top)
            banner_right = min(preview_width - 1, left + text_width + 10)
            if banner_bottom <= banner_top:
                banner_bottom = min(preview_height - 1, banner_top + text_height + baseline + 10)

            cv2.rectangle(preview, (left, banner_top), (banner_right, banner_bottom), color, thickness=-1)
            text_y = min(preview_height - baseline - 1, banner_bottom - baseline - 4)
            cv2.putText(
                preview,
                label,
                (left + 5, text_y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA,
            )

    @staticmethod
    def _hazard_overlay_label(label: str) -> str:
        lowered = label.lower()
        if any(keyword in lowered for keyword in ("gun", "weapon", "pistol", "handgun", "rifle", "shotgun", "firearm")):
            return "Weapon"
        if lowered in {"knife", "scissors"}:
            return "Sharp object"
        if "fire" in lowered:
            return "Fire"
        return label.title() or "Hazard"

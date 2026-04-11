from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import cv2
import numpy as np

from backend.config import Settings
from backend.processing.pipeline import ProcessingPipeline


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CameraSourceState:
    source_id: str
    name: str
    kind: str
    status: str = "offline"
    last_seen: float = 0.0
    frame: np.ndarray | None = None
    frame_seq: int = 0
    preview_jpeg: bytes | None = None
    preview_seq: int = 0
    overlay_items: list[dict[str, object]] = field(default_factory=list)
    overlay_version: int = 0
    source_shape: tuple[int, int] | None = None
    last_processed_seq: int = 0
    last_processed_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        height = self.source_shape[0] if self.source_shape else None
        width = self.source_shape[1] if self.source_shape else None
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "last_seen": self.last_seen or None,
            "has_frame": self.frame is not None and bool(self.frame.size),
            "width": width,
            "height": height,
        }


class CameraProcessor:
    LOCAL_SOURCE_ID = "local-camera"

    def __init__(self, settings: Settings, pipeline: ProcessingPipeline) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.stop_event = threading.Event()
        self.capture_thread: threading.Thread | None = None
        self.preview_thread: threading.Thread | None = None
        self.process_thread: threading.Thread | None = None
        self.latest_frame_jpeg: bytes | None = None
        self.latest_preview_seq = 0
        self.patient_id: str | None = None
        self.sources: dict[str, CameraSourceState] = {
            self.LOCAL_SOURCE_ID: CameraSourceState(
                source_id=self.LOCAL_SOURCE_ID,
                name="Laptop Camera",
                kind="local",
            )
        }
        self.lock = threading.Lock()
        self.frame_ready = threading.Condition(self.lock)

    def start(self, patient_id: str | None) -> None:
        if self.preview_thread and self.preview_thread.is_alive():
            return
        self.patient_id = patient_id
        self.stop_event.clear()
        self.capture_thread = threading.Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self.preview_thread = threading.Thread(target=self._preview_loop, name="camera-preview", daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, name="camera-process", daemon=True)
        self.capture_thread.start()
        self.preview_thread.start()
        self.process_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.frame_ready:
            self.frame_ready.notify_all()
        for thread in (self.capture_thread, self.preview_thread, self.process_thread):
            if thread and thread.is_alive():
                thread.join(timeout=5)

    def set_patient_id(self, patient_id: str | None) -> None:
        with self.frame_ready:
            self.patient_id = patient_id
            for source in self.sources.values():
                source.overlay_items = []
                source.overlay_version += 1
                source.last_processed_seq = 0
                source.last_processed_at = 0.0
            self.frame_ready.notify_all()

    def get_latest_frame_jpeg(self) -> bytes | None:
        with self.lock:
            return self.latest_frame_jpeg

    def get_source_frame_jpeg(self, source_id: str) -> bytes | None:
        with self.lock:
            source = self.sources.get(source_id)
            return source.preview_jpeg if source else None

    def list_sources(self) -> list[dict[str, object]]:
        with self.frame_ready:
            self._expire_stale_sources_locked(time.time())
            sources = [source.to_dict() for source in self._ordered_sources_locked()]
        return sources

    def register_remote_source(self, name: str) -> dict[str, object]:
        with self.frame_ready:
            remote_count = sum(1 for source in self.sources.values() if source.kind == "remote-phone")
            source_id = uuid4().hex[:8]
            source = CameraSourceState(
                source_id=source_id,
                name=name.strip() or f"Phone Camera {remote_count + 1}",
                kind="remote-phone",
                status="connecting",
                last_seen=time.time(),
            )
            self.sources[source_id] = source
            self.frame_ready.notify_all()
            return source.to_dict()

    def disconnect_source(self, source_id: str) -> bool:
        if source_id == self.LOCAL_SOURCE_ID:
            return False
        with self.frame_ready:
            removed = self.sources.pop(source_id, None)
            self.frame_ready.notify_all()
        return removed is not None

    def update_remote_source_frame(self, source_id: str, image_bytes: bytes) -> dict[str, object] | None:
        frame = self._decode_image(image_bytes)
        if frame is None:
            return None

        with self.frame_ready:
            source = self.sources.get(source_id)
            if not source or source.kind != "remote-phone":
                return None
            self._set_source_frame_locked(source, frame)
            self.frame_ready.notify_all()
            return source.to_dict()

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
                yield self._multipart_jpeg(payload)
            time.sleep(throttle_seconds)

    def iter_source_mjpeg_stream(self, source_id: str) -> Iterator[bytes]:
        last_preview_seq = 0
        throttle_seconds = 1 / max(self.settings.camera_preview_fps, 1.0)
        while not self.stop_event.is_set():
            payload: bytes | None = None
            with self.lock:
                source = self.sources.get(source_id)
                if source and source.preview_jpeg and source.preview_seq != last_preview_seq:
                    payload = source.preview_jpeg
                    last_preview_seq = source.preview_seq
            if payload is not None:
                yield self._multipart_jpeg(payload)
            time.sleep(throttle_seconds)

    def _capture_loop(self) -> None:
        if self.settings.camera_index < 0:
            logger.info("Local laptop camera disabled because CAMERA_INDEX is < 0.")
            return

        capture = cv2.VideoCapture(self.settings.camera_index)
        self._configure_capture(capture)
        if not capture.isOpened():
            logger.warning("Webcam %s could not be opened.", self.settings.camera_index)
            with self.frame_ready:
                local_source = self.sources[self.LOCAL_SOURCE_ID]
                local_source.status = "offline"
                self.frame_ready.notify_all()
            return

        try:
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    time.sleep(0.1)
                    continue
                with self.frame_ready:
                    self._set_source_frame_locked(self.sources[self.LOCAL_SOURCE_ID], frame)
                    self.frame_ready.notify_all()
        finally:
            capture.release()

    def _preview_loop(self) -> None:
        last_signature: tuple[tuple[object, ...], ...] | None = None
        throttle_seconds = 1 / max(self.settings.camera_preview_fps, 1.0)

        while not self.stop_event.is_set():
            now = time.time()
            with self.frame_ready:
                self._expire_stale_sources_locked(now)
                source_snapshots = self._snapshot_sources_locked()

            signature = tuple(
                (
                    snapshot["source_id"],
                    snapshot["status"],
                    snapshot["frame_seq"],
                    snapshot["overlay_version"],
                    snapshot["name"],
                )
                for snapshot in source_snapshots
            )
            if signature != last_signature:
                composite_preview = self._build_composite_preview(source_snapshots)
                source_previews: dict[str, bytes | None] = {
                    snapshot["source_id"]: self._build_source_preview(snapshot)
                    for snapshot in source_snapshots
                }
                with self.frame_ready:
                    self.latest_frame_jpeg = composite_preview
                    self.latest_preview_seq += 1
                    for source_id, preview in source_previews.items():
                        source = self.sources.get(source_id)
                        if not source:
                            continue
                        source.preview_jpeg = preview
                        source.preview_seq += 1
                    self.frame_ready.notify_all()
                last_signature = signature

            time.sleep(throttle_seconds)

    def _process_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.frame_ready:
                self.frame_ready.wait(timeout=0.25)
                patient_id = self.patient_id
                process_targets = self._processing_targets_locked(patient_id)

            if not patient_id:
                continue

            for source_id, frame, frame_seq in process_targets:
                try:
                    result = self.pipeline.process_frame(frame, patient_id)
                    overlay_items = self._build_overlay_items(result)
                except Exception as exc:  # pragma: no cover - runtime camera loop issue
                    logger.exception("Frame processing failed for %s: %s", source_id, exc)
                    continue

                with self.frame_ready:
                    source = self.sources.get(source_id)
                    if not source or source.frame_seq < frame_seq:
                        continue
                    source.overlay_items = overlay_items
                    source.overlay_version += 1
                    source.last_processed_seq = frame_seq
                    source.last_processed_at = time.time()
                    self.frame_ready.notify_all()

    def _processing_targets_locked(self, patient_id: str | None) -> list[tuple[str, np.ndarray, int]]:
        if not patient_id:
            return []
        now = time.time()
        targets: list[tuple[str, np.ndarray, int]] = []
        for source in self.sources.values():
            if source.status != "online" or source.frame is None:
                continue
            if source.frame_seq == source.last_processed_seq:
                continue
            if now - source.last_processed_at < self.settings.frame_interval:
                continue
            targets.append((source.source_id, source.frame.copy(), source.frame_seq))
        return targets

    def _ordered_sources_locked(self) -> list[CameraSourceState]:
        return sorted(
            self.sources.values(),
            key=lambda source: (
                0 if source.source_id == self.LOCAL_SOURCE_ID else 1,
                source.name.lower(),
                source.source_id,
            ),
        )

    def _snapshot_sources_locked(self) -> list[dict[str, object]]:
        snapshots: list[dict[str, object]] = []
        for source in self._ordered_sources_locked():
            snapshots.append(
                {
                    "source_id": source.source_id,
                    "name": source.name,
                    "kind": source.kind,
                    "status": source.status,
                    "last_seen": source.last_seen,
                    "frame": source.frame,
                    "frame_seq": source.frame_seq,
                    "overlay_items": [dict(item) for item in source.overlay_items],
                    "overlay_version": source.overlay_version,
                    "source_shape": source.source_shape,
                }
            )
        return snapshots

    def _expire_stale_sources_locked(self, now: float) -> None:
        timeout_seconds = max(self.settings.remote_camera_timeout_seconds, 1.0)
        for source in self.sources.values():
            if source.kind != "remote-phone" or source.status == "offline" or not source.last_seen:
                continue
            if now - source.last_seen <= timeout_seconds:
                continue
            source.status = "offline"
            source.overlay_items = []
            source.overlay_version += 1

    def _set_source_frame_locked(self, source: CameraSourceState, frame: np.ndarray) -> None:
        source.frame = frame.copy()
        source.frame_seq += 1
        source.status = "online"
        source.last_seen = time.time()
        source.source_shape = frame.shape[:2]

    def _build_source_preview(self, snapshot: dict[str, object]) -> bytes | None:
        frame = snapshot.get("frame")
        source_shape = snapshot.get("source_shape")
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            return None
        overlay_items = snapshot.get("overlay_items")
        encoded = self._encode_preview(
            frame,
            overlay_items=overlay_items if isinstance(overlay_items, list) else None,
            overlay_source_shape=source_shape if isinstance(source_shape, tuple) else frame.shape[:2],
        )
        return encoded

    def _build_composite_preview(self, source_snapshots: list[dict[str, object]]) -> bytes | None:
        active_snapshots = [
            snapshot
            for snapshot in source_snapshots
            if snapshot.get("status") == "online"
            and isinstance(snapshot.get("frame"), np.ndarray)
            and bool(snapshot["frame"].size)
        ]
        if not active_snapshots:
            return None

        composite_frame, layouts = self._compose_sources_frame(active_snapshots)
        self._draw_source_chrome(composite_frame, active_snapshots, layouts)
        overlay_items = self._compose_overlay_items(active_snapshots, layouts)
        return self._encode_preview(
            composite_frame,
            overlay_items=overlay_items,
            overlay_source_shape=composite_frame.shape[:2],
        )

    def _compose_sources_frame(
        self,
        source_snapshots: list[dict[str, object]],
    ) -> tuple[np.ndarray, dict[str, dict[str, float]]]:
        count = len(source_snapshots)
        if count == 1:
            frame = source_snapshots[0]["frame"]
            if not isinstance(frame, np.ndarray):
                raise ValueError("Composite preview requires a source frame.")
            height, width = frame.shape[:2]
            return frame.copy(), {
                str(source_snapshots[0]["source_id"]): {
                    "content_x": 0.0,
                    "content_y": 0.0,
                    "content_width": float(width),
                    "content_height": float(height),
                    "tile_x": 0.0,
                    "tile_y": 0.0,
                    "tile_width": float(width),
                    "tile_height": float(height),
                }
            }

        columns = min(self.settings.camera_grid_max_columns, max(1, math.ceil(math.sqrt(count))))
        rows = math.ceil(count / columns)
        tile_width = self.settings.camera_tile_width
        tile_height = self.settings.camera_tile_height
        composite = np.zeros((rows * tile_height, columns * tile_width, 3), dtype=np.uint8)
        composite[:] = (16, 19, 24)
        layouts: dict[str, dict[str, float]] = {}

        for index, snapshot in enumerate(source_snapshots):
            frame = snapshot.get("frame")
            if not isinstance(frame, np.ndarray) or not frame.size:
                continue
            row = index // columns
            column = index % columns
            tile_x = column * tile_width
            tile_y = row * tile_height
            resized, content_x, content_y, content_width, content_height = self._fit_frame_into_tile(
                frame,
                tile_width,
                tile_height,
            )
            composite[tile_y:tile_y + tile_height, tile_x:tile_x + tile_width] = (8, 12, 18)
            composite[
                tile_y + content_y:tile_y + content_y + content_height,
                tile_x + content_x:tile_x + content_x + content_width,
            ] = resized
            layouts[str(snapshot["source_id"])] = {
                "content_x": float(tile_x + content_x),
                "content_y": float(tile_y + content_y),
                "content_width": float(content_width),
                "content_height": float(content_height),
                "tile_x": float(tile_x),
                "tile_y": float(tile_y),
                "tile_width": float(tile_width),
                "tile_height": float(tile_height),
            }

        return composite, layouts

    def _compose_overlay_items(
        self,
        source_snapshots: list[dict[str, object]],
        layouts: dict[str, dict[str, float]],
    ) -> list[dict[str, object]]:
        overlay_items: list[dict[str, object]] = []

        for snapshot in source_snapshots:
            layout = layouts.get(str(snapshot["source_id"]))
            frame = snapshot.get("frame")
            source_shape = snapshot.get("source_shape")
            raw_overlay_items = snapshot.get("overlay_items")
            if (
                layout is None
                or not isinstance(frame, np.ndarray)
                or not isinstance(raw_overlay_items, list)
                or not raw_overlay_items
            ):
                continue

            source_height, source_width = source_shape if isinstance(source_shape, tuple) else frame.shape[:2]
            if source_width <= 0 or source_height <= 0:
                continue
            scale_x = float(layout["content_width"]) / float(source_width)
            scale_y = float(layout["content_height"]) / float(source_height)
            offset_x = float(layout["content_x"])
            offset_y = float(layout["content_y"])

            for item in raw_overlay_items:
                raw_bbox = item.get("bbox")
                if not isinstance(raw_bbox, tuple) or len(raw_bbox) != 4:
                    continue
                x1, y1, x2, y2 = raw_bbox
                overlay_items.append(
                    {
                        "bbox": (
                            int(round(offset_x + x1 * scale_x)),
                            int(round(offset_y + y1 * scale_y)),
                            int(round(offset_x + x2 * scale_x)),
                            int(round(offset_y + y2 * scale_y)),
                        ),
                        "label": item.get("label"),
                        "color": item.get("color"),
                    }
                )

        return overlay_items

    def _draw_source_chrome(
        self,
        composite: np.ndarray,
        source_snapshots: list[dict[str, object]],
        layouts: dict[str, dict[str, float]],
    ) -> None:
        for snapshot in source_snapshots:
            layout = layouts.get(str(snapshot["source_id"]))
            if layout is None:
                continue

            tile_x = int(layout["tile_x"])
            tile_y = int(layout["tile_y"])
            tile_width = int(layout["tile_width"])
            tile_height = int(layout["tile_height"])
            status = str(snapshot.get("status") or "offline")
            name = str(snapshot.get("name") or "Camera")
            border_color = (84, 211, 138) if status == "online" else (120, 127, 140)

            cv2.rectangle(
                composite,
                (tile_x + 1, tile_y + 1),
                (tile_x + tile_width - 2, tile_y + tile_height - 2),
                border_color,
                2,
            )

            label = name if status == "online" else f"{name} (offline)"
            self._draw_label_banner(
                composite,
                label,
                (tile_x + 14, tile_y + 18),
                background_color=(18, 30, 46),
            )

    def _configure_capture(self, capture: cv2.VideoCapture) -> None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
        capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self.settings.camera_buffer_size)

    @staticmethod
    def _decode_image(image_bytes: bytes) -> np.ndarray | None:
        if not image_bytes:
            return None
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        if not array.size:
            return None
        decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if decoded is None or not decoded.size:
            return None
        return decoded

    @staticmethod
    def _build_overlay_items(result: object) -> list[dict[str, object]]:
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
                        "label": CameraProcessor._hazard_overlay_label(str(getattr(detection, "label", "") or "")),
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

        return overlay_items

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
            CameraProcessor._draw_label_banner(preview, label, (left, top), color)

    @staticmethod
    def _draw_label_banner(
        frame: np.ndarray,
        label: str,
        anchor: tuple[int, int],
        background_color: tuple[int, int, int],
    ) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.52
        thickness = 1
        left, top = anchor
        (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
        banner_top = max(0, top - text_height - baseline - 10)
        banner_bottom = min(frame.shape[0] - 1, top)
        banner_right = min(frame.shape[1] - 1, left + text_width + 10)
        if banner_bottom <= banner_top:
            banner_bottom = min(frame.shape[0] - 1, banner_top + text_height + baseline + 10)

        cv2.rectangle(frame, (left, banner_top), (banner_right, banner_bottom), background_color, thickness=-1)
        text_y = min(frame.shape[0] - baseline - 1, banner_bottom - baseline - 4)
        cv2.putText(
            frame,
            label,
            (left + 5, text_y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    @staticmethod
    def _fit_frame_into_tile(
        frame: np.ndarray,
        tile_width: int,
        tile_height: int,
    ) -> tuple[np.ndarray, int, int, int, int]:
        frame_height, frame_width = frame.shape[:2]
        scale = min(tile_width / max(frame_width, 1), tile_height / max(frame_height, 1))
        content_width = max(1, int(round(frame_width * scale)))
        content_height = max(1, int(round(frame_height * scale)))
        resized = cv2.resize(frame, (content_width, content_height), interpolation=cv2.INTER_AREA)
        offset_x = max(0, (tile_width - content_width) // 2)
        offset_y = max(0, (tile_height - content_height) // 2)
        return resized, offset_x, offset_y, content_width, content_height

    @staticmethod
    def _multipart_jpeg(payload: bytes) -> bytes:
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Cache-Control: no-cache\r\n\r\n"
            + payload
            + b"\r\n"
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

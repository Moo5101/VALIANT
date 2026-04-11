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
                    preview_bytes = self._encode_preview(frame)
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
                self.pipeline.process_frame(frame, patient_id)
            except Exception as exc:  # pragma: no cover - runtime camera loop issue
                logger.exception("Frame processing failed: %s", exc)

    def _configure_capture(self, capture: cv2.VideoCapture) -> None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
        capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self.settings.camera_buffer_size)

    @staticmethod
    def _encode_preview(frame: np.ndarray) -> bytes | None:
        height, width = frame.shape[:2]
        preview = frame
        if width > 960:
            scale = 960 / width
            preview = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buffer.tobytes() if ok else None

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from backend.config import Settings

try:
    import easyocr
except Exception:  # pragma: no cover - optional dependency at runtime
    easyocr = None  # type: ignore[assignment]

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MedicineInfo:
    name: str = ""
    dosage: str = ""
    frequency: str = ""
    instructions: str = ""
    raw_ocr_text: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class MedicineOCR:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._reader = None
        self._gemini_client = None

    def read_medicine_label(self, cropped_image: np.ndarray | None) -> MedicineInfo | None:
        if cropped_image is None or not cropped_image.size:
            return None

        raw_text = self._run_easyocr(cropped_image)
        if not raw_text:
            return None

        structured = self._parse_with_gemini(raw_text)
        return MedicineInfo(
            name=structured.get("name", ""),
            dosage=structured.get("dosage", ""),
            frequency=structured.get("frequency", ""),
            instructions=structured.get("instructions", ""),
            raw_ocr_text=raw_text,
        )

    def _run_easyocr(self, cropped_image: np.ndarray) -> str:
        self._ensure_reader()
        if not self._reader:
            return ""
        best_text = ""
        for variant in self._prepare_variants(cropped_image):
            try:
                results = self._reader.readtext(variant, detail=0, paragraph=True)
            except Exception as exc:  # pragma: no cover - runtime OCR issue
                logger.warning("EasyOCR failed: %s", exc)
                continue
            text = re.sub(
                r"\s+",
                " ",
                " ".join(str(item).strip() for item in results if str(item).strip()),
            ).strip()
            if len(text) > len(best_text):
                best_text = text
            if self._looks_like_medicine_text(best_text):
                break
        return best_text

    def _parse_with_gemini(self, raw_text: str) -> dict[str, str]:
        self._ensure_gemini_client()
        if not self._gemini_client:
            return self._fallback_parse(raw_text)

        prompt = (
            "Extract structured medication information from the OCR text below.\n"
            'Return JSON only with this shape: {"name":"","dosage":"","frequency":"","instructions":""}.\n'
            "If a field is missing, use an empty string.\n\n"
            f"OCR text:\n{raw_text}"
        )

        try:
            response = self._gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
            )
            response_text = getattr(response, "text", "") or ""
            parsed = self._extract_json(response_text)
            if parsed:
                return parsed
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Gemini parsing failed: %s", exc)
        return self._fallback_parse(raw_text)

    def _ensure_reader(self) -> None:
        if self._reader is not None or not easyocr:
            return
        try:
            self._reader = easyocr.Reader(["en"], gpu=False)
        except Exception as exc:  # pragma: no cover - runtime OCR init issue
            logger.warning("EasyOCR reader could not be initialized: %s", exc)
            self._reader = None

    def _ensure_gemini_client(self) -> None:
        if self._gemini_client is not None or not genai or not self.settings.gemini_api_key:
            return
        try:
            self._gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
        except Exception as exc:  # pragma: no cover - runtime SDK init issue
            logger.warning("Gemini client could not be initialized: %s", exc)
            self._gemini_client = None

    @staticmethod
    def _extract_json(payload: str) -> dict[str, str]:
        if not payload:
            return {}
        match = re.search(r"\{.*\}", payload, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return {
            "name": str(data.get("name", "")).strip(),
            "dosage": str(data.get("dosage", "")).strip(),
            "frequency": str(data.get("frequency", "")).strip(),
            "instructions": str(data.get("instructions", "")).strip(),
        }

    @staticmethod
    def _fallback_parse(raw_text: str) -> dict[str, str]:
        dosage_match = re.search(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?)\b", raw_text, re.IGNORECASE)
        frequency_match = re.search(
            r"\b(?:once daily|twice daily|three times daily|daily|every \d+ hours|morning|evening|bedtime)\b",
            raw_text,
            re.IGNORECASE,
        )
        instruction_match = re.search(r"(take[^.]+|use[^.]+)", raw_text, re.IGNORECASE)

        lines = [segment.strip() for segment in re.split(r"[\n;]+", raw_text) if segment.strip()]
        first_line = lines[0] if lines else raw_text.strip()
        name = re.sub(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?)\b", "", first_line, flags=re.IGNORECASE)
        return {
            "name": name.strip(" -,:"),
            "dosage": dosage_match.group(0) if dosage_match else "",
            "frequency": frequency_match.group(0) if frequency_match else "",
            "instructions": instruction_match.group(0).strip() if instruction_match else "",
        }

    @staticmethod
    def _prepare_variants(cropped_image: np.ndarray) -> list[np.ndarray]:
        if not cropped_image.size:
            return []

        height, width = cropped_image.shape[:2]
        if min(height, width) < 48:
            scale = max(2.0, 96.0 / max(min(height, width), 1))
            resized = cv2.resize(cropped_image, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        else:
            resized = cropped_image

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        denoised = cv2.bilateralFilter(normalized, 7, 40, 40)
        thresholded = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return [resized, denoised, thresholded]

    @staticmethod
    def _looks_like_medicine_text(text: str) -> bool:
        normalized = text.lower()
        return any(
            marker in normalized
            for marker in ("mg", "mcg", "tablet", "capsule", "take", "daily", "ml", "rx")
        )

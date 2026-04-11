from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from backend.config import Settings

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


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
        self._gemini_client = None
        self._warned_missing_gemini_sdk = False
        self._gemini_disabled = False

    def read_medicine_label(self, cropped_image: np.ndarray | None) -> MedicineInfo | None:
        if cropped_image is None or not cropped_image.size:
            return None

        structured = self._read_with_gemini(cropped_image)
        if not structured:
            return None

        raw_text = structured.get("raw_ocr_text", "")
        return MedicineInfo(
            name=structured.get("name", ""),
            dosage=structured.get("dosage", ""),
            frequency=structured.get("frequency", ""),
            instructions=structured.get("instructions", ""),
            raw_ocr_text=self._normalize_ocr_text(raw_text),
        )

    def _read_with_gemini(self, cropped_image: np.ndarray) -> dict[str, str]:
        if self._gemini_disabled:
            return {}
        self._ensure_gemini_client()
        if not self._gemini_client or not genai_types:
            return {}

        image_bytes = self._encode_image(cropped_image)
        if not image_bytes:
            return {}

        prompt = (
            "You are reading a crop of a medicine bottle or prescription label.\n"
            'Return JSON only with this shape: {"name":"","dosage":"","frequency":"","instructions":"","raw_text":""}.\n'
            "If a field is missing, use an empty string.\n"
            "If the image does not clearly show a medicine label, return empty strings for every field.\n"
            "Use only text visible in the image and do not invent medication details.\n"
            "raw_text should be a concise transcription of the readable label text."
        )

        try:
            response = self._gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[
                    genai_types.Part.from_text(text=prompt),
                    genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            response_text = getattr(response, "text", "") or ""
            parsed = self._extract_json(response_text)
            if parsed:
                return parsed
            fallback = self._fallback_parse(response_text)
            if any(fallback.values()):
                fallback["raw_ocr_text"] = self._normalize_ocr_text(response_text)
                return fallback
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Gemini label extraction failed: %s", exc)
            message = str(exc).lower()
            if any(marker in message for marker in ("api key not valid", "api_key_invalid", "invalid_argument")):
                self._gemini_disabled = True
                self._gemini_client = None
                logger.warning("Gemini label extraction disabled for this session after an authentication failure.")
        return {}

    def _ensure_gemini_client(self) -> None:
        if self._gemini_client is not None or not self.settings.gemini_api_key:
            return
        if not genai or not genai_types:
            if not self._warned_missing_gemini_sdk:
                logger.warning(
                    "GEMINI_API_KEY is set but google-genai is not installed. Medicine label extraction is disabled.",
                )
                self._warned_missing_gemini_sdk = True
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
            "raw_ocr_text": MedicineOCR._normalize_ocr_text(
                str(data.get("raw_text") or data.get("raw_ocr_text") or data.get("transcription") or "")
            ),
        }

    @staticmethod
    def _encode_image(cropped_image: np.ndarray) -> bytes:
        prepared = MedicineOCR._prepare_image(cropped_image)
        ok, buffer = cv2.imencode(".jpg", prepared, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return buffer.tobytes() if ok else b""

    @staticmethod
    def _fallback_parse(raw_text: str) -> dict[str, str]:
        normalized_text = MedicineOCR._normalize_ocr_text(raw_text)
        dosage_match = re.search(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?)\b", normalized_text, re.IGNORECASE)
        frequency_match = re.search(
            r"\b(?:once daily|twice daily|three times daily|daily|every \d+ hours|morning|evening|bedtime)\b",
            normalized_text,
            re.IGNORECASE,
        )
        instruction_match = re.search(r"(take[^.]+|use[^.]+)", normalized_text, re.IGNORECASE)
        name = MedicineOCR._extract_name_from_text(normalized_text, dosage_match.start() if dosage_match else None)
        return {
            "name": name,
            "dosage": dosage_match.group(0) if dosage_match else "",
            "frequency": frequency_match.group(0) if frequency_match else "",
            "instructions": instruction_match.group(0).strip() if instruction_match else "",
        }

    @staticmethod
    def _normalize_ocr_text(raw_text: str) -> str:
        normalized = re.sub(r"[\r\n\t]+", " ", raw_text or "")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @classmethod
    def _extract_name_from_text(cls, raw_text: str, dosage_start: int | None) -> str:
        prefix = raw_text[:dosage_start] if dosage_start else raw_text
        prefix = re.sub(r"\b(?:ndc|rx|lot|exp|usp)\b", " ", prefix, flags=re.IGNORECASE)
        token_matches = list(re.finditer(r"[A-Za-z][A-Za-z'-]{2,}", prefix))
        if not token_matches:
            return ""

        stop_words = {
            "and",
            "bottle",
            "caplet",
            "caplets",
            "capsule",
            "capsules",
            "directions",
            "doctor",
            "dose",
            "doses",
            "for",
            "generic",
            "instructions",
            "keep",
            "label",
            "only",
            "patient",
            "pharmaceutical",
            "pharmaceuticals",
            "pharmacy",
            "pill",
            "pills",
            "prescriber",
            "refill",
            "refills",
            "store",
            "tablet",
            "tablets",
            "take",
            "use",
        }
        name_suffixes = {
            "acetate",
            "besylate",
            "carbonate",
            "citrate",
            "er",
            "fumarate",
            "hcl",
            "hydrochloride",
            "potassium",
            "phosphate",
            "sodium",
            "succinate",
            "tartrate",
            "xr",
            "xl",
        }

        candidates: list[dict[str, object]] = []
        prefix_length = max(len(prefix), 1)
        for match in token_matches:
            token = match.group(0).strip("-'")
            lowered = token.lower()
            if not token or lowered in stop_words or len(token) > 24:
                continue

            score = len(token) * 2
            if token.istitle():
                score += 4
            elif token.islower():
                score += 2
            elif token.isupper():
                score += 1
            else:
                score -= 2
            if len(token) <= 4:
                score -= 2
            score += int((match.start() / prefix_length) * 3)

            candidates.append(
                {
                    "token": token,
                    "lowered": lowered,
                    "start": match.start(),
                    "end": match.end(),
                    "score": score,
                }
            )

        if not candidates:
            return ""

        best_index = max(range(len(candidates)), key=lambda index: int(candidates[index]["score"]))
        anchor = candidates[best_index]
        phrase = str(anchor["token"])

        if anchor["lowered"] in name_suffixes and best_index > 0:
            previous = candidates[best_index - 1]
            if previous["end"] <= anchor["start"] + 3:
                phrase = f"{previous['token']} {anchor['token']}"
        elif best_index + 1 < len(candidates):
            following = candidates[best_index + 1]
            if following["lowered"] in name_suffixes and following["start"] <= anchor["end"] + 3:
                phrase = f"{anchor['token']} {following['token']}"

        return phrase.strip(" -,:")

    @staticmethod
    def _prepare_image(cropped_image: np.ndarray) -> np.ndarray:
        if not cropped_image.size:
            return cropped_image

        prepared = cropped_image
        height, width = prepared.shape[:2]
        min_dimension = max(min(height, width), 1)
        max_dimension = max(height, width)

        scale = 1.0
        if min_dimension < 256:
            scale = max(scale, 256.0 / min_dimension)
        if max_dimension * scale > 1600:
            scale = 1600.0 / max_dimension

        if abs(scale - 1.0) > 0.01:
            prepared = cv2.resize(prepared, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        return prepared

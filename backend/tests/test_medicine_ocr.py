from __future__ import annotations

import unittest

import numpy as np

from backend.config import get_settings
from backend.processing.medicine_ocr import MedicineOCR


class _GeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _SuccessfulModels:
    def __init__(self, payload: str) -> None:
        self.calls = 0
        self.payload = payload

    def generate_content(self, **_: object) -> object:
        self.calls += 1
        return _GeminiResponse(self.payload)


class _SuccessfulGeminiClient:
    def __init__(self, payload: str) -> None:
        self.models = _SuccessfulModels(payload)


class _FailingModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_: object) -> object:
        self.calls += 1
        raise RuntimeError("API_KEY_INVALID")


class _FailingGeminiClient:
    def __init__(self) -> None:
        self.models = _FailingModels()


class MedicineOCRTests(unittest.TestCase):
    def test_fallback_parse_extracts_medicine_name_from_noisy_bottle_text(self) -> None:
        sample = (
            "NDC 68382-721-16 Edhe Nateglinide Oizn Usulb Mmar Tablets, USP "
            "B Dsh KEEPM ThERI 60 mg Codeks Manes s Caur Nmaz 90 TABLETS "
            "Dkshi y Zydusr zydus Rx oly Pengul pharmaceuticals"
        )

        parsed = MedicineOCR._fallback_parse(sample)

        self.assertEqual(parsed["name"], "Nateglinide")
        self.assertEqual(parsed["dosage"], "60 mg")

    def test_fallback_parse_preserves_common_two_word_names(self) -> None:
        parsed = MedicineOCR._fallback_parse(
            "Metformin Hydrochloride Tablets USP 500 mg take one tablet twice daily",
        )

        self.assertEqual(parsed["name"], "Metformin Hydrochloride")
        self.assertEqual(parsed["dosage"], "500 mg")
        self.assertEqual(parsed["frequency"], "twice daily")

    def test_read_medicine_label_uses_gemini_image_response(self) -> None:
        settings = get_settings().model_copy(update={"gemini_api_key": "test-key"})
        ocr = MedicineOCR(settings)
        client = _SuccessfulGeminiClient(
            '{"name":"Nateglinide","dosage":"60 mg","frequency":"daily","instructions":"take by mouth","raw_text":"Nateglinide Tablets USP 60 mg"}',
        )
        ocr._gemini_client = client

        image = np.full((32, 32, 3), 255, dtype=np.uint8)
        info = ocr.read_medicine_label(image)

        assert info is not None
        self.assertEqual(client.models.calls, 1)
        self.assertEqual(info.name, "Nateglinide")
        self.assertEqual(info.dosage, "60 mg")
        self.assertEqual(info.frequency, "daily")
        self.assertEqual(info.instructions, "take by mouth")
        self.assertEqual(info.raw_ocr_text, "Nateglinide Tablets USP 60 mg")

    def test_invalid_gemini_key_disables_repeated_remote_attempts(self) -> None:
        settings = get_settings().model_copy(update={"gemini_api_key": "test-key"})
        ocr = MedicineOCR(settings)
        failing_client = _FailingGeminiClient()
        ocr._gemini_client = failing_client

        image = np.zeros((32, 32, 3), dtype=np.uint8)
        first = ocr.read_medicine_label(image)
        second = ocr.read_medicine_label(image)

        self.assertEqual(failing_client.models.calls, 1)
        self.assertTrue(ocr._gemini_disabled)
        self.assertIsNone(first)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()

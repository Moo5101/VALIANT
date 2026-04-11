from __future__ import annotations

import re


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value or "").strip()
    if not cleaned:
        return ""

    if cleaned.startswith("+"):
        digits = "+" + re.sub(r"\D", "", cleaned[1:])
        return digits

    digits_only = re.sub(r"\D", "", cleaned)
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    if len(digits_only) == 11 and digits_only.startswith("1"):
        return f"+{digits_only}"
    return f"+{digits_only}" if digits_only else ""

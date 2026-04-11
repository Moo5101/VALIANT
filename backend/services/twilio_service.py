from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from backend.config import Settings

try:
    from twilio.rest import Client
except Exception:  # pragma: no cover - optional dependency at runtime
    Client = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class TwilioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cooldowns: dict[str, float] = {}
        self.client = None

        if (
            Client
            and settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        ):
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        else:
            logger.warning("Twilio is not configured. SMS and MMS alerts will be logged only.")

    def _can_send(self, key: str, cooldown_seconds: int | None = None) -> bool:
        window = cooldown_seconds or self.settings.alert_cooldown_seconds
        now = time.time()
        previous = self.cooldowns.get(key)
        if previous and now - previous < window:
            return False
        self.cooldowns[key] = now
        return True

    def send_sms(self, to: str, body: str, cooldown_key: str | None = None) -> str | None:
        if not to or not body:
            return None
        key = cooldown_key or f"sms:{to}:{body}"
        if not self._can_send(key):
            return None
        if not self.client:
            logger.info("SMS dry-run to %s: %s", to, body)
            return "dry-run-sms"
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.settings.twilio_phone_number,
                to=to,
            )
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Twilio SMS failed for %s: %s", to, exc)
            return None
        return message.sid

    def send_mms(
        self,
        to: str,
        body: str,
        media_url: str,
        cooldown_key: str | None = None,
    ) -> str | None:
        if not to or not body or not media_url:
            return None
        key = cooldown_key or f"mms:{to}:{body}:{media_url}"
        if not self._can_send(key):
            return None
        if not self.client:
            logger.info("MMS dry-run to %s: %s (%s)", to, body, media_url)
            return "dry-run-mms"
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.settings.twilio_phone_number,
                to=to,
                media_url=[media_url],
            )
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Twilio MMS failed for %s: %s", to, exc)
            return None
        return message.sid

    def send_alert_to_both(
        self,
        patient_phone: str,
        caregiver_phone: str,
        body: str,
        media_url: str | None = None,
        cooldown_key: str | None = None,
    ) -> list[str]:
        recipients = [number for number in (patient_phone, caregiver_phone) if number]
        results: list[str] = []
        for recipient in recipients:
            result = self.send_mms(
                recipient,
                body,
                media_url,
                cooldown_key=f"{cooldown_key}:{recipient}" if cooldown_key else None,
            ) if media_url else self.send_sms(
                recipient,
                body,
                cooldown_key=f"{cooldown_key}:{recipient}" if cooldown_key else None,
            )
            if result:
                results.append(result)
        return results

    def send_bulk_sms(self, recipients: Iterable[str], body: str, cooldown_key: str) -> list[str]:
        results: list[str] = []
        for recipient in recipients:
            result = self.send_sms(recipient, body, cooldown_key=f"{cooldown_key}:{recipient}")
            if result:
                results.append(result)
        return results

from __future__ import annotations

import html
import json
import logging
import ssl
import time
import urllib.error
import urllib.request

from backend.config import Settings

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency at runtime
    certifi = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class SendGridEmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cooldowns: dict[str, float] = {}
        self.enabled = bool(settings.sendgrid_api_key and settings.sendgrid_from_email)
        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if certifi else None

        if not self.enabled:
            logger.warning("SendGrid is not configured. Email alerts will be logged only.")

    def _can_send(self, key: str, cooldown_seconds: int | None = None) -> bool:
        window = cooldown_seconds or self.settings.alert_cooldown_seconds
        now = time.time()
        previous = self.cooldowns.get(key)
        if previous and now - previous < window:
            return False
        self.cooldowns[key] = now
        return True

    def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        *,
        html_body: str | None = None,
        image_url: str | None = None,
        cooldown_key: str | None = None,
    ) -> str | None:
        if not to_email or not subject or not text_body:
            return None
        key = cooldown_key or f"email:{to_email}:{subject}:{text_body}"
        if not self._can_send(key):
            return None
        if not self.enabled:
            logger.info("Email dry-run to %s: %s | %s", to_email, subject, text_body)
            return "dry-run-email"

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {
                "email": self.settings.sendgrid_from_email,
                "name": self.settings.sendgrid_from_name or self.settings.app_name,
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body or self._default_html(subject, text_body, image_url)},
            ],
        }
        if self.settings.sendgrid_reply_to:
            payload["reply_to"] = {"email": self.settings.sendgrid_reply_to}

        request = urllib.request.Request(
            self.settings.sendgrid_api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=10, context=self.ssl_context) as response:
                message_id = response.headers.get("X-Message-Id")
                return message_id or f"status-{response.status}"
        except urllib.error.HTTPError as exc:  # pragma: no cover - network side effect
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("SendGrid email failed for %s: %s %s", to_email, exc.code, body)
            return None
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("SendGrid email failed for %s: %s", to_email, exc)
            return None

    @staticmethod
    def _default_html(subject: str, text_body: str, image_url: str | None = None) -> str:
        safe_subject = html.escape(subject)
        paragraphs = "".join(
            f"<p style=\"margin:0 0 12px;\">{html.escape(line)}</p>"
            for line in text_body.splitlines()
            if line.strip()
        )
        image_block = ""
        if image_url:
            safe_url = html.escape(image_url, quote=True)
            image_block = (
                f"<p style=\"margin:16px 0 8px;\"><a href=\"{safe_url}\">View captured image</a></p>"
                f"<p style=\"margin:0;\"><img src=\"{safe_url}\" alt=\"Captured evidence\" "
                "style=\"max-width:100%;border-radius:12px;border:1px solid #d9e2ec;\" /></p>"
            )

        return (
            "<html><body style=\"margin:0;background:#f7fafc;font-family:Arial,sans-serif;color:#0f172a;\">"
            "<div style=\"max-width:640px;margin:0 auto;padding:24px;\">"
            "<div style=\"background:#ffffff;border:1px solid #e2e8f0;border-radius:20px;padding:24px;\">"
            f"<h1 style=\"margin:0 0 16px;font-size:24px;line-height:1.2;\">{safe_subject}</h1>"
            f"{paragraphs}"
            f"{image_block}"
            "</div></div></body></html>"
        )

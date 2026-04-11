from __future__ import annotations

import logging
from datetime import time
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.email_service import SendGridEmailService
from backend.services.supabase_service import SupabaseService
from backend.services.twilio_service import TwilioService


logger = logging.getLogger(__name__)

DAY_MAP = {
    "mon": "mon",
    "monday": "mon",
    "tue": "tue",
    "tues": "tue",
    "tuesday": "tue",
    "wed": "wed",
    "wednesday": "wed",
    "thu": "thu",
    "thurs": "thu",
    "thursday": "thu",
    "fri": "fri",
    "friday": "fri",
    "sat": "sat",
    "saturday": "sat",
    "sun": "sun",
    "sunday": "sun",
}


class ReminderScheduler:
    def __init__(self, supabase: SupabaseService, twilio: TwilioService, email_service: SendGridEmailService) -> None:
        self.supabase = supabase
        self.twilio = twilio
        self.email_service = email_service
        self.scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        await self.load_active_reminders()

    async def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def load_active_reminders(self) -> None:
        for reminder in self.supabase.get_active_reminders():
            self.add_reminder(reminder)

    def add_reminder(self, reminder: dict[str, Any]) -> None:
        reminder_id = reminder.get("id")
        reminder_time = self._parse_time(reminder.get("reminder_time"))
        if not reminder_id or not reminder_time:
            return
        days = reminder.get("days_of_week") or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_of_week = ",".join(self._normalize_day(day) for day in days)
        self.scheduler.add_job(
            self.send_reminder_job,
            trigger="cron",
            id=f"reminder:{reminder_id}",
            replace_existing=True,
            day_of_week=day_of_week,
            hour=reminder_time.hour,
            minute=reminder_time.minute,
            kwargs={"reminder_id": str(reminder_id)},
        )

    def remove_reminder(self, reminder_id: str) -> None:
        job_id = f"reminder:{reminder_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def send_reminder_job(self, reminder_id: str) -> None:
        reminder = self.supabase.get_reminder(reminder_id)
        if not reminder:
            logger.warning("Reminder %s could not be loaded for delivery.", reminder_id)
            return

        medicine = reminder.get("medicines") or {}
        patient = reminder.get("patients") or {}
        patient_name = patient.get("name", "The patient")
        medicine_name = medicine.get("name", "medicine")
        dosage = medicine.get("dosage") or ""
        patient_email = str(patient.get("patient_email") or "")
        caregiver_email = str(patient.get("caregiver_email") or "")

        patient_body = f"Time to take {medicine_name} {dosage}".strip()
        caregiver_body = f"Reminder: {patient_name} should take {medicine_name} {dosage}".strip()
        patient_subject = f"Medicine reminder: {medicine_name}"
        caregiver_subject = f"Reminder for {patient_name}: {medicine_name}"

        self.twilio.send_sms(
            patient.get("phone", ""),
            patient_body,
            cooldown_key=f"reminder:patient:{reminder_id}",
        )
        self.twilio.send_sms(
            patient.get("caregiver_phone", ""),
            caregiver_body,
            cooldown_key=f"reminder:caregiver:{reminder_id}",
        )
        self.email_service.send_email(
            patient_email,
            patient_subject,
            patient_body,
            cooldown_key=f"reminder-email:patient:{reminder_id}",
        )
        self.email_service.send_email(
            caregiver_email,
            caregiver_subject,
            caregiver_body,
            cooldown_key=f"reminder-email:caregiver:{reminder_id}",
        )
        self.supabase.mark_reminder_sent(reminder_id)

    @staticmethod
    def _parse_time(raw_value: Any) -> time | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, time):
            return raw_value
        if isinstance(raw_value, str):
            try:
                return time.fromisoformat(raw_value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_day(day: str) -> str:
        return DAY_MAP.get(day.strip().lower(), day.strip().lower()[:3])

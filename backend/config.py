from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


CommaSeparated = Annotated[list[str], NoDecode, Field(default_factory=list)]
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Alzheimer Safety Dashboard", validation_alias=AliasChoices("APP_NAME"))
    app_env: str = Field(default="development", validation_alias=AliasChoices("APP_ENV"))
    frontend_origin: str = Field(default="http://localhost:3000", validation_alias=AliasChoices("FRONTEND_ORIGIN"))
    allowed_origins: CommaSeparated = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS),
        validation_alias=AliasChoices("ALLOWED_ORIGINS"),
    )

    supabase_url: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL"))
    supabase_key: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_KEY"))
    supabase_service_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "SUPABASE_API"),
    )
    supabase_storage_bucket: str = Field(
        default="detection-images",
        validation_alias=AliasChoices("SUPABASE_STORAGE_BUCKET"),
    )

    twilio_account_sid: str | None = Field(default=None, validation_alias=AliasChoices("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str | None = Field(default=None, validation_alias=AliasChoices("TWILIO_AUTH_TOKEN"))
    twilio_phone_number: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TWILIO_PHONE_NUMBER", "TWILIO_FROM_NUMBER"),
    )
    sendgrid_api_key: str | None = Field(default=None, validation_alias=AliasChoices("SENDGRID_API_KEY", "SENDGRID_API"))
    sendgrid_api_url: str = Field(
        default="https://api.sendgrid.com/v3/mail/send",
        validation_alias=AliasChoices("SENDGRID_API_URL"),
    )
    sendgrid_from_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SENDGRID_FROM_EMAIL"),
    )
    sendgrid_from_name: str | None = Field(
        default="VALIANT",
        validation_alias=AliasChoices("SENDGRID_FROM_NAME"),
    )
    sendgrid_reply_to: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SENDGRID_REPLY_TO"),
    )

    roboflow_api_key: str | None = Field(default=None, validation_alias=AliasChoices("ROBOFLOW_API_KEY"))
    roboflow_api_url: str = Field(
        default="https://detect.roboflow.com",
        validation_alias=AliasChoices("ROBOFLOW_API_URL"),
    )
    roboflow_fire_model_id: str = Field(
        default="fire-5vwyl/1",
        validation_alias=AliasChoices("ROBOFLOW_FIRE_MODEL_ID"),
    )
    roboflow_gun_model_id: str = Field(
        default="gun-detection-s5poj/1",
        validation_alias=AliasChoices("ROBOFLOW_GUN_MODEL_ID"),
    )
    roboflow_every_n_frames: int = Field(default=5, validation_alias=AliasChoices("ROBOFLOW_EVERY_N_FRAMES"))

    gemini_api_key: str | None = Field(default=None, validation_alias=AliasChoices("GEMINI_API_KEY"))
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL"),
    )

    patient_id: UUID | None = Field(default=None, validation_alias=AliasChoices("PATIENT_ID"))
    camera_index: int = Field(default=0, validation_alias=AliasChoices("CAMERA_INDEX"))
    camera_width: int = Field(default=1280, validation_alias=AliasChoices("CAMERA_WIDTH"))
    camera_height: int = Field(default=720, validation_alias=AliasChoices("CAMERA_HEIGHT"))
    camera_fps: int = Field(default=30, validation_alias=AliasChoices("CAMERA_FPS"))
    camera_buffer_size: int = Field(default=1, validation_alias=AliasChoices("CAMERA_BUFFER_SIZE"))
    camera_preview_fps: float = Field(default=10.0, validation_alias=AliasChoices("CAMERA_PREVIEW_FPS"))
    frame_interval: float = Field(default=2.0, validation_alias=AliasChoices("FRAME_INTERVAL"))
    familiar_threshold: int = Field(default=5, validation_alias=AliasChoices("FAMILIAR_THRESHOLD"))
    face_match_threshold: float = Field(default=0.6, validation_alias=AliasChoices("FACE_MATCH_THRESHOLD"))
    face_scale_factor: float = Field(default=0.5, validation_alias=AliasChoices("FACE_SCALE_FACTOR"))
    face_detection_upsample: int = Field(default=0, validation_alias=AliasChoices("FACE_DETECTION_UPSAMPLE"))
    face_process_interval: float = Field(default=0.75, validation_alias=AliasChoices("FACE_PROCESS_INTERVAL"))
    alert_cooldown_seconds: int = Field(default=60, validation_alias=AliasChoices("ALERT_COOLDOWN_SECONDS"))
    medicine_cooldown_seconds: int = Field(default=3600, validation_alias=AliasChoices("MEDICINE_COOLDOWN_SECONDS"))
    medicine_scan_interval: float = Field(default=1.5, validation_alias=AliasChoices("MEDICINE_SCAN_INTERVAL"))
    max_medicine_detections_per_frame: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_MEDICINE_DETECTIONS_PER_FRAME"),
    )
    medicine_crop_padding: float = Field(default=0.18, validation_alias=AliasChoices("MEDICINE_CROP_PADDING"))
    medicine_focus_threshold: float = Field(
        default=6.0,
        validation_alias=AliasChoices("MEDICINE_FOCUS_THRESHOLD"),
    )
    medicine_confidence_threshold: float = Field(
        default=0.18,
        validation_alias=AliasChoices("MEDICINE_CONFIDENCE_THRESHOLD"),
    )
    face_alert_cooldown_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("FACE_ALERT_COOLDOWN_SECONDS"),
    )

    yolo_model: str = Field(default="yolov8n.pt", validation_alias=AliasChoices("YOLO_MODEL"))
    yolo_image_size: int = Field(default=512, validation_alias=AliasChoices("YOLO_IMAGE_SIZE"))
    yolo_max_det: int = Field(default=16, validation_alias=AliasChoices("YOLO_MAX_DET"))
    yolo_half: bool = Field(default=False, validation_alias=AliasChoices("YOLO_HALF"))
    yolo_confidence_threshold: float = Field(
        default=0.35,
        validation_alias=AliasChoices("YOLO_CONFIDENCE_THRESHOLD"),
    )
    person_confidence_threshold: float = Field(
        default=0.35,
        validation_alias=AliasChoices("PERSON_CONFIDENCE_THRESHOLD"),
    )
    hazard_confidence_threshold: float = Field(
        default=0.35,
        validation_alias=AliasChoices("HAZARD_CONFIDENCE_THRESHOLD"),
    )
    roboflow_hazard_confidence_threshold: float = Field(
        default=0.6,
        validation_alias=AliasChoices("ROBOFLOW_HAZARD_CONFIDENCE_THRESHOLD"),
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> list[str]:
        if value is None:
            return list(DEFAULT_ALLOWED_ORIGINS)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(DEFAULT_ALLOWED_ORIGINS)

    @field_validator("patient_id", mode="before")
    @classmethod
    def parse_patient_id(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def supabase_admin_key(self) -> str | None:
        return self.supabase_service_key or self.supabase_key


@lru_cache
def get_settings() -> Settings:
    return Settings()

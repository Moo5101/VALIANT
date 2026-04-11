from __future__ import annotations

from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.utils.email import normalize_email
from backend.utils.phone import normalize_phone


router = APIRouter(prefix="/api")


class PatientPayload(BaseModel):
    id: UUID | None = None
    name: str
    phone: str
    patient_email: str | None = None
    caregiver_name: str | None = None
    caregiver_phone: str
    caregiver_email: str | None = None


class FaceLabelPayload(BaseModel):
    label: str = Field(min_length=1)
    is_familiar: bool = True


class PhoneLookupPayload(BaseModel):
    phone: str = Field(min_length=7)


def get_supabase(request: Request):
    return request.app.state.supabase


def get_camera(request: Request):
    return request.app.state.camera


def activate_patient(request: Request, patient_id: str) -> None:
    request.app.state.face_manager.load_known_faces(patient_id)
    request.app.state.camera.set_patient_id(patient_id)
    request.app.state.active_patient_id = patient_id


def clear_active_patient(request: Request) -> None:
    request.app.state.face_manager.cache = {}
    request.app.state.camera.set_patient_id(None)
    request.app.state.active_patient_id = None


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/patient/by-phone")
async def get_patient_by_phone(phone: str, request: Request) -> dict[str, Any]:
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        raise HTTPException(status_code=422, detail="A valid phone number is required")
    patient = get_supabase(request).get_patient_by_phone(normalized_phone)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/patient/{patient_id}")
async def get_patient(patient_id: UUID, request: Request) -> dict[str, Any]:
    patient = get_supabase(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("/session/start")
async def start_session(payload: PhoneLookupPayload, request: Request) -> dict[str, Any]:
    normalized_phone = normalize_phone(payload.phone)
    if not normalized_phone:
        raise HTTPException(status_code=422, detail="A valid phone number is required")
    patient = get_supabase(request).get_patient_by_phone(normalized_phone)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    activate_patient(request, str(patient["id"]))
    return patient


@router.post("/session/activate/{patient_id}")
async def activate_session(patient_id: UUID, request: Request) -> dict[str, Any]:
    patient = get_supabase(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    activate_patient(request, str(patient["id"]))
    return patient


@router.post("/session/clear")
async def clear_session(request: Request) -> dict[str, bool]:
    clear_active_patient(request)
    return {"cleared": True}


@router.get("/medicines/{patient_id}")
async def get_medicines(patient_id: UUID, request: Request) -> list[dict[str, Any]]:
    return get_supabase(request).list_medicines_with_reminders(patient_id)


@router.get("/faces/{patient_id}")
async def get_faces(patient_id: UUID, request: Request) -> list[dict[str, Any]]:
    return get_supabase(request).get_known_faces(patient_id)


@router.get("/alerts/{patient_id}")
async def get_alerts(
    patient_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return get_supabase(request).list_alerts(patient_id, limit=limit, offset=offset)


@router.put("/faces/{face_id}/label")
async def update_face_label(
    face_id: UUID,
    payload: FaceLabelPayload,
    request: Request,
) -> dict[str, Any]:
    updated = get_supabase(request).update_face(
        face_id,
        {
            "label": payload.label.strip(),
            "is_familiar": payload.is_familiar,
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Face not found")
    return updated


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: UUID, request: Request) -> dict[str, Any]:
    updated = get_supabase(request).acknowledge_alert(alert_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    return updated


@router.get("/camera/frame")
async def get_camera_frame(request: Request) -> StreamingResponse:
    image_bytes = get_camera(request).get_latest_frame_jpeg()
    if not image_bytes:
        raise HTTPException(status_code=404, detail="No camera frame available")
    return StreamingResponse(BytesIO(image_bytes), media_type="image/jpeg")


@router.get("/camera/stream")
async def stream_camera(request: Request) -> StreamingResponse:
    stream = get_camera(request).iter_mjpeg_stream()
    return StreamingResponse(
        stream,
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/patient")
async def create_or_update_patient(
    payload: PatientPayload,
    request: Request,
) -> dict[str, Any]:
    normalized_payload = payload.model_dump(exclude_none=True)
    normalized_payload["name"] = str(normalized_payload["name"]).strip()
    normalized_payload["caregiver_name"] = str(normalized_payload.get("caregiver_name") or "").strip() or None
    normalized_payload["phone"] = normalize_phone(str(normalized_payload["phone"]))
    normalized_payload["caregiver_phone"] = normalize_phone(str(normalized_payload["caregiver_phone"]))
    normalized_payload["patient_email"] = normalize_email(str(normalized_payload.get("patient_email") or ""))
    normalized_payload["caregiver_email"] = normalize_email(str(normalized_payload.get("caregiver_email") or ""))
    if not normalized_payload["name"]:
        raise HTTPException(status_code=422, detail="Patient name is required")
    if not normalized_payload["phone"] or not normalized_payload["caregiver_phone"]:
        raise HTTPException(status_code=422, detail="Valid patient and caregiver phone numbers are required")
    if str(normalized_payload.get("patient_email") or "") == "" and "patient_email" in normalized_payload:
        normalized_payload["patient_email"] = None
    if str(normalized_payload.get("caregiver_email") or "") == "" and "caregiver_email" in normalized_payload:
        normalized_payload["caregiver_email"] = None
    if payload.patient_email and not normalized_payload["patient_email"]:
        raise HTTPException(status_code=422, detail="A valid patient email is required")
    if payload.caregiver_email and not normalized_payload["caregiver_email"]:
        raise HTTPException(status_code=422, detail="A valid caregiver email is required")
    patient = get_supabase(request).upsert_patient(normalized_payload)
    if not patient:
        raise HTTPException(status_code=500, detail="Patient could not be stored")
    activate_patient(request, str(patient["id"]))
    return patient

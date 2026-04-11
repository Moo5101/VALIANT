from __future__ import annotations

import json
from io import BytesIO
from html import escape
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
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


class CameraSourcePayload(BaseModel):
    name: str | None = None


def get_supabase(request: Request):
    return request.app.state.supabase


def get_camera(request: Request):
    return request.app.state.camera


def build_route_url(request: Request, route_name: str, *, external: bool = False, **path_params: str) -> str:
    if not external:
        return str(request.url_for(route_name, **path_params))

    public_base = str(request.app.state.settings.public_api_base_url or "").strip()
    if not public_base:
        return str(request.url_for(route_name, **path_params))

    path = str(request.app.url_path_for(route_name, **path_params))
    return public_base.rstrip("/") + path


def serialize_camera_source(request: Request, source: dict[str, Any]) -> dict[str, Any]:
    source_id = str(source.get("id") or "")
    payload = dict(source)
    payload["stream_url"] = build_route_url(request, "stream_camera_source", source_id=source_id)
    if payload.get("kind") == "remote-phone":
        payload["connect_url"] = build_route_url(request, "camera_connect_page", external=True, source_id=source_id)
        payload["disconnect_url"] = build_route_url(request, "disconnect_camera_source", source_id=source_id)
    return payload


def get_camera_source(request: Request, source_id: str) -> dict[str, Any]:
    for source in get_camera(request).list_sources():
        if str(source.get("id") or "") == source_id:
            return source
    raise HTTPException(status_code=404, detail="Camera source not found")


def build_phone_connect_page(request: Request, source: dict[str, Any]) -> str:
    serialized = serialize_camera_source(request, source)
    page_config = json.dumps(
        {
            "sourceId": str(serialized.get("id") or ""),
            "sourceName": str(serialized.get("name") or "Phone Camera"),
            "streamUrl": build_route_url(
                request,
                "stream_camera_source",
                external=True,
                source_id=str(serialized.get("id") or ""),
            ),
            "connectUrl": serialized.get("connect_url"),
            "disconnectUrl": build_route_url(
                request,
                "disconnect_camera_source",
                external=True,
                source_id=str(serialized.get("id") or ""),
            ),
            "ingestUrl": build_route_url(
                request,
                "update_camera_source_frame",
                external=True,
                source_id=str(serialized.get("id") or ""),
            ),
        },
    )
    source_name = escape(str(serialized.get("name") or "Phone Camera"))

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>{source_name} | VALIANT Camera Connect</title>
    <style>
      :root {{
        color-scheme: light;
        --canvas: #f4efe6;
        --card: rgba(255, 252, 246, 0.92);
        --card-border: rgba(18, 38, 58, 0.12);
        --ink: #12263a;
        --muted: #52606d;
        --accent: #264653;
        --accent-2: #2a9d8f;
        --warn: #a16207;
      }}
      * {{
        box-sizing: border-box;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top right, rgba(42, 157, 143, 0.18), transparent 28%),
          radial-gradient(circle at bottom left, rgba(244, 162, 97, 0.18), transparent 26%),
          linear-gradient(180deg, #fbf8f2 0%, var(--canvas) 100%);
        color: var(--ink);
        font-family: "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
      }}
      main {{
        width: min(980px, calc(100vw - 24px));
        margin: 0 auto;
        padding: 20px 0 40px;
      }}
      .hero {{
        padding: 24px;
        border: 1px solid var(--card-border);
        border-radius: 28px;
        background: var(--card);
        box-shadow: 0 24px 80px rgba(15, 23, 42, 0.12);
      }}
      .eyebrow {{
        margin: 0;
        font-size: 12px;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        color: var(--muted);
      }}
      h1 {{
        margin: 16px 0 10px;
        font-size: clamp(34px, 8vw, 56px);
        line-height: 1;
      }}
      .lede {{
        margin: 0;
        max-width: 56ch;
        color: var(--muted);
        line-height: 1.55;
      }}
      .controls {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 22px;
      }}
      button,
      a.link {{
        appearance: none;
        border: none;
        border-radius: 999px;
        padding: 14px 18px;
        font: inherit;
        font-weight: 600;
        text-decoration: none;
        cursor: pointer;
        transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
      }}
      button:hover,
      a.link:hover {{
        transform: translateY(-1px);
      }}
      button:disabled {{
        cursor: wait;
        opacity: 0.6;
        transform: none;
      }}
      .primary {{
        background: var(--accent);
        color: white;
      }}
      .secondary {{
        background: white;
        color: var(--ink);
        border: 1px solid rgba(18, 38, 58, 0.16);
      }}
      .danger {{
        background: #8d2f2f;
        color: white;
      }}
      .status {{
        margin-top: 18px;
        padding: 14px 16px;
        border-radius: 18px;
        background: rgba(38, 70, 83, 0.08);
        color: var(--ink);
        font-size: 15px;
      }}
      .status[data-tone="warn"] {{
        background: rgba(161, 98, 7, 0.12);
        color: #6b4708;
      }}
      .status[data-tone="good"] {{
        background: rgba(42, 157, 143, 0.14);
        color: #17574f;
      }}
      .grid {{
        display: grid;
        gap: 18px;
        margin-top: 20px;
      }}
      .panel {{
        overflow: hidden;
        border: 1px solid var(--card-border);
        border-radius: 24px;
        background: var(--card);
        box-shadow: 0 20px 64px rgba(15, 23, 42, 0.1);
      }}
      .panel h2 {{
        margin: 0 0 8px;
        font-size: 18px;
      }}
      .panel-copy {{
        margin: 0;
        color: var(--muted);
        line-height: 1.5;
      }}
      .panel-head {{
        padding: 20px 20px 0;
      }}
      .frame {{
        width: 100%;
        aspect-ratio: 4 / 3;
        object-fit: cover;
        background: #0f172a;
      }}
      .panel-body {{
        padding: 18px 20px 22px;
      }}
      .meta {{
        display: grid;
        gap: 10px;
        margin-top: 16px;
      }}
      .meta-item {{
        padding: 12px 14px;
        border-radius: 16px;
        background: rgba(18, 38, 58, 0.06);
      }}
      .meta-label {{
        margin: 0 0 6px;
        font-size: 11px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--muted);
      }}
      .meta-value {{
        margin: 0;
        word-break: break-word;
      }}
      code {{
        font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
        font-size: 0.82em;
      }}
      @media (min-width: 820px) {{
        .grid {{
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <p class="eyebrow">Remote Camera Link</p>
        <h1>{source_name}</h1>
        <p class="lede">
          Keep this page open on the phone and tap start. VALIANT will capture frames from this device,
          run the same medicine and face pipeline, and fold the result into the dashboard preview.
        </p>
        <div class="controls">
          <button id="start" class="primary" type="button">Start camera feed</button>
          <button id="stop" class="secondary" type="button" disabled>Stop</button>
          <button id="disconnect" class="danger" type="button">Disconnect source</button>
          <a id="preview-link" class="link secondary" href="#" target="_blank" rel="noreferrer">Open server preview</a>
        </div>
        <div id="status" class="status" data-tone="default">
          Camera permission has not been requested yet.
        </div>
      </section>

      <section class="grid">
        <article class="panel">
          <div class="panel-head">
            <h2>Phone camera</h2>
            <p class="panel-copy">This is the live camera on the phone before the frame is uploaded.</p>
          </div>
          <video id="phone-preview" class="frame" playsinline muted autoplay></video>
          <div class="panel-body">
            <div class="meta">
              <div class="meta-item">
                <p class="meta-label">Upload cadence</p>
                <p class="meta-value">One JPEG frame roughly every half second.</p>
              </div>
              <div class="meta-item">
                <p class="meta-label">Best framing</p>
                <p class="meta-value">Aim the patient area or medicine bottle so it fills the center of the shot.</p>
              </div>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-head">
            <h2>Server preview</h2>
            <p class="panel-copy">This stream comes back from the backend after ingestion. Bounding boxes appear here once processing starts.</p>
          </div>
          <img id="server-preview" class="frame" alt="Server-side processed stream" />
          <div class="panel-body">
            <div class="meta">
              <div class="meta-item">
                <p class="meta-label">Source ID</p>
                <p class="meta-value"><code>{escape(str(serialized.get("id") or ""))}</code></p>
              </div>
              <div class="meta-item">
                <p class="meta-label">Connect link</p>
                <p class="meta-value"><code>{escape(str(serialized.get("connect_url") or ""))}</code></p>
              </div>
            </div>
          </div>
        </article>
      </section>

      <canvas id="capture-canvas" hidden></canvas>
    </main>

    <script>
      const config = {page_config};
      const startButton = document.getElementById("start");
      const stopButton = document.getElementById("stop");
      const disconnectButton = document.getElementById("disconnect");
      const status = document.getElementById("status");
      const phonePreview = document.getElementById("phone-preview");
      const serverPreview = document.getElementById("server-preview");
      const previewLink = document.getElementById("preview-link");
      const canvas = document.getElementById("capture-canvas");
      const context = canvas.getContext("2d", {{ alpha: false }});

      let activeStream = null;
      let uploadTimer = null;
      let uploadInFlight = false;

      previewLink.href = config.streamUrl;
      serverPreview.src = config.streamUrl;

      function setStatus(message, tone = "default") {{
        status.textContent = message;
        status.dataset.tone = tone;
      }}

      async function captureAndUpload() {{
        if (!activeStream || uploadInFlight || !phonePreview.videoWidth || !phonePreview.videoHeight) {{
          return;
        }}
        if (!context) {{
          setStatus("This browser could not initialize the image capture canvas.", "warn");
          return;
        }}

        const maxWidth = 960;
        const scale = Math.min(1, maxWidth / phonePreview.videoWidth);
        canvas.width = Math.max(1, Math.round(phonePreview.videoWidth * scale));
        canvas.height = Math.max(1, Math.round(phonePreview.videoHeight * scale));
        context.drawImage(phonePreview, 0, 0, canvas.width, canvas.height);

        uploadInFlight = true;
        try {{
          const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.76));
          if (!blob) {{
            throw new Error("The browser could not encode a JPEG frame.");
          }}

          const response = await fetch(config.ingestUrl, {{
            method: "PUT",
            headers: {{
              "Content-Type": "image/jpeg"
            }},
            body: blob
          }});

          if (!response.ok) {{
            const message = await response.text();
            throw new Error(message || `Upload failed with status ${{response.status}}.`);
          }}

          setStatus(`Streaming from ${{config.sourceName}}. Frames are reaching the backend.`, "good");
        }} catch (error) {{
          setStatus(error instanceof Error ? error.message : "The upload failed.", "warn");
        }} finally {{
          uploadInFlight = false;
        }}
      }}

      async function startFeed() {{
        if (!window.isSecureContext) {{
          setStatus(
            "Camera access requires a secure page. Open this link over HTTPS on the Tailscale hostname, not plain HTTP.",
            "warn",
          );
          return;
        }}
        if (!navigator.mediaDevices?.getUserMedia) {{
          setStatus(
            "This browser is not exposing camera APIs. Use Safari or Chrome on the HTTPS Tailscale link instead of an in-app browser.",
            "warn",
          );
          return;
        }}

        startButton.disabled = true;
        setStatus("Requesting camera access...", "default");

        try {{
          activeStream = await navigator.mediaDevices.getUserMedia({{
            audio: false,
            video: {{
              facingMode: {{ ideal: "environment" }},
              width: {{ ideal: 1280 }},
              height: {{ ideal: 720 }}
            }}
          }});

          phonePreview.srcObject = activeStream;
          await phonePreview.play();

          stopButton.disabled = false;
          uploadTimer = window.setInterval(() => {{
            void captureAndUpload();
          }}, 500);
          void captureAndUpload();
          setStatus("Camera active. Point the phone at the room or medicine bottle you want monitored.", "good");
        }} catch (error) {{
          startButton.disabled = false;
          setStatus(error instanceof Error ? error.message : "Camera access was denied.", "warn");
        }}
      }}

      function stopFeed() {{
        if (uploadTimer) {{
          window.clearInterval(uploadTimer);
          uploadTimer = null;
        }}
        if (activeStream) {{
          activeStream.getTracks().forEach((track) => track.stop());
          activeStream = null;
        }}
        phonePreview.srcObject = null;
        startButton.disabled = false;
        stopButton.disabled = true;
        setStatus("Camera stopped. You can start it again whenever needed.", "default");
      }}

      async function disconnectSource() {{
        disconnectButton.disabled = true;
        try {{
          const response = await fetch(config.disconnectUrl, {{ method: "DELETE" }});
          if (!response.ok) {{
            throw new Error("The backend rejected the disconnect request.");
          }}
          stopFeed();
          setStatus("This phone source was disconnected. You can close the page now.", "warn");
          startButton.disabled = true;
          stopButton.disabled = true;
        }} catch {{
          disconnectButton.disabled = false;
          setStatus("The source could not be disconnected from the backend.", "warn");
        }}
      }}

      startButton.addEventListener("click", () => {{
        void startFeed();
      }});
      stopButton.addEventListener("click", stopFeed);
      disconnectButton.addEventListener("click", () => {{
        void disconnectSource();
      }});
      window.addEventListener("beforeunload", stopFeed);
    </script>
  </body>
</html>
"""


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


@router.get("/camera/sources")
async def list_camera_sources(request: Request) -> list[dict[str, Any]]:
    return [serialize_camera_source(request, source) for source in get_camera(request).list_sources()]


@router.post("/camera/sources")
async def register_camera_source(payload: CameraSourcePayload, request: Request) -> dict[str, Any]:
    source = get_camera(request).register_remote_source(payload.name or "")
    return serialize_camera_source(request, source)


@router.delete("/camera/sources/{source_id}")
async def disconnect_camera_source(source_id: str, request: Request) -> dict[str, bool]:
    source = get_camera_source(request, source_id)
    if source.get("kind") != "remote-phone":
        raise HTTPException(status_code=400, detail="Only remote phone sources can be disconnected")
    removed = get_camera(request).disconnect_source(source_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Camera source not found")
    return {"removed": True}


@router.put("/camera/sources/{source_id}/frame")
async def update_camera_source_frame(source_id: str, request: Request) -> dict[str, Any]:
    source = get_camera_source(request, source_id)
    if source.get("kind") != "remote-phone":
        raise HTTPException(status_code=400, detail="Frames can only be uploaded to remote phone sources")

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="A JPEG frame payload is required")

    updated = get_camera(request).update_remote_source_frame(source_id, image_bytes)
    if not updated:
        raise HTTPException(status_code=422, detail="The uploaded camera frame could not be decoded")
    return serialize_camera_source(request, updated)


@router.get("/camera/sources/{source_id}/stream")
async def stream_camera_source(source_id: str, request: Request) -> StreamingResponse:
    get_camera_source(request, source_id)
    stream = get_camera(request).iter_source_mjpeg_stream(source_id)
    return StreamingResponse(
        stream,
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/camera/connect/{source_id}", response_class=HTMLResponse)
async def camera_connect_page(source_id: str, request: Request) -> HTMLResponse:
    source = get_camera_source(request, source_id)
    if source.get("kind") != "remote-phone":
        raise HTTPException(status_code=404, detail="Phone camera source not found")
    return HTMLResponse(
        content=build_phone_connect_page(request, source),
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

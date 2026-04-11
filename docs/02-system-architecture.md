# System Architecture

## Stack Overview

The system is a two-part web application with a live vision-processing backend and a companion multi-camera network server.

### Backend

- `FastAPI`
- Python-based computer vision pipeline
- camera capture and MJPEG preview streaming
- scheduling with `APScheduler`
- persistence through `Supabase`
- SMS/MMS delivery through `Twilio`
- email delivery through `SendGrid`

### Frontend

- `Next.js`
- React client components
- onboarding and sign-in flow with patient and caregiver email capture
- dashboard for live monitoring, medicine history, faces, and alerts

### Intelligence Services

- `YOLOv8` for medicine bottle, person, knife, and scissors detection
- `Roboflow` hosted inference for fire and gun detection
- `Gemini` for medicine label extraction directly from cropped bottle images
- `face_recognition` for familiar/unfamiliar face matching

### Multi-Camera Network (`network` branch)

- `aiohttp` WebSocket server
- phone-as-camera architecture using browser `getUserMedia`
- real-time frame relay from any phone to a centralized dashboard
- client-side motion detection with server-side event broadcasting
- TLS support for secure local-network streaming

## High-Level Runtime Flow

1. the backend starts the detector, scheduler, and camera threads
2. the camera captures frames continuously
3. selected frames are processed through the safety pipeline
4. detections are interpreted into medicines, faces, and hazards
5. structured events are stored in Supabase
6. alerts and reminders are created when needed
7. notifications are dispatched through Twilio (SMS/MMS) and SendGrid (email) to both the patient and caregiver
8. the frontend polls and subscribes to changes to keep the dashboard current
9. the live preview stream shows the camera feed with server-side bounding boxes

## Backend Composition

The backend is assembled in [backend/main.py](/backend/main.py).

The application creates and wires:

- `SupabaseService`
- `TwilioService`
- `SendGridEmailService`
- `Detector`
- `MedicineOCR`
- `FaceManager`
- `ReminderScheduler`
- `ProcessingPipeline`
- `CameraProcessor`

This is a clean service graph:

- perception modules produce structured results
- storage modules persist them
- orchestration modules convert them into reminders or alerts
- notification modules deliver them through SMS, MMS, and email

## Notification Architecture

The notification system is multi-channel by design. Every alert-generating event dispatches through both the phone channel and the email channel, with independent cooldown tracking per channel.

### SMS and MMS (Twilio)

- SMS to the patient with short, direct language
- SMS to the caregiver with escalation framing
- MMS to the caregiver when an image crop is available
- soft-fail handling so Twilio outages do not crash the processing loop

### Email (SendGrid)

Email delivery is a first-class notification channel, implemented in [backend/services/email_service.py](/backend/services/email_service.py).

The email service is built on the SendGrid Mail Send v3 API and provides:

- dual-format delivery with both plain text and HTML for every message
- automatic HTML generation with styled layout, readable typography, and evidence images when available
- image evidence embedding with clickable links and inline rendering for hazard crops, medicine crops, and face images
- independent cooldown tracking per recipient and event type so email and SMS cooldowns do not interfere with each other
- graceful degradation when SendGrid credentials are not configured, falling back to dry-run logging instead of crashing
- TLS certificate handling through `certifi` for reliable outbound HTTPS in all environments
- configurable sender identity with `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME`, and optional `SENDGRID_REPLY_TO`

The HTML template uses:

- a centered card layout with white background and soft border radius
- paragraph-level text rendering preserving line breaks from the alert message
- a linked and inlined evidence image when an `image_url` is available
- safe HTML escaping on all dynamic content to prevent injection

### Where Email Is Dispatched

Email is sent in three distinct event paths:

1. **Hazard alerts** in [backend/processing/pipeline.py](/backend/processing/pipeline.py): when a hazard is detected, both the patient email and caregiver email receive an alert with subject line, escalation copy, and the hazard crop image when available.

2. **Unfamiliar face alerts** in [backend/processing/pipeline.py](/backend/processing/pipeline.py): when an unknown person is detected, both emails receive a warning with the face image attached.

3. **Medicine reminders** in [backend/services/scheduler.py](/backend/services/scheduler.py): when a scheduled reminder fires, the patient email receives a direct reminder and the caregiver email receives a notification with the patient name and medicine details.

Each dispatch uses a unique cooldown key per channel, so the same event can trigger both an SMS and an email without one blocking the other.

### Email Validation

Email addresses are validated on both the backend and frontend:

- the backend normalizes and validates emails in [backend/utils/email.py](/backend/utils/email.py) using a strict regex pattern before storage
- the frontend validates in [frontend/src/lib/email.ts](/frontend/src/lib/email.ts) before submission
- the `POST /api/patient` endpoint rejects payloads where an email was provided but fails validation

This means email fields are optional during onboarding, but if provided, they must be well-formed.

### Recipient Model

The notification system treats the patient and caregiver as a care pair. Every notification event generates two parallel delivery paths:

| Channel | Patient receives | Caregiver receives |
|---|---|---|
| SMS | short direct message | escalation-framed message |
| MMS | not used | image-backed escalation when crop available |
| Email | alert with evidence when available | identical alert with evidence when available |

The caregiver-facing copy across all channels is intentionally written as escalation language rather than generic event logging. SMS messages to the patient are deliberately brief. Email messages include richer context and image evidence because the format supports it.

## Data Model For Email

The `patients` table stores both email addresses as optional columns:

- `patient_email text` - the patient's own email address
- `caregiver_email text` - the caregiver's email address

These columns were added via `ALTER TABLE` migration in [supabase/schema.sql](/supabase/schema.sql) for backward compatibility with existing rows.

The frontend `Patient` type in [frontend/src/lib/types.ts](/frontend/src/lib/types.ts) and the `OnboardingPayload` in [frontend/src/components/AuthGate.tsx](/frontend/src/components/AuthGate.tsx) both expose `patient_email` and `caregiver_email` as optional fields.

The `PatientPayload` in [backend/api/routes.py](/backend/api/routes.py) accepts both emails, normalizes them, and persists them through `SupabaseService.upsert_patient`.

## API Surface

The API in [backend/api/routes.py](/backend/api/routes.py) exposes:

- health check
- patient lookup and creation (including email fields)
- session start, activate, and clear
- medicine listing
- familiar-face listing and labeling
- alerts listing and acknowledgment
- camera frame and live stream endpoints

This makes the frontend thin by design. The frontend does not own the safety logic; it renders the operational state exposed by the backend.

## Camera And Live Preview

The camera subsystem in [backend/processing/camera.py](/backend/processing/camera.py) runs two loops:

- a capture loop
- a processing loop

The capture loop:

- opens the webcam
- captures frames continuously
- encodes preview frames as JPEG with server-side bounding box overlays
- serves an MJPEG stream to the browser

The processing loop:

- respects a configurable frame interval
- pushes frames into the safety pipeline
- updates overlay state for the preview

An important product decision was to render bounding boxes server-side instead of in browser canvas code. That keeps the frontend simpler and ensures the live preview is already annotated when delivered.

## Multi-Camera Phone Network

The project includes a companion multi-camera surveillance server on the `network` branch that extends the platform's vision capabilities beyond a single laptop webcam.

### Architecture

The network server is built on `aiohttp` and uses a hub-and-spoke model:

- **Hub**: a Python WebSocket server ([server.py](/server.py) on the `network` branch) running on the local network
- **Spokes**: any iPhone or Android phone running the camera page in its native browser

There is no mobile app to install. The phone opens a URL, grants camera permission, and begins streaming.

### Phone-To-Server Protocol

1. the phone loads `/camera` and opens the device camera via `getUserMedia`
2. the phone sends `POST /api/register` with a human-readable name and receives a unique camera ID
3. the phone captures frames at approximately 6 fps, downscaled to 320px width
4. each frame is JPEG-encoded at 60% quality and posted as `multipart/form-data` to `POST /api/frame`
5. the server stores the latest frame and broadcasts it to all connected dashboard WebSocket clients as base64
6. if the phone detects motion, it sends `POST /api/motion` with the event; the server broadcasts a motion alert to all dashboards

### Client-Side Motion Detection

Motion detection runs entirely on the phone in JavaScript:

- each frame is compared to the previous frame pixel by pixel
- the absolute per-channel difference is averaged across RGB
- if the percentage of changed pixels exceeds `MOTION_PIXEL_RATIO` (default 1.5%) with per-pixel threshold `MOTION_THRESHOLD` (default 25), motion is flagged
- motion state changes are sent to the server for real-time dashboard updates and toast notifications

### Dashboard

The network dashboard ([static/dashboard.html](/static/dashboard.html) on the `network` branch) provides:

- a real-time camera grid with live frame updates via WebSocket
- per-camera status indicators: online, offline, connecting
- motion event badges and toast notifications
- motion event counters per camera
- automatic stale-camera cleanup when a phone goes offline for more than 10 seconds
- a WebSocket reconnection loop with automatic recovery
- responsive grid layout that adapts to the number of connected cameras

### Network Requirements

- all devices must be on the same WiFi network or reachable via Tailscale or similar overlay
- the server supports TLS via self-signed certificates for HTTPS camera access on phones
- iPhone requires Safari (iOS 14.5+); Android requires Chrome
- the phone screen must remain on while streaming

### Relationship To The Main Application

The network server is a standalone companion that provides additional camera coverage. The conceptual relationship is:

- the `main` branch runs the full safety pipeline on frames from the laptop webcam
- the `network` branch collects frames from any number of phones and displays them on a centralized dashboard with motion detection

The intended integration path is for the network server to feed phone-captured frames into the same `ProcessingPipeline` that the main backend uses, enabling medicine detection, face recognition, and hazard detection from any phone camera in the home.

## Data Layer

The system uses Supabase for:

- `patients` (including `patient_email` and `caregiver_email`)
- `medicines`
- `reminders`
- `known_faces`
- `alerts`
- image storage in the `detection-images` bucket

The schema is defined in [supabase/schema.sql](/supabase/schema.sql).

This gives the application both operational data and durable evidence objects:

- medicine crops
- hazard crops
- face images

## Reminder Scheduling

The scheduler in [backend/services/scheduler.py](/backend/services/scheduler.py) loads active reminders on startup and converts them into cron jobs.

That means medicines are not only stored as records; they are operationalized into future actions.

When a reminder fires, the scheduler dispatches notifications through both Twilio and SendGrid:

- the patient receives an SMS and an email with the medicine name and dosage
- the caregiver receives an SMS and an email with the patient name and medicine details
- each channel has independent cooldown tracking so duplicate deliveries are suppressed without cross-channel interference

## Frontend Architecture

The frontend organizes the experience around:

- `AuthGate` for onboarding and sign-in, with fields for patient email and caregiver email
- `AppShell` for session restoration
- `Dashboard` for medicine, face, and alert state
- `StatusBanner` for live camera coverage
- `MedicinePanel`, `FacesPanel`, and `AlertsFeed` for core monitoring views

The onboarding form captures six fields: patient name, patient phone, patient email, caregiver name, caregiver phone, and caregiver email. Phone numbers are required; email addresses are optional but validated when provided.

The dashboard refreshes on an active cadence rather than waiting for a manual page reload, which materially improves the feel of the medicine workflow.

## Resilience Characteristics

Several robustness improvements are already in place:

- Twilio failures fail soft instead of crashing the pipeline
- SendGrid failures fail soft with structured logging and do not block SMS delivery
- Supabase upload logic uses the byte payload format the SDK expects
- Roboflow authorization failures trigger backoff instead of repeated wasteful retries
- blurry medicine crops are rejected before extraction
- duplicate medicine names are normalized before new records are created
- email and SMS cooldowns are tracked independently so one channel's cooldown does not suppress the other

These are not cosmetic details. They are the difference between a demo that "works once" and a system that can keep running during imperfect real-world conditions.

## Environment Variables For Notifications

The notification layer is configured through environment variables defined in `.env`:

| Variable | Purpose |
|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account identifier |
| `TWILIO_AUTH_TOKEN` | Twilio authentication secret |
| `TWILIO_PHONE_NUMBER` | sender phone number for SMS and MMS |
| `SENDGRID_API_KEY` | SendGrid API key for email delivery |
| `SENDGRID_FROM_EMAIL` | verified sender email address |
| `SENDGRID_FROM_NAME` | display name on outbound emails (defaults to "VALIANT") |
| `SENDGRID_REPLY_TO` | optional reply-to address |
| `ALERT_COOLDOWN_SECONDS` | minimum seconds between repeated alerts of the same type |

When `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` are both set, email delivery is live. When either is missing, the service logs a degraded-mode warning and runs in dry-run mode.

## Architecture Summary

The architecture is strong because it is layered correctly:

- capture (webcam and phone cameras)
- detect
- interpret
- persist
- schedule
- notify (SMS, MMS, and email)
- visualize (Next.js dashboard and multi-camera network dashboard)

That is the right shape for a safety product.

# System Architecture

## Stack Overview

The system is a two-part web application with a live vision-processing backend.

### Backend

- `FastAPI`
- Python-based computer vision pipeline
- camera capture and MJPEG preview streaming
- scheduling with `APScheduler`
- persistence through `Supabase`
- SMS/MMS delivery through `Twilio`

### Frontend

- `Next.js`
- React client components
- onboarding and sign-in flow
- dashboard for live monitoring, medicine history, faces, and alerts

### Intelligence Services

- `YOLOv8` for medicine bottle, person, knife, and scissors detection
- `Roboflow` hosted inference for fire and gun detection
- `Gemini` for medicine label extraction directly from cropped bottle images
- `face_recognition` for familiar/unfamiliar face matching

## High-Level Runtime Flow

1. the backend starts the detector, scheduler, and camera threads
2. the camera captures frames continuously
3. selected frames are processed through the safety pipeline
4. detections are interpreted into medicines, faces, and hazards
5. structured events are stored in Supabase
6. alerts and reminders are created when needed
7. the frontend polls and subscribes to changes to keep the dashboard current
8. the live preview stream shows the camera feed with server-side bounding boxes

## Backend Composition

The backend is assembled in [backend/main.py](/Users/vishruth/Desktop/Build/backend/main.py:24).

The application creates and wires:

- `SupabaseService`
- `TwilioService`
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

## API Surface

The API in [backend/api/routes.py](/Users/vishruth/Desktop/Build/backend/api/routes.py:1) exposes:

- health check
- patient lookup and creation
- session start, activate, and clear
- medicine listing
- familiar-face listing and labeling
- alerts listing and acknowledgment
- camera frame and live stream endpoints

This makes the frontend thin by design. The frontend does not own the safety logic; it renders the operational state exposed by the backend.

## Camera And Live Preview

The camera subsystem in [backend/processing/camera.py](/Users/vishruth/Desktop/Build/backend/processing/camera.py:16) runs two loops:

- a capture loop
- a processing loop

The capture loop:

- opens the webcam
- captures frames continuously
- encodes preview frames as JPEG
- serves an MJPEG stream to the browser

The processing loop:

- respects a configurable frame interval
- pushes frames into the safety pipeline
- updates overlay state for the preview

An important product decision was to render bounding boxes server-side instead of in browser canvas code. That keeps the frontend simpler and ensures the live preview is already annotated when delivered.

## Data Layer

The system uses Supabase for:

- `patients`
- `medicines`
- `reminders`
- `known_faces`
- `alerts`
- image storage in the `detection-images` bucket

The schema is defined in [supabase/schema.sql](/Users/vishruth/Desktop/Build/supabase/schema.sql:1).

This gives the application both operational data and durable evidence objects:

- medicine crops
- hazard crops
- face images

## Reminder Scheduling

The scheduler in [backend/services/scheduler.py](/Users/vishruth/Desktop/Build/backend/services/scheduler.py:1) loads active reminders on startup and converts them into cron jobs.

That means medicines are not only stored as records; they are operationalized into future actions.

## Notification Architecture

The current live implementation is centered on `Twilio`:

- SMS to the patient
- SMS or MMS to the caregiver depending on whether an image is attached

This distinction is important:

- patient communication is intentionally short and direct
- caregiver communication includes escalation framing and, when available, visual evidence

## Frontend Architecture

The frontend organizes the experience around:

- `AuthGate` for onboarding and sign-in
- `AppShell` for session restoration
- `Dashboard` for medicine, face, and alert state
- `StatusBanner` for live camera coverage
- `MedicinePanel`, `FacesPanel`, and `AlertsFeed` for core monitoring views

The dashboard now refreshes on an active cadence rather than waiting for a manual page reload, which materially improves the feel of the medicine workflow.

## Resilience Characteristics

Several robustness improvements are already in place:

- Twilio failures fail soft instead of crashing the pipeline
- Supabase upload logic uses the byte payload format the SDK expects
- Roboflow authorization failures trigger backoff instead of repeated wasteful retries
- blurry medicine crops are rejected before extraction
- duplicate medicine names are normalized before new records are created

These are not cosmetic details. They are the difference between a demo that “works once” and a system that can keep running during imperfect real-world conditions.

## Architecture Summary

The architecture is strong because it is layered correctly:

- capture
- detect
- interpret
- persist
- schedule
- notify
- visualize

That is the right shape for a safety product.

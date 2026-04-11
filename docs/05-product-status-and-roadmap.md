# Product Status And Roadmap

## What Has Already Been Achieved

This project has moved beyond the stage where the main question is whether the idea can be built.

It can.

The current system already includes:

- patient onboarding and sign-in with email capture for both patient and caregiver
- persistent patient, medicine, face, reminder, and alert records in Supabase
- live camera preview in the dashboard with server-side bounding boxes
- medicine bottle detection
- Gemini-based medicine label extraction
- duplicate-aware medicine normalization
- reminder generation and scheduler registration
- familiar-face accumulation and unfamiliar-face warning logic
- hazard detection and escalation
- SMS and MMS notification plumbing through Twilio
- email notification delivery through SendGrid with dual-format HTML and plain text
- multi-channel notification dispatch with independent cooldown tracking
- email validation on both frontend and backend
- dashboard views for medicines, faces, alerts, and live status
- a companion multi-camera network server for phone-based surveillance

## Recently Achieved Milestones

Recent progress materially improved the system:

- **Email notifications**: full SendGrid integration with styled HTML templates, image evidence embedding, and independent cooldown tracking across all alert types
- **Patient and caregiver email capture**: onboarding flow updated to collect optional email addresses with validation on both frontend and backend
- **Multi-channel dispatch**: every alert-generating event now sends through both SMS/MMS and email in parallel, with independent rate limiting per channel
- **Multi-camera phone network**: a companion server that turns any phone into a surveillance camera streaming through the browser with real-time motion detection
- direct Gemini label extraction replaced the weaker OCR-first approach
- bottle quality gates were added so blurry crops are skipped
- medication parsing quality improved on real sample imagery
- duplicate medicines are now reconciled more intelligently
- Supabase image upload handling was fixed
- Twilio sending now fails soft instead of breaking processing
- SendGrid sending fails soft with structured error logging
- Roboflow authorization failures now back off instead of retrying aggressively
- the camera stream now renders bounding boxes server-side
- the frontend now refreshes dashboard data automatically without manual reload

These changes are exactly the kind that make an MVP feel operational rather than fragile.

## What The Current Build Is Best At

The current build is strongest as:

- a working prototype for caregiver safety monitoring with multi-channel notifications
- a technical demonstration of a complete perception-to-action loop from camera to SMS and email
- a foundation for a more clinically rigorous household safety product
- a multi-camera surveillance platform that works with commodity phones and no app installation

## Multi-Camera Network Status

The `network` branch contains a working multi-camera server:

### What Works Today

- phone registration with human-readable camera names
- real-time frame streaming from phone to dashboard via HTTP and WebSocket
- client-side motion detection with server-side broadcast
- dashboard with live camera grid, status indicators, motion alerts, and toast notifications
- automatic stale-camera cleanup when a phone disconnects
- TLS support for secure local-network access
- works on Safari (iOS 14.5+) and Chrome (Android) with no app installation

### Current Architecture

- `aiohttp`-based Python server running on the local network
- phones connect via browser and use `getUserMedia` for camera access
- frames are captured at ~6 fps, downscaled to 320px, JPEG-encoded at 60% quality
- frames are relayed to the dashboard via WebSocket as base64
- motion events are tracked per camera with a rolling history of 200 events

### Integration Path

The multi-camera server currently operates as a standalone companion. The intended integration is:

1. the network server collects frames from multiple phones
2. those frames are forwarded to the `ProcessingPipeline` from the main backend
3. this enables medicine detection, face recognition, and hazard detection from any phone camera
4. alerts and notifications generated from phone cameras flow through the same Twilio and SendGrid channels

## What Is Production-Shaped But Not Yet Production-Finished

Several pieces have the right architecture but still need deeper hardening.

### Medication Validation

The current system performs real internal validation and persistence, but a production deployment should add formal medication-registry verification.

### Notifications

Both phone-based (Twilio) and email-based (SendGrid) notifications are live in the architecture. Areas for further hardening:

- delivery receipt tracking and retry on transient failures
- email bounce and complaint handling
- daily or weekly digest emails for lower-urgency events
- push notifications for mobile devices

### Multi-Camera Pipeline Integration

The network server streams frames and detects motion. The next step is feeding phone-captured frames into the main vision pipeline for full safety analysis.

### Security

The current build is designed for rapid iteration. A production system should strengthen:

- authentication
- authorization
- patient-data access control
- audit logging
- secret handling and deployment hygiene

### Reliability

The system already includes several resilience improvements, but production readiness would require:

- stronger retry policy design
- queueing and dead-letter strategies
- better observability
- deployment health checks
- more explicit fault domains between vision, storage, and notification services

## Recommended Next Milestones

### 1. Registry-Backed Medication Validation

Add a formal medication registry or clinical drug database integration so extracted labels can be verified, normalized, and enriched.

### 2. Phone Camera Pipeline Integration

Connect the multi-camera network server to the main `ProcessingPipeline` so phone-captured frames get the same medicine, face, and hazard analysis as the laptop webcam.

### 3. Enhanced Email Notifications

Build on the existing SendGrid integration:

- daily summary digests for caregivers
- weekly incident reports with statistics
- configurable notification preferences per channel
- delivery tracking and retry logic

### 4. Human Review Workflow

Allow a caregiver to confirm or correct:

- medicine names
- reminder schedules
- face labels
- false hazard detections

### 5. Stronger Identity And Care Roles

Introduce explicit roles such as:

- patient
- caregiver
- family admin
- clinical observer

### 6. Mobile-Friendly Escalation Experience

The current web dashboard is useful, but push-oriented mobile flows would better match real caregiver behavior.

## Risks And Constraints

The main current risks are:

- visual quality variance from real home camera conditions
- imperfect medicine extraction under glare or occlusion
- heuristic reminder interpretation
- lack of formal clinical data validation
- dependence on third-party services for alerts and hosted hazard models
- phone camera streaming requires the screen to remain on

These are real constraints, but they do not undermine the core achievement of the project. They define the next engineering priorities.

## Why This Project Is Strong

The strongest thing about this project is not any one model.

It is that the system has a coherent product loop:

- a real caregiving problem
- a rational architecture
- working perception from both laptop and phone cameras
- persistent data
- multi-channel notifications through SMS, MMS, and email
- a dashboard that closes the loop
- a camera network that extends coverage

That coherence is what makes the project investable, extensible, and worth continuing.

## Final Assessment

This is a serious MVP for Alzheimer's home safety assistance.

It already demonstrates:

- technical feasibility
- product clarity
- real user motivation
- meaningful end-to-end execution
- multi-channel notification delivery
- extensible multi-camera architecture

The next phase should focus on making the system more trustworthy, more clinically grounded, and more operationally robust without losing the simplicity that makes it usable for families.

## Recommended Positioning

The best way to describe the project is:

**an ambient safety and medication-support platform for Alzheimer's care, built to help families move from reactive monitoring to proactive awareness, with multi-channel notifications and extensible multi-camera coverage.**

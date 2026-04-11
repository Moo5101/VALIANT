# Safety Monitoring And Notifications

## Safety Scope

The project monitors three categories of household risk:

- medication adherence context
- unfamiliar human presence
- physical hazards

These are not random features. They map directly to common family concerns in Alzheimer’s care:

- Was the medicine identified and scheduled?
- Is someone near the patient who should not be ignored?
- Is there an immediate danger in the room?

## Familiar And Unfamiliar Face Logic

The familiar-face system is implemented in [backend/processing/face_manager.py](/Users/vishruth/Desktop/Build/backend/processing/face_manager.py:1).

The workflow is:

1. detect faces in the frame
2. encode them with `face_recognition`
3. compare the embedding to known stored encodings
4. update existing records when a match is found
5. create a new unknown-face record when no match exists
6. promote a face to familiar after enough repeated sightings

This is a pragmatic care-oriented model:

- repeated exposure builds familiarity over time
- the system does not require a perfect pre-labeled face set to start being useful

## Unknown Visitor Alerts

When a new face appears in an environment that already has familiar faces, the system can flag that face as unfamiliar and create an alert.

The alert includes:

- a warning severity
- explanatory copy
- the associated face image when available
- delivery routing to both patient and caregiver channels

## Hazard Detection

Hazard detection currently combines:

- `YOLOv8` for knives and scissors
- `Roboflow` hosted models for fire and gun detection

The backend normalizes hazard classes into care-oriented labels such as:

- `sharp object`
- `weapon`
- `fire`

This is a product-quality decision. It keeps downstream messaging clean and understandable.

## Hazard Escalation

Hazard detections are treated as critical events.

The system:

- captures an image crop when possible
- stores an alert record
- sends a short warning to the patient
- sends an escalation message to the caregiver
- uses MMS when an image is available

The caregiver-facing copy is explicitly written as escalation language rather than generic event logging.

## Notification Channels

### Live Today

The implemented notification path is currently based on Twilio:

- SMS
- MMS

The backend has soft-fail handling, so a Twilio outage does not take down the frame-processing loop.

### Designed For Expansion

The broader notification strategy is intentionally multi-channel.

The product should support:

- SMS
- MMS
- email
- push or mobile notifications in a future version

### Email Notifications

Email notifications are part of the intended communication model, even if the current build is still centered on Twilio-based phone delivery.

Email matters for several reasons:

- caregivers often want an asynchronous written record
- email is a good fit for daily summaries and lower-urgency events
- image evidence, timeline context, and grouped reports are often better consumed in email than SMS

The system architecture already points in that direction:

- structured alerts exist as persistent records
- medicines, reminders, and incidents are all stored centrally
- a notification service abstraction can expand beyond Twilio cleanly

In other words, email is not a disconnected idea. It is a natural next extension of the existing event model.

## Dashboard Monitoring

The frontend provides a live operational view of:

- current patient session
- medicine schedule
- known and unknown faces
- recent alerts
- camera preview with server-side bounding boxes

This is crucial because notifications alone are not enough. Caregivers also need a place to inspect the system’s current state.

## Why The Overlay Matters

The camera preview now includes bounding boxes for:

- medicines
- faces
- hazards

That serves two purposes:

- it helps users understand what the system thinks it is seeing
- it gives immediate visual trust in the inference pipeline

For safety software, interpretability is not optional. It is part of usability.

## Data As Evidence

The system does not only raise alerts. It also stores evidence:

- medicine crop images
- hazard images
- face images
- timestamps
- acknowledgment state

That gives the project the beginnings of a real audit trail.

## Safety Monitoring Summary

The system’s safety model is effective because it does not treat every event equally.

- medicines become reminders
- unfamiliar people become warnings
- hazards become escalations

That event taxonomy is one of the strongest product decisions in the current build.

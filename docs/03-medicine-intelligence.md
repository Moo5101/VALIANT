# Medicine Intelligence

## What This Part Of The Product Does

The medication workflow is one of the most important parts of the system.

Its job is to turn a bottle seen by the camera into a usable care artifact:

- a medicine record
- a dosage
- frequency or usage instructions when available
- reminder times
- an image-backed audit trail
- SMS and email notifications at scheduled times

## End-To-End Flow

The medication path is implemented primarily in:

- [backend/processing/detector.py](/backend/processing/detector.py)
- [backend/processing/medicine_ocr.py](/backend/processing/medicine_ocr.py)
- [backend/processing/pipeline.py](/backend/processing/pipeline.py)
- [backend/services/supabase_service.py](/backend/services/supabase_service.py)
- [backend/services/scheduler.py](/backend/services/scheduler.py)
- [backend/services/email_service.py](/backend/services/email_service.py)

The flow is:

1. YOLO detects a bottle-class object
2. the crop is padded and extracted
3. blurry crops are rejected before label extraction
4. Gemini reads the bottle image directly
5. the response is normalized into `name`, `dosage`, `frequency`, `instructions`, and raw text
6. plausibility checks reject obviously bad parses
7. duplicate medication names are canonicalized
8. the medicine is stored in Supabase
9. reminder times are derived from the frequency text
10. APScheduler jobs are registered
11. when a reminder fires, the patient receives an SMS and email; the caregiver receives an SMS and email

## Detection Layer

The current detector maps COCO bottle detections to the project's `medicine` category.

This is intentionally practical:

- it avoids needing a custom medicine-bottle detector to reach MVP functionality
- it leverages the strong baseline availability of YOLOv8
- it creates a clean bridge from generic bottle detection into domain-specific medication logic

## Gemini-Based Label Extraction

The current build is **Gemini-only** for medicine label extraction.

This matters because the earlier OCR-first approach produced low-quality text under real webcam conditions. The current implementation sends the cropped bottle image directly to Gemini and asks for a structured JSON response.

The extraction target is:

- `name`
- `dosage`
- `frequency`
- `instructions`
- `raw_text`

This is the right move for a prototype like this:

- bottle labels are noisy
- perspective and glare are common
- traditional OCR alone often returns garbage
- a multimodal model can reason over partial or messy text more effectively

## Current Validation Logic

The medication pipeline does not blindly trust the model output.

It currently applies multiple safeguards:

- blur rejection through a focus score (Laplacian variance)
- name normalization to remove noise characters
- plausibility filters on length and token count
- blocked words to reject non-medicine label text (e.g., "pharmacy", "patient", "instructions", "directions", "refill", "prescriber", "doctor", "label", "needed")
- medicine-marker checks such as `mg`, `mcg`, `ml`, `tablet`, `capsule`, `dose`, and `rx`
- duplicate matching across canonicalized medicine names with fuzzy substring matching
- dosage-unit and form-word stripping for canonicalization so "Nateglinide" and "Nateglinide Tablets USP" resolve to the same medicine

## Medicine Database Strategy

Medication verification in this project should be understood in two layers.

### Layer 1: Internal Medicine Database

Today, the application already maintains a structured medicine database inside Supabase:

- detected medicines are stored persistently
- names are normalized
- variants like `Nateglinide` and `Nateglinide Tablets USP` are reconciled
- reminders are attached to the same logical medicine record

In that sense, the product already checks new detections against a medicine database: the project's own normalized medicine store.

### Layer 2: External Medication Registry

For production hardening, the intended next step is explicit validation against a formal medication registry or drug database.

Examples of suitable production-grade sources would include:

- RxNorm
- NDC-backed datasets
- openFDA-derived medication metadata
- a commercial clinical medication database

The purpose of that layer would be to:

- confirm that an extracted medicine name is real
- normalize brand and generic variants
- validate dosage forms and units
- reduce hallucinated or corrupted medicine names
- support richer reminder and safety rules

This is an important distinction:

- the current build has working internal medicine validation and persistence
- the external medication-registry integration is the next level of rigor

## Reminder Generation

The current reminder engine derives schedule times from frequency text using heuristics.

Examples:

- `twice daily` becomes morning and evening reminders (09:00, 21:00)
- `three times daily` becomes three reminders (08:00, 14:00, 20:00)
- `every 12 hours` becomes two evenly spaced reminders (08:00, 20:00)
- `every 8 hours` becomes three reminders (06:00, 14:00, 22:00)
- `morning` becomes one morning reminder (09:00)
- `evening` or `bedtime` becomes one evening reminder (20:00)
- explicit times like `08:30` are used directly
- when no frequency is parseable, the system defaults to a single morning reminder (09:00)

This is intentionally MVP-friendly:

- it works without requiring the user to manually enter times
- it makes the demo path powerful immediately
- it is easy to replace later with richer medication scheduling logic

## Reminder Delivery

When a scheduled reminder fires, the scheduler dispatches notifications through all configured channels.

### SMS Delivery (Twilio)

- **Patient**: "Time to take {medicine_name} {dosage}"
- **Caregiver**: "Reminder: {patient_name} should take {medicine_name} {dosage}"

### Email Delivery (SendGrid)

- **Patient**: subject "Medicine reminder: {medicine_name}", body identical to the SMS text, with styled HTML formatting
- **Caregiver**: subject "Reminder for {patient_name}: {medicine_name}", body identical to the SMS text, with styled HTML formatting

Each channel has an independent cooldown key:

| Key | Channel |
|---|---|
| `reminder:patient:{reminder_id}` | patient SMS |
| `reminder:caregiver:{reminder_id}` | caregiver SMS |
| `reminder-email:patient:{reminder_id}` | patient email |
| `reminder-email:caregiver:{reminder_id}` | caregiver email |

This means a duplicate SMS suppression does not prevent the email from going through, and vice versa.

After all notifications are dispatched, the scheduler calls `supabase.mark_reminder_sent` to record the delivery timestamp.

## Image Evidence

Every accepted medicine detection can persist its crop image to Supabase storage.

That gives the system:

- a visual audit artifact
- a way to inspect false positives
- better caregiver trust
- a basis for future human review workflows

## What Has Already Been Proven

The medication path has already been validated end to end in the current project lifecycle:

- Gemini successfully parsed a real bottle sample as `Nateglinide` / `60 mg`
- the medicine was stored in Supabase
- the crop image uploaded successfully
- the API returned the saved medicine
- the reminder was registered in the scheduler
- the notification channels (SMS and email) are wired and tested

That is an important milestone because it shows the loop is not theoretical.

## Limitations

The current medication intelligence layer is strong for an MVP, but it is not yet a production-grade medication reconciliation system.

Current limitations include:

- no formal external drug registry lookup yet
- no pharmacy-grade dosage or interaction logic
- frequency-to-time mapping is heuristic
- image quality still matters for successful extraction
- the system assumes the visible bottle is relevant to the active patient

## Why This Still Matters

Even with those limitations, this subsystem solves a real problem:

it removes manual entry from the first step of medication tracking.

That is strategically important because manual entry is often exactly where caregiver workflows break down.

# Alzheimer Safety Dashboard MVP

This repository contains a two-part MVP for an Alzheimer support dashboard:

- A `FastAPI` backend that captures webcam frames, runs computer vision tasks, stores results in Supabase, and sends SMS or MMS alerts through Twilio.
- A `Next.js` dashboard for patients and caregivers to review medicines, familiar faces, alerts, and live camera status.

## Features

- Medicine bottle detection with YOLOv8
- Gemini label extraction from medicine images
- Familiar face auto-learning with `face_recognition`
- Hazard detection for knives and scissors with YOLOv8
- Hazard detection for fire and guns with Roboflow hosted inference
- SMS and MMS alerts to both patient and caregiver via Twilio
- Reminder scheduling with APScheduler
- Supabase-backed storage, alerts, medicines, reminders, and face records

## Project Layout

```text
repo/
├── backend/
│   ├── api/
│   ├── processing/
│   ├── services/
│   ├── config.py
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   └── .env.local.example
├── supabase/
│   └── schema.sql
└── .env.example
```

## Environment

1. Copy `.env.example` to `.env` for the backend.
2. Copy `frontend/.env.local.example` to `frontend/.env.local` for the dashboard.
3. Fill in:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SUPABASE_SERVICE_KEY`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
   - `ROBOFLOW_API_KEY`
   - `GEMINI_API_KEY`

## Database Setup

Apply [supabase/schema.sql](/Users/vishruth/Desktop/Build/supabase/schema.sql) in the Supabase SQL editor or through the CLI. The schema creates:

- `patients`
- `medicines`
- `reminders`
- `known_faces`
- `alerts`
- The public storage bucket `detection-images`

## Backend Runbook

1. Create a Python 3.11 virtual environment.
2. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Start the API:

```bash
uvicorn backend.main:app --reload
```

The backend starts the reminder scheduler automatically and attempts to start the webcam loop on launch.

## Frontend Runbook

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Start the dashboard:

```bash
npm run dev
```

3. Open `http://localhost:3000`.

On a fresh install, the dashboard opens into an onboarding or sign-in flow instead of requiring a preconfigured patient ID.

## API Endpoints

- `GET /api/health`
- `GET /api/patient/by-phone?phone=...`
- `GET /api/patient/{id}`
- `POST /api/patient`
- `POST /api/session/start`
- `POST /api/session/activate/{patient_id}`
- `POST /api/session/clear`
- `GET /api/medicines/{patient_id}`
- `GET /api/faces/{patient_id}`
- `PUT /api/faces/{face_id}/label`
- `GET /api/alerts/{patient_id}`
- `PUT /api/alerts/{alert_id}/acknowledge`
- `GET /api/camera/frame`

## Operational Notes

- The backend is resilient to missing third-party credentials and will log degraded-mode warnings instead of crashing where possible.
- YOLO and `face_recognition` are heavyweight dependencies. Expect longer first-run setup time.
- Medicine reminder times are inferred from parsed label frequency text using simple heuristics in the MVP.
- Supabase Realtime is wired on the frontend for the `alerts` table. If anon policies are restricted, the dashboard will still update through periodic polling.
- The backend can optionally start with `PATIENT_ID`, but the normal flow is now patient activation through sign-in or onboarding.

# Full System Pipeline Diagram

```
                            ALZHEIMER SAFETY DASHBOARD - FULL PIPELINE
================================================================================================

    CAMERA INPUT                    DETECTION LAYER                    PROCESSING PIPELINE
    ============                    ===============                    ===================

 +----------------+          +---------------------------+
 |   Webcam       |          |       Detector            |
 | (OpenCV        |  frame   |                           |
 |  capture loop) |--------->|  +---------------------+  |
 |                |          |  |  YOLOv8 (local)     |  |
 +-------+--------+          |  |  - bottle (medicine) |  |
         |                   |  |  - person            |  |
         |                   |  |  - knife             |  |
         | MJPEG stream      |  |  - scissors          |  |
         | (with bounding    |  +---------------------+  |
         |  boxes drawn      |                           |
         |  server-side)     |  +---------------------+  |
         |                   |  |  Roboflow (hosted)   |  |
         v                   |  |  - fire              |  |
 +----------------+          |  |  - gun/weapon        |  |
 | Browser Live   |          |  +---------------------+  |
 | Camera Preview |          +---------------------------+
 +----------------+                     |
                                        | list[Detection]
                                        | (category, label,
                                        |  confidence, crop)
                                        v
                          +-----------------------------------+
                          |     ProcessingPipeline            |
                          |     (process_frame)               |
                          +-----------------------------------+
                          |                                   |
                 +--------+--------+-----------+              |
                 |                 |           |              |
                 v                 v           v              |
          medicine           hazard       person             |
          detections         detections   detections          |
                 |                 |           |              |
                 v                 v           v              |
                                                             |
================================================================================================

   MEDICINE PATH              HAZARD PATH              FACE PATH
   =============              ===========              =========

 +------------------+    +------------------+    +------------------------+
 | Quality Gate     |    | Normalize Label  |    | FaceManager            |
 | - blur rejection |    | - knife/scissors |    | (face_recognition lib) |
 |   (Laplacian     |    |   -> "sharp obj" |    |                        |
 |    focus score)  |    | - gun/pistol/etc |    | 1. Detect faces        |
 +--------+---------+    |   -> "weapon"    |    | 2. Encode embedding    |
          |              | - fire -> "fire" |    | 3. Compare to known    |
          v              +--------+---------+    |    stored encodings    |
 +------------------+             |              | 4. Match -> update     |
 | MedicineOCR      |             |              |    last_seen           |
 | (Gemini Vision)  |             |              | 5. No match -> create  |
 |                  |             |              |    new unknown face    |
 | Sends cropped    |             |              | 6. Promote to familiar |
 | bottle image to  |             |              |    after N sightings   |
 | Gemini API for   |             |              +----------+-------------+
 | structured JSON: |             |                         |
 | - name           |             |                         |
 | - dosage         |             |                         | unfamiliar?
 | - frequency      |             |                         |
 | - instructions   |             |                         v
 | - raw_text       |             |              +------------------+
 +--------+---------+             |              | Unfamiliar Face  |
          |                       |              | Alert Generation |
          v                       |              | (if new face in  |
 +------------------+             |              |  known env)      |
 | Validation Layer |             |              +--------+---------+
 | - name normalize |             |                       |
 | - length check   |             |                       |
 | - blocked words  |             |                       |
 | - medicine       |             |                       |
 |   markers check  |             |                       |
 |   (mg, tablet,   |             |                       |
 |    capsule, rx)  |             |                       |
 | - plausibility   |             |                       |
 +--------+---------+             |                       |
          |                       |                       |
          v                       |                       |
 +------------------+             |                       |
 | Duplicate Check  |             |                       |
 | - exact match    |             |                       |
 | - fuzzy match    |             |                       |
 |   (canonicalized |             |                       |
 |    name keys)    |             |                       |
 +--------+---------+             |                       |
          |                       |                       |
          v                       v                       v

================================================================================================

                            PERSISTENCE LAYER (Supabase)
                            ============================

    +-------------+     +-----------+     +-------------+     +----------+
    | medicines   |     | reminders |     | known_faces |     | alerts   |
    |-------------|     |-----------|     |-------------|     |----------|
    | id          |     | id        |     | id          |     | id       |
    | patient_id  |<-+  | medicine_ |     | patient_id  |     | patient_ |
    | name        |  |  |   id      |     | label       |     |   id     |
    | dosage      |  |  | patient_  |     | face_       |     | type     |
    | frequency   |  |  |   id      |     |   encoding  |     | severity |
    | instructions|  |  | reminder_ |     | image_url   |     | title    |
    | image_url   |  |  |   time    |     | times_seen  |     | message  |
    | raw_ocr_text|  |  | days_of_  |     | is_familiar |     | image_url|
    | detected_at |  |  |   week    |     | first_seen  |     | ack'd    |
    +-------------+  |  | is_active |     | last_seen   |     | created  |
                     |  +-----------+     +-------------+     +----------+
                     |
    +-------------+  |     +----------------------------+
    | patients    |--+     | detection-images (bucket)  |
    |-------------|        |----------------------------|
    | id          |        | medicines/YYYYMMDD/uuid.jpg|
    | name        |        | hazards/YYYYMMDD/uuid.jpg  |
    | phone       |        | faces/uuid.jpg             |
    | patient_    |        +----------------------------+
    |   email     |
    | caregiver_  |
    |   name      |
    | caregiver_  |
    |   phone     |
    | caregiver_  |
    |   email     |
    +-------------+

================================================================================================

                          SCHEDULING & NOTIFICATION LAYER
                          ===============================

 +---------------------------------------------+
 | ReminderScheduler (APScheduler)              |
 |                                              |
 | - Loads active reminders on startup          |
 | - Converts frequency -> cron jobs            |
 |   ("twice daily" -> 09:00, 21:00)            |
 |   ("every 8 hours" -> 06:00, 14:00, 22:00)  |
 |   ("morning" -> 09:00)                       |
 | - Fires at scheduled times                   |
 +----------------------+-----------------------+
                        |
                        | on trigger
                        v
 +---------------------------------------------+
 |           NOTIFICATION DISPATCH              |
 |                                              |
 |  +------------------+  +------------------+  |
 |  | Twilio Service   |  | SendGrid Email   |  |
 |  |                  |  |   Service         |  |
 |  | - SMS to patient |  | - Email to       |  |
 |  |   (short, direct)|  |   patient         |  |
 |  | - SMS to carer   |  | - Email to       |  |
 |  | - MMS to carer   |  |   caregiver       |  |
 |  |   (with image)   |  |   (with evidence) |  |
 |  | - Soft-fail on   |  |                   |  |
 |  |   errors         |  |                   |  |
 |  +------------------+  +------------------+  |
 +---------------------------------------------+
          |                        |
          v                        v
    +----------+            +------------+
    | Patient  |            | Caregiver  |
    | Phone    |            | Phone +    |
    +----------+            | Email      |
                            +------------+

================================================================================================

                          FRONTEND (Next.js Dashboard)
                          ============================

 +-----------------------------------------------------------------------+
 |                                                                       |
 |  AuthGate                                                             |
 |  (Onboarding / Sign-in by phone)                                     |
 |       |                                                               |
 |       v                                                               |
 |  AppShell                                                             |
 |  (Session restore, patient activation)                                |
 |       |                                                               |
 |       v                                                               |
 |  +----------------------------------------------------------------+  |
 |  |                      Dashboard                                 |  |
 |  |                                                                |  |
 |  |  +---------------------+  +---------------------+             |  |
 |  |  | Live Camera Feed    |  | StatusBanner        |             |  |
 |  |  | (MJPEG stream with  |  | (camera coverage    |             |  |
 |  |  |  bounding boxes)    |  |  indicator)         |             |  |
 |  |  +---------------------+  +---------------------+             |  |
 |  |                                                                |  |
 |  |  +---------------------+  +---------------------+             |  |
 |  |  | MedicinePanel       |  | FacesPanel          |             |  |
 |  |  | - Detected meds     |  | - Known faces       |             |  |
 |  |  | - Dosage info       |  | - Unknown faces     |             |  |
 |  |  | - Reminder times    |  | - Label editing     |             |  |
 |  |  | - Crop images       |  | - Familiarity count |             |  |
 |  |  +---------------------+  +---------------------+             |  |
 |  |                                                                |  |
 |  |  +--------------------------------------------------+         |  |
 |  |  | AlertsFeed                                        |         |  |
 |  |  | - Hazard SOS alerts (critical)                    |         |  |
 |  |  | - Unfamiliar face warnings                        |         |  |
 |  |  | - Medicine reminders (info)                       |         |  |
 |  |  | - Acknowledge button                              |         |  |
 |  |  | - Supabase Realtime subscription                  |         |  |
 |  |  +--------------------------------------------------+         |  |
 |  +----------------------------------------------------------------+  |
 +-----------------------------------------------------------------------+
          |                                       ^
          | API calls (polling + realtime)         | JSON responses
          v                                       |
 +-----------------------------------------------------------------------+
 |                   FastAPI Backend (/api/...)                           |
 |  GET  /health                                                         |
 |  POST /patient           GET /patient/{id}                            |
 |  POST /session/start     POST /session/activate/{id}                  |
 |  GET  /medicines/{id}    GET /faces/{id}    GET /alerts/{id}          |
 |  PUT  /faces/{id}/label  PUT /alerts/{id}/acknowledge                 |
 |  GET  /camera/frame      GET /camera/stream                           |
 +-----------------------------------------------------------------------+

================================================================================================

                          END-TO-END EVENT TAXONOMY
                          =========================

  Bottle in view -----> Medicine record -----> Reminders -----> SMS/Email at scheduled times
  (detect)              (extract+store)        (derive)         (notify)

  Unknown face -------> Face record ----------> Warning alert -> SMS/Email immediately
  (detect+encode)       (store)                 (escalate)      (notify)

  Knife/Fire/Gun -----> Hazard alert ---------> SOS message --> SMS/MMS/Email immediately
  (detect)              (store + image)         (escalate)      (notify with evidence)

================================================================================================
```

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router
from backend.config import get_settings
from backend.processing.camera import CameraProcessor
from backend.processing.detector import Detector
from backend.processing.face_manager import FaceManager
from backend.processing.medicine_ocr import MedicineOCR
from backend.processing.pipeline import ProcessingPipeline
from backend.services.scheduler import ReminderScheduler
from backend.services.supabase_service import SupabaseService
from backend.services.twilio_service import TwilioService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app() -> FastAPI:
    settings = get_settings()
    supabase = SupabaseService(settings)
    twilio = TwilioService(settings)
    detector = Detector(settings)
    medicine_ocr = MedicineOCR(settings)
    face_manager = FaceManager(settings, supabase)
    scheduler = ReminderScheduler(supabase, twilio)
    pipeline = ProcessingPipeline(
        settings=settings,
        detector=detector,
        medicine_ocr=medicine_ocr,
        face_manager=face_manager,
        supabase=supabase,
        twilio=twilio,
        scheduler=scheduler,
    )
    camera = CameraProcessor(settings, pipeline)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        detector.startup()
        if settings.patient_id:
            face_manager.load_known_faces(str(settings.patient_id))
        await scheduler.start()
        camera.start(str(settings.patient_id) if settings.patient_id else None)
        try:
            yield
        finally:
            camera.stop()
            await scheduler.stop()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins or [settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    app.state.settings = settings
    app.state.supabase = supabase
    app.state.twilio = twilio
    app.state.detector = detector
    app.state.medicine_ocr = medicine_ocr
    app.state.face_manager = face_manager
    app.state.scheduler = scheduler
    app.state.pipeline = pipeline
    app.state.camera = camera

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)

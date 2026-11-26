import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.transcript_api import router as transcription_router
from app.api.live_socket import router as websocket_router
from app.core.config import get_settings
from app.core.database import engine
from app.models import Transcription
from app.core.errors import register_error_handlers
from app.services.speech_engine_factory import SpeechEngineFactory

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Preloading faster-whisper model model_size=%s device=%s", settings.model_size, settings.device)
        await asyncio.to_thread(SpeechEngineFactory.create)
        logger.info("faster-whisper model ready")
    except Exception:
        logger.exception("faster-whisper model preload failed; it will retry on the first transcription")
    yield
    if engine is not None:
        await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Requested-With"],
)


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "alive", "service": settings.app_name}


app.include_router(router)
app.include_router(transcription_router)
app.include_router(websocket_router)
register_error_handlers(app)

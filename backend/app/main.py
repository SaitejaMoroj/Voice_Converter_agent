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

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])
app.include_router(router)
app.include_router(transcription_router)
app.include_router(websocket_router)
register_error_handlers(app)

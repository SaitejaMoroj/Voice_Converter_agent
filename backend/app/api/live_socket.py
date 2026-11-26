from fastapi import APIRouter, WebSocket

from app.api.live_session import run_transcription_session

router = APIRouter()


@router.websocket("/api/v1/transcription/stream")
@router.websocket("/ws/transcription")
async def stream_transcription(websocket: WebSocket) -> None:
    await run_transcription_session(websocket)


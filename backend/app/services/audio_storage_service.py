import os
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings


class AudioStorageError(ValueError):
    pass


class AudioStorageService:
    MEDIA_EXTENSIONS = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
    }

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        configured_dir = storage_dir or get_settings().audio_storage_dir
        if os.getenv("VERCEL") == "1":
            configured_dir = "/tmp/voxflow/audio"
        root = Path(configured_dir).expanduser()
        self.root = root.resolve()

    def store(self, transcription_id: UUID, content: bytes, content_type: str) -> tuple[str, str]:
        media_type = content_type.split(";", 1)[0].strip().lower()
        extension = self.MEDIA_EXTENSIONS.get(media_type)
        if extension is None:
            raise AudioStorageError("Unsupported audio format.")
        if not content:
            raise AudioStorageError("The uploaded audio file is empty.")

        self.root.mkdir(parents=True, exist_ok=True)
        storage_key = f"{transcription_id.hex}-{uuid4().hex}{extension}"
        target = self.path_for(storage_key)
        temporary = self.root / f".{transcription_id.hex}.{uuid4().hex}.tmp"
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return storage_key, media_type

    def path_for(self, storage_key: str) -> Path:
        candidate_key = Path(storage_key)
        if candidate_key.name != storage_key or candidate_key.is_absolute():
            raise AudioStorageError("Invalid audio storage key.")
        candidate = (self.root / candidate_key).resolve()
        if candidate.parent != self.root:
            raise AudioStorageError("Invalid audio storage key.")
        return candidate

    def remove(self, storage_key: str | None) -> None:
        if storage_key:
            self.path_for(storage_key).unlink(missing_ok=True)
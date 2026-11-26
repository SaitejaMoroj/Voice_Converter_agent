import asyncio
import logging
import time
from dataclasses import replace

from app.core.config import Settings, get_settings
from app.services.audio_processing_service import AudioProcessingError, AudioProcessingService
from app.services.speech_engine import SpeechEngine, SpeechRecognitionError, SpeechResult
from app.services.speech_engine_factory import SpeechEngineFactory

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(
        self,
        engine: SpeechEngine | None = None,
        audio_processor: AudioProcessingService | None = None,
        settings: Settings | None = None,
        provider: str = "faster-whisper",
    ) -> None:
        self.settings = settings or get_settings()
        self.engine = engine or SpeechEngineFactory.create(provider)
        self.audio_processor = audio_processor or AudioProcessingService(self.settings.audio_sample_rate)

    async def transcribe_pcm16(
        self,
        audio: bytes,
        *,
        sample_rate: int | None = None,
        language_override: str | None = None,
    ) -> SpeechResult:
        started_at = time.perf_counter()
        try:
            processed = self.audio_processor.process_pcm16(audio, sample_rate)
            language = language_override
            if language == "auto":
                language = None
            if not self.settings.enable_language_detection and language is None:
                language = self.settings.default_language
            result = await asyncio.to_thread(
                self.engine.transcribe,
                processed.samples,
                language=language,
                enable_language_detection=self.settings.enable_language_detection,
            )
            return replace(result, processing_time=time.perf_counter() - started_at)
        except AudioProcessingError:
            logger.warning("Invalid audio payload rejected")
            raise
        except SpeechRecognitionError:
            logger.exception("Speech engine failed")
            raise
        except Exception as exc:
            logger.exception("Unexpected transcription failure")
            raise SpeechRecognitionError("Speech recognition failed while processing this audio.") from exc
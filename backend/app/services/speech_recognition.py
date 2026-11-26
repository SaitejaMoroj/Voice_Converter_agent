import logging
import os
import threading
import time
from datetime import datetime, timezone

import numpy as np

from app.services.speech_engine import SpeechRecognitionError, SpeechResult, SpeechSegment

logger = logging.getLogger(__name__)


class FasterWhisperEngine:
    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel

            cpu_threads = max(1, min(4, os.cpu_count() or 1))
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
            )
            self._inference_lock = threading.Lock()
        except Exception as exc:
            logger.exception("Unable to load faster-whisper model", extra={"model_size": model_size, "device": device})
            raise SpeechRecognitionError("The configured speech model could not be loaded.") from exc

    def transcribe(
        self,
        audio: np.ndarray,
        *,
        language: str | None = None,
        enable_language_detection: bool = True,
    ) -> SpeechResult:
        started_at = time.perf_counter()
        selected_language = language
        if not enable_language_detection and selected_language is None:
            selected_language = "en"
        try:
            logger.info("[timing] Whisper inference started ts=%s samples=%d language=%s", datetime.now(timezone.utc).isoformat(), len(audio), selected_language or "auto")
            with self._inference_lock:
                segments_iter, info = self.model.transcribe(
                    audio,
                    language=selected_language,
                    vad_filter=True,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                )
                segments = [
                    SpeechSegment(
                        float(segment.start),
                        float(segment.end),
                        segment.text.strip(),
                        average_log_probability=getattr(segment, "avg_logprob", None),
                        no_speech_probability=getattr(segment, "no_speech_prob", None),
                        detected_language=info.language,
                    )
                    for segment in segments_iter
                    if segment.text.strip()
                ]
            elapsed = time.perf_counter() - started_at
            logger.info("[timing] Whisper inference completed ts=%s elapsed_seconds=%.3f segments=%d", datetime.now(timezone.utc).isoformat(), elapsed, len(segments))
            return SpeechResult(
                transcript_text=" ".join(segment.text for segment in segments).strip(),
                detected_language=info.language,
                segments=segments,
                processing_time=time.perf_counter() - started_at,
            )
        except Exception as exc:
            logger.exception("faster-whisper transcription failed")
            raise SpeechRecognitionError("Speech recognition failed while processing this audio.") from exc

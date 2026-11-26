import logging
import threading
import time

import numpy as np

from app.services.speech_engine import SpeechRecognitionError, SpeechResult, SpeechSegment

logger = logging.getLogger(__name__)


class FasterWhisperEngine:
    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel

            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
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
            with self._inference_lock:
                segments_iter, info = self.model.transcribe(
                    audio,
                    language=selected_language,
                    vad_filter=True,
                    beam_size=3,
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
            return SpeechResult(
                transcript_text=" ".join(segment.text for segment in segments).strip(),
                detected_language=info.language,
                segments=segments,
                processing_time=time.perf_counter() - started_at,
            )
        except Exception as exc:
            logger.exception("faster-whisper transcription failed")
            raise SpeechRecognitionError("Speech recognition failed while processing this audio.") from exc

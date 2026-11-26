from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    end: float
    text: str
    average_log_probability: float | None = None
    no_speech_probability: float | None = None
    detected_language: str | None = None


@dataclass(frozen=True)
class SpeechResult:
    transcript_text: str
    detected_language: str | None
    segments: list[SpeechSegment] = field(default_factory=list)
    processing_time: float = 0.0
    status: str = "completed"


@runtime_checkable
class SpeechEngine(Protocol):
    def transcribe(
        self,
        audio: np.ndarray,
        *,
        language: str | None = None,
        enable_language_detection: bool = True,
    ) -> SpeechResult:
        """Recognize mono float32 audio sampled at 16 kHz."""


class SpeechRecognitionError(RuntimeError):
    """Raised when a configured speech engine cannot process audio."""

from dataclasses import dataclass

import numpy as np

from app.core.config import get_settings


class AudioProcessingError(ValueError):
    """Raised when audio bytes do not match the supported PCM format."""


@dataclass(frozen=True)
class ProcessedAudio:
    samples: np.ndarray
    duration_seconds: float
    sample_rate: int


class AudioProcessingService:
    def __init__(self, target_sample_rate: int | None = None) -> None:
        self.target_sample_rate = target_sample_rate or get_settings().audio_sample_rate

    def process_pcm16(self, audio: bytes, sample_rate: int | None = None) -> ProcessedAudio:
        source_rate = sample_rate or self.target_sample_rate
        if source_rate < 8_000 or source_rate > 192_000:
            raise AudioProcessingError("Sample rate must be between 8 kHz and 192 kHz.")
        if not audio:
            raise AudioProcessingError("Audio payload is empty.")
        if len(audio) % 2:
            raise AudioProcessingError("PCM16 audio payload must contain complete 16-bit samples.")

        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        duration_seconds = len(samples) / source_rate
        if source_rate != self.target_sample_rate:
            target_count = max(1, round(duration_seconds * self.target_sample_rate))
            source_positions = np.arange(len(samples), dtype=np.float64)
            target_positions = np.arange(target_count, dtype=np.float64) * source_rate / self.target_sample_rate
            samples = np.interp(target_positions, source_positions, samples).astype(np.float32)

        return ProcessedAudio(
            samples=np.ascontiguousarray(samples, dtype=np.float32),
            duration_seconds=duration_seconds,
            sample_rate=self.target_sample_rate,
        )
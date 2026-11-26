import asyncio
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from app.core.config import Settings
from app.services.audio_processing_service import AudioProcessingError, AudioProcessingService
from app.services.speech_recognition import FasterWhisperEngine
from app.services.speech_engine import SpeechRecognitionError, SpeechResult, SpeechSegment
from app.services.speech_engine_factory import SpeechEngineFactory
from app.services.transcribe import TranscriptionService


class FakeEngine:
    def __init__(self):
        self.language = None
        self.detection_enabled = None

    def transcribe(self, audio, *, language=None, enable_language_detection=True):
        self.language = language
        self.detection_enabled = enable_language_detection
        return SpeechResult(
            transcript_text="नमस्ते hello",
            detected_language="hi",
            segments=[SpeechSegment(0.0, 0.8, "नमस्ते hello")],
        )


def test_audio_processor_decodes_pcm_and_resamples():
    processor = AudioProcessingService(target_sample_rate=16_000)
    samples = np.array([0, 16_384, -16_384, 32_767], dtype="<i2")

    result = processor.process_pcm16(samples.tobytes(), sample_rate=8_000)

    assert result.sample_rate == 16_000
    assert result.duration_seconds == pytest.approx(0.0005)
    assert result.samples.dtype == np.float32
    assert len(result.samples) == 8
    assert result.samples.max() <= 1
    assert result.samples.min() >= -1


@pytest.mark.parametrize("audio", [b"", b"\x01"])
def test_audio_processor_rejects_empty_or_incomplete_pcm(audio):
    with pytest.raises(AudioProcessingError):
        AudioProcessingService().process_pcm16(audio)


def test_transcription_service_applies_language_override_and_returns_result():
    engine = FakeEngine()
    service = TranscriptionService(
        engine=engine,
        audio_processor=AudioProcessingService(target_sample_rate=16_000),
        settings=Settings(_env_file=None, enable_language_detection=True),
    )
    pcm = np.zeros(16_000, dtype="<i2").tobytes()

    result = asyncio.run(service.transcribe_pcm16(pcm, language_override="hi"))

    assert engine.language == "hi"
    assert engine.detection_enabled is True
    assert result.transcript_text == "नमस्ते hello"
    assert result.detected_language == "hi"
    assert result.segments[0].end == 0.8
    assert result.processing_time >= 0
    assert result.status == "completed"


def test_transcription_service_auto_detects_language_without_override():
    engine = FakeEngine()
    service = TranscriptionService(
        engine=engine,
        audio_processor=AudioProcessingService(target_sample_rate=16_000),
        settings=Settings(_env_file=None, enable_language_detection=True),
    )

    result = asyncio.run(service.transcribe_pcm16(np.zeros(16, dtype="<i2").tobytes()))

    assert engine.language is None
    assert engine.detection_enabled is True
    assert result.detected_language == "hi"


def test_transcription_service_uses_configured_default_when_detection_disabled():
    engine = FakeEngine()
    service = TranscriptionService(
        engine=engine,
        audio_processor=AudioProcessingService(target_sample_rate=16_000),
        settings=Settings(_env_file=None, enable_language_detection=False, default_language="hi"),
    )

    asyncio.run(service.transcribe_pcm16(np.zeros(16, dtype="<i2").tobytes()))

    assert engine.language == "hi"
    assert engine.detection_enabled is False


def test_engine_factory_caches_loaded_provider(monkeypatch):
    calls = []

    def builder(model_size, device, compute_type):
        calls.append((model_size, device, compute_type))
        return FakeEngine()

    monkeypatch.setattr(
        "app.services.speech_engine_factory.get_settings",
        lambda: Settings(_env_file=None, model_size="small", device="cpu", compute_type="int8"),
    )
    SpeechEngineFactory.register_provider("test-cache", builder)
    SpeechEngineFactory.clear_cache()
    first = SpeechEngineFactory.create("test-cache")
    second = SpeechEngineFactory.create("test-cache")
    SpeechEngineFactory.clear_cache()

    assert first is second
    assert len(calls) == 1


def test_speech_configuration_reads_environment(monkeypatch):
    monkeypatch.setenv("MODEL_SIZE", "small")
    monkeypatch.setenv("DEVICE", "cuda")
    monkeypatch.setenv("COMPUTE_TYPE", "float16")
    monkeypatch.setenv("DEFAULT_LANGUAGE", "hi")
    monkeypatch.setenv("ENABLE_LANGUAGE_DETECTION", "false")

    settings = Settings(_env_file=None)

    assert settings.model_size == "small"
    assert settings.device == "cuda"
    assert settings.compute_type == "float16"
    assert settings.default_language == "hi"
    assert settings.enable_language_detection is False


def test_faster_whisper_returns_segments_and_detected_language(monkeypatch):
    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            assert (model_size, device, compute_type) == ("small", "cpu", "int8")

        def transcribe(self, audio, **kwargs):
            assert kwargs["language"] == "hi"
            segment = SimpleNamespace(
                start=0.1,
                end=0.9,
                text=" नमस्ते ",
                avg_logprob=-0.24,
                no_speech_prob=0.03,
            )
            return iter([segment]), SimpleNamespace(language="hi")

    fake_module = ModuleType("faster_whisper")
    fake_module.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    engine = FasterWhisperEngine("small", "cpu", "int8")
    result = engine.transcribe(np.zeros(16_000, dtype=np.float32), language="hi")

    assert result.transcript_text == "नमस्ते"
    assert result.detected_language == "hi"
    assert result.segments == [SpeechSegment(0.1, 0.9, "नमस्ते", -0.24, 0.03, "hi")]
    assert result.processing_time >= 0


def test_transcription_service_translates_engine_errors():
    class BrokenEngine:
        def transcribe(self, audio, *, language=None, enable_language_detection=True):
            raise RuntimeError("internal provider detail")

    service = TranscriptionService(
        engine=BrokenEngine(),
        audio_processor=AudioProcessingService(target_sample_rate=16_000),
    )

    with pytest.raises(SpeechRecognitionError, match="Speech recognition failed"):
        asyncio.run(service.transcribe_pcm16(np.zeros(16, dtype="<i2").tobytes()))
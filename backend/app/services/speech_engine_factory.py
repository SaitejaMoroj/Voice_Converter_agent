from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings
from app.services.speech_engine import SpeechEngine

EngineBuilder = Callable[[str, str, str], SpeechEngine]


def _build_faster_whisper(model_size: str, device: str, compute_type: str) -> SpeechEngine:
    from app.services.speech_recognition import FasterWhisperEngine

    return FasterWhisperEngine(model_size, device, compute_type)


class SpeechEngineFactory:
    _providers: dict[str, EngineBuilder] = {"faster-whisper": _build_faster_whisper}

    @classmethod
    def register_provider(cls, name: str, builder: EngineBuilder) -> None:
        if not name.strip():
            raise ValueError("Provider name cannot be empty")
        cls._providers[name.strip().lower()] = builder

    @classmethod
    def create(cls, provider: str = "faster-whisper") -> SpeechEngine:
        settings = get_settings()
        key = provider.strip().lower()
        try:
            builder = cls._providers[key]
        except KeyError as exc:
            raise ValueError(f"Unsupported speech engine provider: {key}") from exc
        return _cached_engine(builder, settings.model_size, settings.device, settings.compute_type)

    @classmethod
    def clear_cache(cls) -> None:
        _cached_engine.cache_clear()


@lru_cache(maxsize=8)
def _cached_engine(builder: EngineBuilder, model_size: str, device: str, compute_type: str) -> SpeechEngine:
    return builder(model_size, device, compute_type)

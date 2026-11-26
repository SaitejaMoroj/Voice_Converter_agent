from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import live_session
from app.main import app
from app.services.speech_engine import SpeechResult, SpeechSegment


class FakeSpeechService:
    def __init__(self):
        self.calls = 0

    async def transcribe_pcm16(self, audio, *, sample_rate, language_override):
        self.calls += 1
        if self.calls == 1:
            segments = [SpeechSegment(3.8, 4.4, "repeat this", -0.24, 0.03)]
        elif self.calls == 2:
            segments = [SpeechSegment(0.0, 0.4, "repeat this")]
        else:
            segments = []
        return SpeechResult(
            transcript_text=" ".join(segment.text for segment in segments),
            detected_language=language_override or "en",
            segments=segments,
            processing_time=0.01,
        )


def install_websocket_fakes(monkeypatch):
    speech_service = FakeSpeechService()
    saved = []

    class FakeSessionService:
        def __init__(self):
            self.records = {}

        def record(self, session_id):
            return self.records[session_id]

        async def create_session(self, title, language):
            record = SimpleNamespace(
                id=uuid4(), title=title, transcript_text="", detected_language=language,
                duration_seconds=0.0, status="CREATED", created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc), transcription_metadata={},
            )
            self.records[record.id] = record
            saved.append(record)
            return record

        async def set_status(self, session_id, next_status):
            record = self.record(session_id)
            record.status = next_status.value
            record.updated_at = datetime.now(timezone.utc)
            return record

        async def save_progress(self, session_id, *, transcript_text, detected_language, duration_seconds, metadata, status_value=None):
            record = self.record(session_id)
            record.transcript_text = transcript_text
            record.detected_language = detected_language
            record.duration_seconds = duration_seconds
            record.transcription_metadata = metadata
            if status_value:
                record.status = status_value.value
            record.updated_at = datetime.now(timezone.utc)
            return record

        async def complete(self, session_id, **values):
            from app.services.transcript_sessions import SessionStatus

            return await self.save_progress(session_id, **values, status_value=SessionStatus.COMPLETED)

        async def fail(self, session_id, *, transcript_text, detected_language, duration_seconds, metadata):
            from app.services.transcript_sessions import SessionStatus

            return await self.save_progress(
                session_id, transcript_text=transcript_text, detected_language=detected_language,
                duration_seconds=duration_seconds, metadata=metadata, status_value=SessionStatus.FAILED,
            )

    monkeypatch.setattr(live_session, "TranscriptionService", lambda: speech_service)
    monkeypatch.setattr(live_session, "TranscriptionSessionService", FakeSessionService)
    return speech_service, saved


def receive_until(websocket, message_type, max_messages=20):
    for _ in range(max_messages):
        message = websocket.receive_json()
        if message.get("type") == message_type:
            return message
    raise AssertionError(f"Did not receive WebSocket event {message_type!r}")


def send_pcm_chunk(websocket, sequence, sample_rate=8_000, seconds=5):
    audio = np.zeros(sample_rate * seconds, dtype="<i2").tobytes()
    websocket.send_json({
        "type": "audio_chunk",
        "sequence": sequence,
        "format": "pcm_s16le",
        "sample_rate": sample_rate,
        "channels": 1,
        "byte_length": len(audio),
    })
    websocket.send_bytes(audio)


def test_streaming_protocol_updates_progressively_and_deduplicates_overlap(monkeypatch):
    service, saved = install_websocket_fakes(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({
            "type": "start", "title": "Streaming test", "language": "auto",
            "sample_rate": 8_000, "format": "pcm_s16le", "channels": 1,
        })
        started = receive_until(websocket, "session_started")
        assert started["session_id"]
        assert started["status"] == "CREATED"
        assert receive_until(websocket, "status")["status"] == "loading_model"
        assert receive_until(websocket, "status")["status"] == "recording"
        assert saved[0].status == "RECORDING"

        send_pcm_chunk(websocket, 0)
        partial = receive_until(websocket, "partial_transcript")
        assert partial["text"] == "repeat this"
        first_update = receive_until(websocket, "transcription_update")
        assert len(first_update["segments"]) == 1
        assert first_update["segments"][0]["average_log_probability"] == -0.24
        assert first_update["segments"][0]["no_speech_probability"] == 0.03
        assert first_update["segments"][0]["detected_language"] == "en"
        assert receive_until(websocket, "status")["status"] == "recording"

        websocket.send_json({"type": "pause"})
        assert receive_until(websocket, "status")["status"] == "processing"
        paused_status = receive_until(websocket, "status")
        assert paused_status["status"] == "paused"
        assert paused_status["save_state"] == "saved"
        assert saved[0].status == "PAUSED"
        assert saved[0].transcript_text == "repeat this"
        websocket.send_json({"type": "resume"})
        assert receive_until(websocket, "status")["status"] == "recording"

        send_pcm_chunk(websocket, 1)
        update = receive_until(websocket, "transcription_update")
        assert len([segment for segment in update["segments"] if segment["text"] == "repeat this"]) == 1

        websocket.send_json({"type": "stop"})
        receive_until(websocket, "status")
        final = receive_until(websocket, "final_transcript")
        completed = receive_until(websocket, "session_completed")

    assert final["status"] == "completed"
    assert final["transcript_text"] == "repeat this"
    assert len(final["segments"]) == 1
    assert completed["transcript"]["title"] == "Streaming test"
    assert completed["transcript"]["segments"] == final["segments"]
    assert len(saved) == 1
    assert saved[0].status == "COMPLETED"
    assert saved[0].transcription_metadata["segments"] == final["segments"]
    assert service.calls >= 3


@pytest.mark.parametrize("language", ["te", "kn", "th"])
def test_stream_accepts_telugu_kannada_and_thai_overrides(monkeypatch, language):
    _, saved = install_websocket_fakes(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({
            "type": "start", "title": "Language override", "language": language,
            "sample_rate": 8_000, "format": "pcm_s16le", "channels": 1,
        })
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        websocket.send_json({"type": "stop"})
        receive_until(websocket, "final_transcript")
        receive_until(websocket, "session_completed")

    assert saved[0].detected_language == language


def test_manual_save_checkpoints_progress_without_stopping_session(monkeypatch):
    install_websocket_fakes(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({"type": "start", "title": "Manual save", "sample_rate": 8_000})
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        send_pcm_chunk(websocket, 0)
        receive_until(websocket, "partial_transcript")
        receive_until(websocket, "transcription_update")
        receive_until(websocket, "status")
        websocket.send_json({"type": "save"})
        saved = receive_until(websocket, "status")
        assert saved["save_state"] == "saved_manual"
        assert saved["status"] == "recording"
        websocket.send_json({"type": "stop"})
        receive_until(websocket, "status")
        receive_until(websocket, "final_transcript")
        receive_until(websocket, "session_completed")


def test_disabling_auto_save_skips_interim_checkpoint_but_saves_on_stop(monkeypatch):
    _, saved = install_websocket_fakes(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({
            "type": "start", "title": "Manual checkpoint mode", "sample_rate": 8_000,
            "auto_save": False,
        })
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        send_pcm_chunk(websocket, 0)
        receive_until(websocket, "partial_transcript")
        receive_until(websocket, "transcription_update")
        assert receive_until(websocket, "status")["status"] == "recording"
        assert saved[0].transcript_text == ""

        websocket.send_json({"type": "stop"})
        receive_until(websocket, "status")
        receive_until(websocket, "final_transcript")
        receive_until(websocket, "session_completed")

    assert saved[0].status == "COMPLETED"
    assert saved[0].transcript_text == "repeat this"


def test_disconnect_marks_session_failed_with_partial_transcript(monkeypatch):
    _, saved = install_websocket_fakes(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({"type": "start", "title": "Interrupted", "sample_rate": 8_000})
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        send_pcm_chunk(websocket, 0)
        receive_until(websocket, "partial_transcript")
        websocket.close()

    assert saved[0].status == "FAILED"
    assert saved[0].transcript_text == "repeat this"
    assert saved[0].duration_seconds == 5


def test_failed_final_save_can_be_retried_without_losing_transcript(monkeypatch):
    install_websocket_fakes(monkeypatch)
    manager = live_session.TranscriptionSessionService
    original_complete = manager.complete
    fail_once = {"enabled": True}

    async def fail_first_completion(self, session_id, **values):
        if fail_once["enabled"]:
            fail_once["enabled"] = False
            raise RuntimeError("temporary storage outage")
        return await original_complete(self, session_id, **values)

    monkeypatch.setattr(manager, "complete", fail_first_completion)
    client = TestClient(app)

    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({"type": "start", "title": "Retry save", "sample_rate": 8_000})
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        send_pcm_chunk(websocket, 0)
        receive_until(websocket, "partial_transcript")
        receive_until(websocket, "transcription_update")
        receive_until(websocket, "status")
        websocket.send_json({"type": "stop"})
        retryable_status = None
        while retryable_status is None:
            event = websocket.receive_json()
            if event.get("type") == "status" and event.get("save_state") == "failed":
                retryable_status = event
        error = receive_until(websocket, "error")
        assert error["retryable"] is True
        websocket.send_json({"type": "save"})
        receive_until(websocket, "status")
        receive_until(websocket, "final_transcript")
        complete = receive_until(websocket, "session_completed")

    assert complete["transcript"]["content"] == "repeat this"
    assert complete["status"] == "completed"


@pytest.mark.parametrize("bad_message", ["not-json", "[]", '{"type":"unknown"}'])
def test_stream_rejects_malformed_or_unknown_control_messages(client, bad_message):
    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_text(bad_message)
        response = websocket.receive_json()
        assert response["type"] == "error"


def test_stream_rejects_invalid_audio_descriptor(client, monkeypatch):
    install_websocket_fakes(monkeypatch)
    with client.websocket_connect("/ws/transcription") as websocket:
        websocket.send_json({"type": "start", "sample_rate": 8_000})
        receive_until(websocket, "session_started")
        receive_until(websocket, "status")
        receive_until(websocket, "status")
        websocket.send_json({
            "type": "audio_chunk", "sequence": 0, "format": "pcm_s16le",
            "sample_rate": 8_000, "channels": 1, "byte_length": 10,
        })
        websocket.send_bytes(b"\x00\x00")
        assert websocket.receive_json()["type"] == "error"
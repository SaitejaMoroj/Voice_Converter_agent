import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import asdict
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.services.speech_engine import SpeechResult, SpeechSegment
from app.services.transcribe import TranscriptionService
from app.services.transcript_sessions import SessionStatus, TranscriptionSessionService

logger = logging.getLogger(__name__)
LANGUAGE_CODE = re.compile(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*")


async def _send_error(websocket: WebSocket, message: str, close_code: int) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
        await websocket.close(code=close_code)
    except RuntimeError:
        return


def _text_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"\w+", normalized, flags=re.UNICODE)


def _same_overlapping_phrase(first: str, second: str) -> bool:
    first_tokens = _tokens(first)
    second_tokens = _tokens(second)
    if not first_tokens or not second_tokens:
        return False
    if first_tokens == second_tokens:
        return True
    shorter, longer = sorted((first_tokens, second_tokens), key=len)
    return any(longer[index:index + len(shorter)] == shorter for index in range(len(longer) - len(shorter) + 1))


class StreamingTranscriptionSession:
    def __init__(
        self,
        websocket: WebSocket,
        settings: Settings,
        service: TranscriptionService,
        persistence: TranscriptionSessionService,
        *,
        transcription_id: UUID,
        title: str,
        language: str | None,
        sample_rate: int,
        auto_save: bool = True,
    ) -> None:
        self.websocket = websocket
        self.settings = settings
        self.service = service
        self.persistence = persistence
        self.transcription_id = transcription_id
        self.title = title
        self.language = language
        self.sample_rate = sample_rate
        self.auto_save_enabled = auto_save
        self.session_id = str(uuid4())
        self.status = SessionStatus.RECORDING.value.lower()
        self.persisted_status = SessionStatus.RECORDING
        self.buffer = bytearray()
        self.audio_duration = 0.0
        self.next_window_start = 0.0
        self.processing_time = 0.0
        self.detected_language = language or "auto"
        self.finalized_segments: list[SpeechSegment] = []
        self.pending_segments: list[SpeechSegment] = []
        self.window_samples = settings.audio_window_seconds * sample_rate
        self.overlap_samples = round(settings.audio_overlap_seconds * sample_rate)
        self.window_bytes = self.window_samples * 2
        self.overlap_bytes = self.overlap_samples * 2
        self.stride_bytes = (self.window_samples - self.overlap_samples) * 2
        self.max_session_bytes = settings.websocket_max_session_seconds * sample_rate * 2
        self.received_bytes = 0
        self.next_sequence = 0
        self.processed_windows_since_save = 0
        self.saved_at: str | None = None
        self.completion_pending = False

    async def send_status(self, status: str, *, save_state: str | None = None) -> None:
        self.status = status.lower()
        message = {"type": "status", "status": self.status, "session_id": self.session_id}
        if save_state:
            message["save_state"] = save_state
        if self.saved_at:
            message["saved_at"] = self.saved_at
        await self.websocket.send_json(message)

    def transcript_text(self) -> str:
        segments = sorted(
            self.finalized_segments + self.pending_segments,
            key=lambda segment: (segment.start, segment.end),
        )
        return " ".join(segment.text for segment in segments).strip()

    def session_metadata(self) -> dict:
        segments = sorted(
            self.finalized_segments + self.pending_segments,
            key=lambda segment: (segment.start, segment.end),
        )
        return {
            "segments": [asdict(segment) for segment in segments],
            "processing_time": self.processing_time,
        }

    async def persist_progress(self, *, status_value: SessionStatus | None = None, manual: bool = False) -> bool:
        try:
            record = await self.persistence.save_progress(
                self.transcription_id,
                transcript_text=self.transcript_text(),
                detected_language=self.detected_language,
                duration_seconds=self.audio_duration,
                metadata=self.session_metadata(),
                status_value=status_value or self.persisted_status,
            )
            self.persisted_status = SessionStatus(record.status)
            self.saved_at = record.updated_at.isoformat()
            self.processed_windows_since_save = 0
            await self.send_status(self.status, save_state="saved_manual" if manual else "saved")
            return True
        except Exception:
            logger.exception("Unable to autosave transcription session", extra={"session_id": self.session_id})
            await self.send_status(self.status, save_state="failed")
            await self.websocket.send_json({
                "type": "error",
                "message": "Could not save your latest transcript progress. Retry save when the service is available.",
                "retryable": True,
            })
            return False

    async def set_persisted_status(self, status_value: SessionStatus) -> None:
        record = await self.persistence.set_status(self.transcription_id, status_value)
        self.persisted_status = SessionStatus(record.status)

    async def mark_failed(self) -> None:
        try:
            await self.persistence.fail(
                self.transcription_id,
                transcript_text=self.transcript_text(),
                detected_language=self.detected_language,
                duration_seconds=self.audio_duration,
                metadata=self.session_metadata(),
            )
            self.persisted_status = SessionStatus.FAILED
        except Exception:
            logger.exception("Unable to mark interrupted transcription session as failed", extra={"session_id": self.session_id})

    def _append_unique(self, target: list[SpeechSegment], candidate: SpeechSegment) -> None:
        candidate_key = _text_key(candidate.text)
        overlap_tolerance = max(2.0, (self.overlap_samples / self.sample_rate) * 2)
        for index, existing in enumerate(target):
            if candidate_key == _text_key(existing.text) and abs(existing.start - candidate.start) <= overlap_tolerance:
                if len(_tokens(candidate.text)) > len(_tokens(existing.text)):
                    target[index] = candidate
                return
            intersection = min(existing.end, candidate.end) - max(existing.start, candidate.start)
            if intersection > 0.15 and _same_overlapping_phrase(existing.text, candidate.text):
                if len(_tokens(candidate.text)) > len(_tokens(existing.text)):
                    target[index] = candidate
                return
            if _text_key(candidate.text) == _text_key(existing.text) and abs(existing.start - candidate.start) < 0.08:
                return
        target.append(candidate)

    async def _send_update(self) -> None:
        finalized = sorted(self.finalized_segments, key=lambda segment: (segment.start, segment.end))
        pending = sorted(self.pending_segments, key=lambda segment: (segment.start, segment.end))
        all_segments = finalized + pending
        finalized_text = " ".join(segment.text for segment in finalized).strip()
        partial_text = " ".join(segment.text for segment in pending).strip()
        if partial_text:
            await self.websocket.send_json({
                "type": "partial_transcript",
                "text": partial_text,
                "detected_language": self.detected_language,
                "segments": [asdict(segment) for segment in pending],
            })
        await self.websocket.send_json({
            "type": "transcription_update",
            "transcript_text": " ".join(segment.text for segment in all_segments).strip(),
            "finalized_text": finalized_text,
            "partial_text": partial_text,
            "detected_language": self.detected_language,
            "segments": [asdict(segment) for segment in all_segments],
            "processing_time": self.processing_time,
            "status": self.status,
        })

    async def _process_window(self, audio: bytes, window_start: float, *, final: bool = False) -> None:
        if len(audio) < 2:
            return
        await self.send_status(SessionStatus.PROCESSING.value)
        result: SpeechResult = await self.service.transcribe_pcm16(
            audio,
            sample_rate=self.sample_rate,
            language_override=self.language,
        )
        self.processing_time += result.processing_time
        if result.detected_language:
            self.detected_language = result.detected_language

        new_segments = result.segments
        if not new_segments and result.transcript_text.strip():
            new_segments = [SpeechSegment(window_start, window_start + len(audio) / (self.sample_rate * 2), result.transcript_text.strip())]
        absolute_segments = [
            SpeechSegment(
                start=window_start + segment.start,
                end=window_start + segment.end,
                text=segment.text.strip(),
                average_log_probability=segment.average_log_probability,
                no_speech_probability=segment.no_speech_probability,
                detected_language=segment.detected_language or result.detected_language,
            )
            for segment in new_segments
            if segment.text.strip() and segment.start >= 0 and segment.end >= segment.start
        ]

        if final:
            for segment in self.pending_segments:
                self._append_unique(self.finalized_segments, segment)
            self.pending_segments.clear()
            for segment in absolute_segments:
                self._append_unique(self.finalized_segments, segment)
        else:
            for segment in self.pending_segments:
                if segment.start < window_start:
                    self._append_unique(self.finalized_segments, segment)
            self.pending_segments.clear()
            for segment in absolute_segments:
                if any(
                    min(existing.end, segment.end) - max(existing.start, segment.start) > 0.15
                    and _same_overlapping_phrase(existing.text, segment.text)
                    for existing in self.finalized_segments
                ):
                    self._append_unique(self.finalized_segments, segment)
                    continue
                self._append_unique(self.pending_segments, segment)

        await self._send_update()
        if not final:
            self.processed_windows_since_save += 1
            await self.send_status(SessionStatus.RECORDING.value)
            if self.auto_save_enabled and self.processed_windows_since_save >= self.settings.websocket_autosave_windows:
                await self.persist_progress(status_value=SessionStatus.RECORDING)

    async def receive_audio(self, audio: bytes) -> None:
        if self.status == "paused":
            return
        if self.status != "recording":
            await _send_error(self.websocket, "Audio is not accepted in the current session state.", 1008)
            return
        if not audio:
            await _send_error(self.websocket, "Audio chunk is empty.", 1003)
            return
        if len(audio) > self.settings.websocket_max_chunk_bytes:
            await _send_error(self.websocket, "Audio chunk exceeds the maximum allowed size.", 1009)
            return
        if len(audio) % 2:
            await _send_error(self.websocket, "Audio chunks must contain complete PCM16 samples.", 1003)
            return
        if self.received_bytes + len(audio) > self.max_session_bytes:
            await _send_error(self.websocket, "Session audio duration limit exceeded.", 1008)
            return

        self.received_bytes += len(audio)
        self.audio_duration += len(audio) / (self.sample_rate * 2)
        self.buffer.extend(audio)
        while len(self.buffer) >= self.window_bytes:
            window = bytes(self.buffer[:self.window_bytes])
            del self.buffer[:self.stride_bytes]
            await self._process_window(window, self.next_window_start)
            self.next_window_start += self.stride_bytes / (self.sample_rate * 2)

    async def receive_audio_chunk(self, metadata: dict, audio: bytes) -> None:
        sequence = metadata.get("sequence")
        byte_length = metadata.get("byte_length")
        if type(sequence) is not int or sequence != self.next_sequence:
            await _send_error(self.websocket, "Audio chunk sequence is invalid.", 1008)
            return
        if type(byte_length) is not int or byte_length != len(audio):
            await _send_error(self.websocket, "Audio chunk length does not match its descriptor.", 1003)
            return
        if metadata.get("format") != "pcm_s16le" or type(metadata.get("channels")) is not int or metadata["channels"] != 1:
            await _send_error(self.websocket, "Audio chunk format must be mono PCM16 little-endian.", 1003)
            return
        if type(metadata.get("sample_rate")) is not int or metadata["sample_rate"] != self.sample_rate:
            await _send_error(self.websocket, "Audio chunk sample rate changed during the session.", 1003)
            return
        await self.receive_audio(audio)
        if self.websocket.client_state.name != "DISCONNECTED":
            self.next_sequence += 1

    async def _flush_tail(self) -> None:
        if len(self.buffer) >= 2:
            audio = bytes(self.buffer)
            await self._process_window(audio, self.next_window_start, final=True)
        else:
            for segment in self.pending_segments:
                self._append_unique(self.finalized_segments, segment)
            self.pending_segments.clear()
            await self._send_update()
        self.buffer.clear()

    async def pause(self) -> None:
        if self.status != SessionStatus.RECORDING.value.lower():
            await _send_error(self.websocket, "Session is not recording.", 1008)
            return
        await self._flush_tail()
        self.status = SessionStatus.PAUSED.value.lower()
        await self.persist_progress(status_value=SessionStatus.PAUSED)
        self.next_window_start = self.audio_duration

    async def resume(self) -> None:
        if self.status != SessionStatus.PAUSED.value.lower():
            await _send_error(self.websocket, "Session is not paused.", 1008)
            return
        await self.set_persisted_status(SessionStatus.RECORDING)
        await self.send_status(SessionStatus.RECORDING.value)

    async def save_now(self) -> None:
        if self.completion_pending:
            await self.stop()
            return
        await self.persist_progress(manual=True)

    async def stop(self) -> bool:
        if self.status not in {
            SessionStatus.RECORDING.value.lower(),
            SessionStatus.PAUSED.value.lower(),
            SessionStatus.PROCESSING.value.lower(),
        }:
            await _send_error(self.websocket, "Session cannot be stopped in the current state.", 1008)
            return False
        self.status = SessionStatus.PROCESSING.value
        if self.persisted_status in {SessionStatus.RECORDING, SessionStatus.PAUSED}:
            await self.set_persisted_status(SessionStatus.PROCESSING)
        await self.send_status(SessionStatus.PROCESSING.value)
        if self.buffer:
            await self._flush_tail()
        else:
            for segment in self.pending_segments:
                self._append_unique(self.finalized_segments, segment)
            self.pending_segments.clear()
        segments = sorted(self.finalized_segments, key=lambda segment: (segment.start, segment.end))
        transcript_text = " ".join(segment.text for segment in segments).strip()
        structured = {
            "transcript_text": transcript_text,
            "detected_language": self.detected_language,
            "segments": [asdict(segment) for segment in segments],
            "processing_time": self.processing_time,
            "status": SessionStatus.COMPLETED.value.lower(),
        }
        await self.send_status("saving")
        self.completion_pending = True
        try:
            record = await self.persistence.complete(
                self.transcription_id,
                transcript_text=transcript_text,
                detected_language=self.detected_language,
                duration_seconds=self.audio_duration,
                metadata=self.session_metadata(),
            )
        except Exception:
            logger.exception("Unable to complete transcription session", extra={"session_id": self.session_id})
            self.status = SessionStatus.PROCESSING.value
            await self.send_status(self.status, save_state="failed")
            await self.websocket.send_json({
                "type": "error",
                "message": "Your transcript is ready but could not be saved. Retry save to finish this session.",
                "retryable": True,
            })
            return False
        self.persisted_status = SessionStatus.COMPLETED
        self.completion_pending = False
        await self.websocket.send_json({"type": "final_transcript", **structured})
        await self.websocket.send_json({
            "type": "session_completed",
            "session_id": self.session_id,
            "status": "completed",
            "transcript": {
                "id": str(record.id),
                "title": record.title,
                "content": record.transcript_text,
                "language": record.detected_language or "auto",
                "duration_seconds": round(self.audio_duration),
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
                "status": record.status,
                "segments": [asdict(segment) for segment in segments],
                "processing_time": self.processing_time,
            },
        })
        await self.websocket.close(code=1000)
        return True


async def run_transcription_session(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("Transcription WebSocket connected", extra={"path": websocket.url.path})
    settings = get_settings()
    persistence = TranscriptionSessionService()
    transcription_id: UUID | None = None
    stream_session: StreamingTranscriptionSession | None = None
    try:
        start = await asyncio.wait_for(
            websocket.receive_json(), timeout=settings.websocket_start_timeout_seconds
        )
        if not isinstance(start, dict) or start.get("type") != "start":
            await _send_error(websocket, "The first message must be a start command.", 1008)
            return

        language = start.get("language", "auto")
        if language not in (None, "auto") and (
            not isinstance(language, str) or LANGUAGE_CODE.fullmatch(language) is None
        ):
            await _send_error(websocket, "Language must be auto or a valid language code such as en or hi.", 1008)
            return
        title = start.get("title", "Untitled session")
        auto_save = start.get("auto_save", True)
        sample_rate = start.get("sample_rate", settings.audio_sample_rate)
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            await _send_error(websocket, "Title must contain 1 to 200 characters.", 1008)
            return
        if type(auto_save) is not bool:
            await _send_error(websocket, "Auto-save must be a boolean value.", 1008)
            return
        if type(sample_rate) is not int or not 8_000 <= sample_rate <= 48_000:
            await _send_error(websocket, "Sample rate must be an integer between 8 kHz and 48 kHz.", 1008)
            return
        channels = start.get("channels", 1)
        if start.get("format", "pcm_s16le") != "pcm_s16le" or type(channels) is not int or channels != 1:
            await _send_error(websocket, "Only mono PCM16 little-endian audio is supported.", 1008)
            return
        if settings.audio_overlap_seconds < 0 or settings.audio_overlap_seconds >= settings.audio_window_seconds:
            await _send_error(websocket, "Audio overlap configuration is invalid.", 1011)
            return

        normalized_language = None if language in (None, "auto") else language
        record = await persistence.create_session(title.strip(), normalized_language)
        transcription_id = record.id
        session_id = str(record.id)
        await websocket.send_json({
            "type": "session_started",
            "session_id": session_id,
            "transcription_id": session_id,
            "status": SessionStatus.CREATED.value,
            "saved_at": record.updated_at.isoformat(),
        })
        await websocket.send_json({"type": "status", "session_id": session_id, "status": "loading_model"})
        logger.info("Loading speech recognition model", extra={"session_id": session_id})
        service = await asyncio.to_thread(TranscriptionService)
        logger.info("Speech recognition model ready", extra={"session_id": session_id})
        await persistence.set_status(record.id, SessionStatus.RECORDING)
        stream_session = StreamingTranscriptionSession(
            websocket,
            settings,
            service,
            persistence,
            transcription_id=record.id,
            title=title.strip(),
            language=normalized_language,
            sample_rate=sample_rate,
            auto_save=auto_save,
        )
        stream_session.session_id = session_id
        stream_session.saved_at = record.updated_at.isoformat()
        await stream_session.send_status(SessionStatus.RECORDING.value)
        session_started_at = asyncio.get_running_loop().time()
        pending_chunk: dict | None = None

        while True:
            elapsed = asyncio.get_running_loop().time() - session_started_at
            remaining_session_time = settings.websocket_max_session_seconds - elapsed
            if remaining_session_time <= 0:
                await stream_session.mark_failed()
                await _send_error(websocket, "Maximum session duration exceeded.", 1008)
                return
            message = await asyncio.wait_for(
                websocket.receive(),
                timeout=min(settings.websocket_idle_timeout_seconds, remaining_session_time),
            )
            if message.get("type") == "websocket.disconnect":
                await stream_session.mark_failed()
                return
            if message.get("bytes") is not None:
                if pending_chunk is None:
                    await _send_error(websocket, "Binary audio frame requires an audio_chunk descriptor.", 1003)
                    return
                metadata = pending_chunk
                pending_chunk = None
                await stream_session.receive_audio_chunk(metadata, message["bytes"])
                if websocket.client_state.name == "DISCONNECTED":
                    await stream_session.mark_failed()
                    return
                continue
            if message.get("text") is None:
                await _send_error(websocket, "Unsupported WebSocket message frame.", 1003)
                return

            try:
                command = json.loads(message["text"])
            except json.JSONDecodeError:
                await _send_error(websocket, "Malformed JSON control message.", 1008)
                return
            if not isinstance(command, dict):
                await _send_error(websocket, "Control message must be a JSON object.", 1008)
                return
            command_type = command.get("type")
            if pending_chunk is not None:
                await _send_error(websocket, "Audio chunk descriptor must be followed by one binary frame.", 1008)
                return
            if command_type == "audio_chunk":
                sequence = command.get("sequence")
                byte_length = command.get("byte_length")
                if type(sequence) is not int or type(byte_length) is not int:
                    await stream_session.mark_failed()
                    await _send_error(websocket, "Audio chunk descriptor requires integer sequence and byte_length.", 1008)
                    return
                if not 0 < byte_length <= settings.websocket_max_chunk_bytes or byte_length % 2:
                    await stream_session.mark_failed()
                    await _send_error(websocket, "Audio chunk size must be an even number of bytes within the configured limit.", 1009)
                    return
                pending_chunk = command
            elif command_type == "pause":
                await stream_session.pause()
            elif command_type == "resume":
                await stream_session.resume()
            elif command_type == "stop":
                if await stream_session.stop():
                    return
            elif command_type == "save":
                await stream_session.save_now()
            elif command_type == "ping":
                await websocket.send_json({"type": "status", "status": stream_session.status, "heartbeat": "pong"})
            else:
                await stream_session.mark_failed()
                await _send_error(websocket, "Unknown control message.", 1008)
                return
    except asyncio.TimeoutError:
        if stream_session:
            await stream_session.mark_failed()
        elif transcription_id:
            await persistence.fail(transcription_id, transcript_text="", detected_language=None, duration_seconds=0, metadata={})
        await _send_error(websocket, "WebSocket session timed out due to inactivity.", 1001)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if stream_session:
            await stream_session.mark_failed()
        await _send_error(websocket, "Malformed JSON start message.", 1008)
    except WebSocketDisconnect:
        logger.info("Transcription WebSocket disconnected", extra={"session_id": transcription_id and str(transcription_id)})
        if stream_session:
            await stream_session.mark_failed()
        elif transcription_id:
            try:
                await persistence.fail(transcription_id, transcript_text="", detected_language=None, duration_seconds=0, metadata={})
            except Exception:
                logger.exception("Unable to persist disconnected session", extra={"session_id": str(transcription_id)})
        return
    except Exception:
        logger.exception("WebSocket transcription session failed")
        if stream_session:
            await stream_session.mark_failed()
        elif transcription_id:
            try:
                await persistence.fail(transcription_id, transcript_text="", detected_language=None, duration_seconds=0, metadata={})
            except Exception:
                logger.exception("Unable to persist failed session", extra={"session_id": str(transcription_id)})
        await _send_error(websocket, "Transcription failed. The session was not completed.", 1011)
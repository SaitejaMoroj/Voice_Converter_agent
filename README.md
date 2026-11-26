# VoxFlow

VoxFlow is a multilingual speech-to-text workspace built with React/TypeScript, FastAPI, PostgreSQL, and a replaceable recognition engine. The initial engine is faster-whisper. Mono 16 kHz signed 16-bit PCM is streamed over WebSocket; partial results are emitted per audio window and the finished transcript is persisted.

## Structure

```text
frontend/src/{components,pages,services,types}
backend/app/{api,core,models,repositories,schemas,services,migrations}
```

## Docker

Copy `.env.example` to `.env`, change `POSTGRES_PASSWORD`, and run `docker compose up --build`. The API applies Alembic migrations during startup. Open http://localhost:5173 (UI), http://localhost:8000/docs (API), or `/api/v1/health/live` and `/api/v1/health/ready` (health checks). The first transcription loads/downloads the configured model (`MODEL_SIZE`, default `base`).

## Local development

From `frontend/`, run `npm install` and `npm run dev`. This starts both the FastAPI backend on port `8000` and Vite frontend on port `5174`. Set `DATABASE_URL` to the PostgreSQL connection URL before starting the backend.

## Render deployment

Set these Render backend environment variables:

```text
DATABASE_URL=postgresql+asyncpg://username:password@host:5432/database
CORS_ORIGINS=https://your-frontend.onrender.com
```

For separate frontend and backend Render services, set these frontend build/environment variables:

```text
VITE_API_URL=https://voice-converter-agent-s1ru.onrender.com/api/v1
VITE_WS_URL=wss://voice-converter-agent-s1ru.onrender.com/ws/transcription
```

Render may provide `postgres://` or `postgresql://`; VoxFlow normalizes these values to `postgresql+asyncpg://` automatically. Do not set `psycopg2` in the async application configuration.

Deploy `backend/` as the web service root. The Docker startup command runs Alembic migrations and listens on Render's `PORT` value.

## Backend tests

From `backend/`, install `requirements-test.txt` and run `python -m pytest tests -q`. The endpoint suite uses an isolated SQLite database for fast request/response coverage; run the Alembic migrations against PostgreSQL as part of deployment or integration testing.

## Speech protocol

Connect to `/ws/transcription`, send `{"type":"start","language":"hi","title":"Meeting notes","sample_rate":16000,"format":"pcm_s16le","channels":1}`, then send an `audio_chunk` JSON descriptor followed by one binary frame for each mono PCM16 little-endian chunk. Control messages `pause`, `resume`, and `stop` are supported. The server emits `session_started`, `status`, `partial_transcript`, `transcription_update`, `final_transcript`, and `session_completed` events. `/api/v1/transcription/stream` remains as a compatibility alias. `SpeechEngine` is the replaceable contract; transcript persistence does not depend on faster-whisper.

Speech runtime settings are `MODEL_SIZE`, `DEVICE`, `COMPUTE_TYPE`, `DEFAULT_LANGUAGE`, and `ENABLE_LANGUAGE_DETECTION`. Streaming limits are `AUDIO_WINDOW_SECONDS`, `AUDIO_OVERLAP_SECONDS`, `WEBSOCKET_MAX_CHUNK_BYTES`, `WEBSOCKET_MAX_SESSION_SECONDS`, `WEBSOCKET_IDLE_TIMEOUT_SECONDS`, and `WEBSOCKET_START_TIMEOUT_SECONDS`. Set `DEVICE=cuda` and a compatible compute type such as `float16` for a CUDA-enabled host; CPU defaults to `int8`. English, Hindi, Telugu, and Kannada overrides are supported. `auto` can detect other languages supported by the multilingual model, with detection per configured audio window (five seconds by default), not per word. Rapid Hindi-English switching, accents, noise, and short clips can reduce accuracy; recognition quality varies by language and model size. Faster-whisper's average token log probability and no-speech probability are raw model diagnostics, not calibrated transcription confidence, and other engine providers may omit them.

faster-whisper is not a native streaming recognizer. VoxFlow transcribes bounded overlapping windows and reconciles segments by text and timestamps; updates therefore arrive after each window, and CPU inference/model load can add latency. Overlap reduces boundary truncation and duplicate phrases, but recognition and code-switch quality remain model-dependent.

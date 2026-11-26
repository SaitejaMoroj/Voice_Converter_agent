from fastapi import Depends

from app.api.dependencies import get_transcription_service
from app.core.database import get_session
from app.repositories.transcript_store import TranscriptionRepository
from app.services.audio_storage_service import AudioStorageService
from app.services.transcript_library import TranscriptionCrudService


def create_transcription(client, title, transcript_text, **extra):
    response = client.post("/api/transcriptions", json={
        "title": title,
        "transcript_text": transcript_text,
        **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_health_endpoints(client):
    assert client.get("/api/health").json() == {"status": "alive"}
    assert client.get("/api/health/database").json() == {
        "status": "healthy",
        "database": "connected",
    }


def test_create_get_update_patch_and_delete(client):
    created = create_transcription(
        client,
        "Planning call",
        "Discussed the next release",
        detected_language="en",
        duration_seconds=42.5,
        metadata={"source": "microphone"},
    )
    assert created["status"] == "completed"
    assert created["metadata"] == {"source": "microphone"}

    transcription_id = created["id"]
    fetched = client.get(f"/api/transcriptions/{transcription_id}")
    assert fetched.status_code == 200
    assert fetched.json()["transcript_text"] == "Discussed the next release"

    replaced = client.put(f"/api/transcriptions/{transcription_id}", json={
        "title": "Release planning",
        "transcript_text": "The release is scheduled for Friday.",
    })
    assert replaced.status_code == 200
    assert replaced.json()["title"] == "Release planning"
    assert replaced.json()["detected_language"] == "en"

    patched = client.patch(f"/api/transcriptions/{transcription_id}", json={"status": "reviewed"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "reviewed"
    assert patched.json()["transcript_text"] == "The release is scheduled for Friday."

    deleted = client.delete(f"/api/transcriptions/{transcription_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/transcriptions/{transcription_id}").status_code == 404


def test_search_pagination_and_sorting(client):
    create_transcription(client, "Beta review", "A customer feedback session")
    create_transcription(client, "Alpha planning", "Review the delivery milestones")
    create_transcription(client, "Gamma notes", "Discuss a roadmap")

    page = client.get("/api/transcriptions?page=1&page_size=1&sort_by=title&sort_order=asc")
    assert page.status_code == 200
    assert page.json()["records"][0]["title"] == "Alpha planning"
    assert page.json()["total_count"] == 3
    assert page.json()["total_pages"] == 3

    filtered = client.get("/api/transcriptions?search=feedback")
    assert filtered.json()["total_count"] == 1
    assert filtered.json()["records"][0]["title"] == "Beta review"

    searched = client.get("/api/transcriptions/search?q=roadmap")
    assert searched.status_code == 200
    assert searched.json()["records"][0]["title"] == "Gamma notes"


def test_history_filters_duration_sorting_statistics_and_bulk_delete(client):
    short = create_transcription(
        client, "Short English", "A brief update", detected_language="en", duration_seconds=10
    )
    long = create_transcription(
        client, "Long Telugu", "ఒక సమావేశం", detected_language="te", duration_seconds=65
    )

    languages = client.get("/api/transcriptions/languages")
    assert languages.status_code == 200
    assert languages.json() == ["en", "te"]

    filtered = client.get("/api/transcriptions", params={"language": "TE"})
    assert filtered.status_code == 200
    assert [record["id"] for record in filtered.json()["records"]] == [long["id"]]

    date_filtered = client.get("/api/transcriptions", params={
        "created_after": "2000-01-01T00:00:00Z",
        "created_before": "2100-01-01T00:00:00Z",
        "sort_by": "duration_seconds",
        "sort_order": "asc",
    })
    assert [record["id"] for record in date_filtered.json()["records"]] == [short["id"], long["id"]]

    stats = client.get("/api/transcriptions/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "total_sessions": 2,
        "total_duration_seconds": 75.0,
        "unique_languages": 2,
        "sessions_this_month": 2,
    }

    deleted = client.request("DELETE", "/api/transcriptions/bulk", json={"ids": [short["id"], long["id"]]})
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_count": 2}
    assert client.get(f"/api/transcriptions/{short['id']}").status_code == 404


def test_original_audio_upload_streaming_download_and_delete(client, tmp_path):
    audio_storage = AudioStorageService(tmp_path / "audio")

    async def override_transcription_service(session=Depends(get_session)):
        return TranscriptionCrudService(TranscriptionRepository(session), audio_storage)

    from app.main import app

    app.dependency_overrides[get_transcription_service] = override_transcription_service
    try:
        created = create_transcription(client, "Audio archive", "Original words", duration_seconds=3.0)
        audio_content = b"original-webm-audio-bytes"
        uploaded = client.put(
            f"/api/transcriptions/{created['id']}/audio",
            content=audio_content,
            headers={"Content-Type": "audio/webm"},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["audio_available"] is True
        assert uploaded.json()["audio_url"].endswith(f"/api/transcriptions/{created['id']}/audio")

        streamed = client.get(uploaded.json()["audio_url"], headers={"Range": "bytes=0-7"})
        assert streamed.status_code == 206
        assert streamed.content == audio_content[:8]
        assert streamed.headers["content-type"].startswith("audio/webm")

        downloaded = client.get(f"/api/transcriptions/{created['id']}/audio?download=true")
        assert downloaded.status_code == 200
        assert "attachment" in downloaded.headers["content-disposition"]
        assert downloaded.content == audio_content

        storage_key = uploaded.json()["audio_url"].split("/")[-1]
        stored_files = list((tmp_path / "audio").iterdir())
        assert len(stored_files) == 1
        assert stored_files[0].name.startswith(created["id"].replace("-", ""))

        deleted = client.delete(f"/api/transcriptions/{created['id']}")
        assert deleted.status_code == 204
        assert list((tmp_path / "audio").iterdir()) == []
        assert client.get(f"/api/transcriptions/{created['id']}/audio").status_code == 404
    finally:
        app.dependency_overrides.pop(get_transcription_service, None)


def test_validation_and_legacy_routes(client):
    assert client.post("/api/transcriptions", json={"title": "   "}).status_code == 422
    assert client.get("/api/transcriptions?page=0").status_code == 422
    assert client.get("/api/transcriptions?sort_by=unknown").status_code == 422
    assert client.patch("/api/transcriptions/00000000-0000-0000-0000-000000000000", json={}).status_code == 422

    legacy = client.post("/api/v1/transcripts", json={
        "title": "Legacy session",
        "content": "Still available to the workspace",
        "language": "en",
        "duration_seconds": 12,
    })
    assert legacy.status_code == 201
    assert legacy.json()["content"] == "Still available to the workspace"
    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}

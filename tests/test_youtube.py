"""Unit tests for official YouTube API integration and video uploads."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from src.youtube import (
    get_authenticated_service,
    upload_video,
    update_video_privacy,
    delete_video,
)


def test_missing_youtube_credentials(monkeypatch):
    monkeypatch.delenv("YT_CLIENT_ID", raising=False)
    monkeypatch.delenv("YT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YT_REFRESH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="Missing YouTube credentials"):
        get_authenticated_service()


@patch("src.youtube.get_authenticated_service")
def test_upload_video_mocked(mock_get_service, tmp_path: Path):
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy video content")

    mock_service = MagicMock()
    mock_insert_req = MagicMock()
    # Simulate resumable upload finishing in 1 chunk
    mock_insert_req.next_chunk.return_value = (None, {"id": "mock_yt_vid_999"})
    mock_service.videos().insert.return_value = mock_insert_req
    mock_get_service.return_value = mock_service

    result = upload_video(
        video_path=dummy_video,
        title="Timeless Stoic Wisdom",
        description="Daily stoicism lesson",
        tags=["stoicism", "wisdom"],
        privacy_status="private",
    )

    assert result["video_id"] == "mock_yt_vid_999"
    assert result["video_url"] == "https://youtu.be/mock_yt_vid_999"
    assert result["privacy_status"] == "private"

    # Verify disclosure was included in snippet description
    call_kwargs = mock_service.videos().insert.call_args[1]
    inserted_desc = call_kwargs["body"]["snippet"]["description"]
    assert "Created with AI assistance" in inserted_desc


@patch("src.youtube.get_authenticated_service")
def test_update_video_privacy_mocked(mock_get_service):
    mock_service = MagicMock()
    mock_update_req = MagicMock()
    mock_update_req.execute.return_value = {"id": "vid_123", "status": {"privacyStatus": "public"}}
    mock_service.videos().update.return_value = mock_update_req
    mock_get_service.return_value = mock_service

    res = update_video_privacy("vid_123", "public")
    assert res["status"]["privacyStatus"] == "public"
    mock_service.videos().update.assert_called_once()


@patch("src.youtube.get_authenticated_service")
def test_delete_video_mocked(mock_get_service):
    mock_service = MagicMock()
    mock_delete_req = MagicMock()
    mock_delete_req.execute.return_value = {}
    mock_service.videos().delete.return_value = mock_delete_req
    mock_get_service.return_value = mock_service

    delete_video("vid_123")
    mock_service.videos().delete.assert_called_once_with(id="vid_123")

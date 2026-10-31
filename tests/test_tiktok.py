"""Unit tests for TikTok publishing module."""

from pathlib import Path
from unittest.mock import patch, MagicMock
from src.tiktok import format_tiktok_caption, is_tiktok_configured, post_to_tiktok


def test_format_tiktok_caption():
    caption = format_tiktok_caption(
        title="When Nikola Tesla Saw Modern AI",
        hook="Imagine Nikola Tesla woke up in 2026...",
        hashtags=["#TimeReborn", "#AI", "#History", "#Shorts"],
    )
    assert "When Nikola Tesla Saw Modern AI" in caption
    assert "Imagine Nikola Tesla woke up in 2026..." in caption
    assert "#TimeReborn" in caption
    assert "#AI" in caption


def test_is_tiktok_configured_without_env(monkeypatch):
    monkeypatch.delenv("TIKTOK_SESSION_ID", raising=False)
    monkeypatch.delenv("TIKTOK_COOKIES_PATH", raising=False)
    assert is_tiktok_configured() is False


def test_is_tiktok_configured_with_session(monkeypatch):
    monkeypatch.setenv("TIKTOK_SESSION_ID", "dummy_session_123")
    assert is_tiktok_configured() is True


def test_post_to_tiktok_pending_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("TIKTOK_SESSION_ID", raising=False)
    monkeypatch.delenv("TIKTOK_COOKIES_PATH", raising=False)
    
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy")
    
    result = post_to_tiktok(
        video_path=dummy_video,
        title="Test Title",
        description="Test Caption",
    )
    assert result["status"] == "pending_credentials"
    assert result["platform"] == "tiktok"


@patch("tiktok_uploader.upload.upload_video")
def test_post_to_tiktok_with_session_success(mock_upload, tmp_path, monkeypatch):
    monkeypatch.setenv("TIKTOK_SESSION_ID", "valid_session_123")
    mock_upload.return_value = [{"status": "success", "video_id": "999"}]
    
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy")
    
    result = post_to_tiktok(
        video_path=dummy_video,
        title="Test Title",
        description="Test Caption",
    )
    assert result["status"] == "published"
    assert result["platform"] == "tiktok"
    mock_upload.assert_called_once()


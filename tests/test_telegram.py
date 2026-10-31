"""Unit tests for Telegram Bot API client with strict mock guards."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.telegram import (
    format_real_post_message,
    get_telegram_config,
    send_alert,
    send_message,
    send_post_notification,
    send_video,
)


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(ValueError, match="Missing Telegram credentials"):
        get_telegram_config()


def test_format_real_post_message_valid():
    record = {
        "title": "When Caesar Meets AI",
        "youtube_url": "https://youtu.be/test1234",
        "platform": "YouTube",
        "reference_file": "1.mp4",
        "style_variant": "cinematic_stock_footage",
        "slot_time_utc": "13:00",
    }
    msg = format_real_post_message(record)
    assert "Posted to YouTube" in msg
    assert "Title: When Caesar Meets AI" in msg
    assert "Link: https://youtu.be/test1234" in msg
    assert "Based on: 1.mp4 | Style: cinematic_stock_footage" in msg


def test_format_real_post_message_rejects_placeholder():
    # Must refuse to send messages with placeholder text
    with pytest.raises(ValueError):
        format_real_post_message({"title": "<title>", "youtube_url": "https://youtu.be/123"})

    with pytest.raises(ValueError):
        format_real_post_message({"title": "Test video placeholder", "youtube_url": "https://youtu.be/123"})


@patch("src.telegram.requests.post")
def test_send_message_success(mock_post, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 101}}
    mock_post.return_value = mock_resp

    res = send_message("Test message")
    assert res["ok"] is True
    assert mock_post.called
    assert "https://api.telegram.org/botmock_token/sendMessage" in mock_post.call_args[0][0]


def test_dry_run_never_calls_network(monkeypatch):
    # Ensure dry_run flag never executes an actual network request
    with patch("src.telegram.requests.post") as mock_post:
        res = send_message("Test message", dry_run=True)
        assert res["ok"] is True
        assert res["dry_run"] is True
        mock_post.assert_not_called()


@patch("src.telegram.requests.post")
def test_send_video_success(mock_post, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy video binary data")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 102}}
    mock_post.return_value = mock_resp

    res = send_video(dummy_video, caption="Test Caption")
    assert res["ok"] is True
    assert "https://api.telegram.org/botmock_token/sendVideo" in mock_post.call_args[0][0]


@patch("src.telegram.send_message")
def test_send_alert(mock_send_msg):
    send_alert(error_summary="FFmpeg render error", details="Exit code 1")
    assert mock_send_msg.called
    msg = mock_send_msg.call_args[1]["text"]
    assert "Pipeline error: FFmpeg render error" in msg
    assert "Exit code 1" in msg

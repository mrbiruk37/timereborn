"""Unit tests for Telegram Bot API client and approval messaging."""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest
from src.telegram import (
    get_telegram_config,
    send_message,
    send_video,
    send_approval_request,
    send_alert,
)


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(ValueError, match="Missing Telegram credentials"):
        get_telegram_config()


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


@patch("src.telegram.send_video")
@patch("src.telegram.send_message")
def test_send_approval_request(mock_send_msg, mock_send_vid, tmp_path: Path):
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"data")

    send_approval_request(
        video_id="yt_abc123",
        title="Marcus Aurelius Secret",
        youtube_url="https://youtu.be/yt_abc123",
        video_path=dummy_video,
        caption="Sample TikTok Caption #Shorts",
        slot="slot_1",
    )

    assert mock_send_vid.called
    assert mock_send_msg.called

    # Verify inline keyboard has Approve and Reject callback buttons
    call_kwargs = mock_send_msg.call_args[1]
    keyboard = call_kwargs["reply_markup"]["inline_keyboard"]
    assert keyboard[0][0]["callback_data"] == "approve:yt_abc123"
    assert keyboard[0][1]["callback_data"] == "reject:yt_abc123"


@patch("src.telegram.send_message")
def test_send_alert(mock_send_msg):
    send_alert("FFmpeg error", details="Code 1")
    assert mock_send_msg.called
    msg_text = mock_send_msg.call_args[1]["text"]
    assert "TIMEREBORN FAILURE ALERT" in msg_text
    assert "FFmpeg error" in msg_text

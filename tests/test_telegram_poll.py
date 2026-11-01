"""Unit tests for telegram_poll.py commands."""

from unittest.mock import MagicMock, patch
from src.telegram_poll import (
    handle_command,
    update_settings_key,
)


@patch("src.telegram_poll.update_settings_key")
@patch("src.telegram_poll.send_message")
def test_handle_command_pause_and_resume(mock_send_msg, mock_update_settings):
    handle_command("/pause", chat_id="123")
    mock_update_settings.assert_called_with("status", "paused")
    assert mock_send_msg.called

    handle_command("/resume", chat_id="123")
    mock_update_settings.assert_called_with("status", "active")


@patch("src.telegram_poll.add_user_idea")
@patch("src.telegram_poll.send_message")
def test_handle_command_idea(mock_send_msg, mock_add_idea):
    mock_add_idea.return_value = {
        "title_seed": "Nikola Tesla in Silicon Valley",
        "topic": "Nikola Tesla reborn",
        "hook_seed": "What if Tesla walked into Silicon Valley?",
    }
    handle_command("/idea Nikola Tesla reborn", chat_id="123")
    mock_add_idea.assert_called_once_with("Nikola Tesla reborn")
    assert mock_send_msg.called


@patch("src.telegram_poll.get_stats")
@patch("src.telegram_poll.send_message")
def test_handle_command_stats_no_data(mock_send_msg, mock_get_stats):
    mock_get_stats.return_value = {}
    handle_command("/stats", chat_id="123")
    assert mock_send_msg.called
    assert "No data yet." in mock_send_msg.call_args[0][0]


@patch("src.telegram_poll.get_stats")
@patch("src.telegram_poll.send_message")
def test_handle_command_stats_with_real_data(mock_send_msg, mock_get_stats):
    mock_get_stats.return_value = {
        "last_7_days": {
            "total_videos": 3,
            "total_views": 1500,
            "total_likes": 120,
            "total_comments": 15,
        }
    }
    handle_command("/stats", chat_id="123")
    assert mock_send_msg.called
    msg = mock_send_msg.call_args[0][0]
    assert "Videos: 3" in msg
    assert "Views: 1500" in msg


@patch("src.telegram_poll.repost_from_url")
@patch("src.telegram_poll.send_message")
@patch("src.telegram_poll.get_updates")
@patch("src.telegram_poll.get_telegram_config")
def test_poll_telegram_events_tiktok_link(mock_cfg, mock_updates, mock_send, mock_repost, tmp_path, monkeypatch):
    from src.telegram_poll import poll_telegram_events
    monkeypatch.setattr("src.telegram_poll.POLL_STATE_FILE", tmp_path / ".offset")
    mock_cfg.return_value = {"chat_id": "123", "bot_token": "abc"}
    mock_updates.return_value = [
        {
            "update_id": 101,
            "message": {
                "chat": {"id": "123"},
                "text": "Hey check out https://www.tiktok.com/@creator/video/1234567890",
            },
        }
    ]
    mock_repost.return_value = {"status": "published", "youtube_id": "yt123"}

    handled = poll_telegram_events()
    assert handled == 1
    assert mock_repost.called
    assert mock_repost.call_args[0][0] == "https://www.tiktok.com/@creator/video/1234567890"

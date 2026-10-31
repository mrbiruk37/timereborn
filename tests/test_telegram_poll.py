"""Unit tests for telegram_poll.py commands and inline callback queries."""

from unittest.mock import MagicMock, patch
from src.telegram_poll import (
    handle_callback_query,
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
        "title_seed": "Dichotomy of Control",
        "topic": "Epictetus on control",
        "hook_seed": "Stop stressing over external things.",
    }
    handle_command("/idea Marcus Aurelius on anger", chat_id="123")
    mock_add_idea.assert_called_once_with("Marcus Aurelius on anger")
    assert mock_send_msg.called


@patch("src.telegram_poll.update_video_privacy")
@patch("src.telegram_poll.answer_callback_query")
@patch("src.telegram_poll.edit_message_text")
@patch("src.telegram_poll.get_posts", return_value=[{"youtube_id": "vid_abc", "status": "pending"}])
@patch("src.telegram_poll.save_posts")
def test_handle_callback_approve(mock_save, mock_get_posts, mock_edit, mock_answer, mock_privacy):
    cq = {
        "id": "cq_100",
        "data": "approve:vid_abc",
        "message": {"message_id": 55, "chat": {"id": 123}},
    }
    handle_callback_query(cq)
    mock_privacy.assert_called_once_with("vid_abc", "public")
    mock_answer.assert_called_once()
    mock_edit.assert_called_once()


@patch("src.telegram_poll.delete_video")
@patch("src.telegram_poll.answer_callback_query")
@patch("src.telegram_poll.edit_message_text")
@patch("src.telegram_poll.get_posts", return_value=[{"youtube_id": "vid_abc", "status": "pending"}])
@patch("src.telegram_poll.save_posts")
def test_handle_callback_reject(mock_save, mock_get_posts, mock_edit, mock_answer, mock_delete):
    cq = {
        "id": "cq_101",
        "data": "reject:vid_abc",
        "message": {"message_id": 56, "chat": {"id": 123}},
    }
    handle_callback_query(cq)
    mock_delete.assert_called_once_with("vid_abc")
    mock_answer.assert_called_once()
    mock_edit.assert_called_once()

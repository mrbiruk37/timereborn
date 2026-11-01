"""Tests for TikTok repost engine."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.repost import (
    extract_tiktok_url,
    generate_repost_metadata,
    is_already_reposted,
    load_reposts,
    record_repost,
    repost_from_url,
)


def test_extract_tiktok_url():
    """Test extracting TikTok URLs from message strings."""
    assert extract_tiktok_url("Check this out https://www.tiktok.com/@user/video/7106594312292453675 please") == "https://www.tiktok.com/@user/video/7106594312292453675"
    assert extract_tiktok_url("Look at https://vm.tiktok.com/ZM8xXYZ/") == "https://vm.tiktok.com/ZM8xXYZ/"
    assert extract_tiktok_url("No link here at all") is None


def test_reposts_tracking(tmp_path, monkeypatch):
    """Test tracking and detecting already reposted videos."""
    test_reposts_file = tmp_path / "reposts.json"
    monkeypatch.setattr("src.repost.REPOSTS_FILE", test_reposts_file)

    assert not is_already_reposted("12345")
    record_repost({
        "video_id": "12345",
        "original_url": "https://www.tiktok.com/@user/video/12345",
        "title": "Test Title",
    })
    assert is_already_reposted("12345")
    assert is_already_reposted("https://www.tiktok.com/@user/video/12345")


@patch("src.repost.Groq")
def test_generate_repost_metadata(mock_groq_class, monkeypatch):
    """Test Groq LLM generating fresh metadata."""
    monkeypatch.setenv("GROQ_API_KEY", "mock_key")
    mock_client = MagicMock()
    mock_groq_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = '{"title": "The Secret Roman Hack", "hook": "Did Romans know this?", "description": "Rome had secrets. #Shorts", "hashtags": ["#Shorts", "#TimeReborn"], "tags": ["History", "Shorts"]}'
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    data = generate_repost_metadata("Old title", "Old desc", "creator")
    assert data["title"] == "The Secret Roman Hack"
    assert data["hook"] == "Did Romans know this?"
    assert "#Shorts" in data["hashtags"]


@patch("src.repost.send_message")
@patch("src.repost.send_video")
@patch("src.repost.upload_video")
@patch("src.repost.sanitize_and_reencode_video")
@patch("src.repost.download_tiktok_video")
def test_repost_from_url_dry_run(
    mock_dl,
    mock_reencode,
    mock_upload,
    mock_send_vid,
    mock_send_msg,
    tmp_path,
    monkeypatch,
):
    """Test dry run execution of repost pipeline."""
    test_reposts_file = tmp_path / "reposts.json"
    monkeypatch.setattr("src.repost.REPOSTS_FILE", test_reposts_file)
    monkeypatch.setenv("GROQ_API_KEY", "mock_key")

    dummy_input = tmp_path / "in.mp4"
    dummy_input.write_text("fake video")

    mock_dl.return_value = {
        "video_path": dummy_input,
        "video_id": "998877",
        "title": "Ancient Trick",
        "description": "Watch this",
        "duration": 25.0,
        "uploader": "history_buff",
        "original_url": "https://www.tiktok.com/@history_buff/video/998877",
    }

    with patch("src.repost.generate_repost_metadata") as mock_meta:
        mock_meta.return_value = {
            "title": "The Forgotten Ancient Trick",
            "hook": "This changed empires.",
            "description": "A forgotten ancient trick revealed. #Shorts",
            "hashtags": ["#Shorts", "#TimeReborn"],
            "tags": ["History", "Shorts"],
        }

        res = repost_from_url(
            tiktok_url="https://www.tiktok.com/@history_buff/video/998877",
            slot="test_slot",
            dry_run=True,
        )

        assert res["youtube_id"] == "dry_run_repost"
        assert res["platform"] == "YouTube Shorts"
        assert is_already_reposted("998877")


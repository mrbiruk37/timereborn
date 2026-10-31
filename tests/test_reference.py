"""Unit tests for reference video analysis module."""

from pathlib import Path
from unittest.mock import patch, MagicMock
from src.reference import (
    compute_file_sha256,
    load_reference_analyses,
    save_reference_analyses,
    analyze_technical,
    analyze_audio,
    scan_and_update_references,
)


def test_compute_file_sha256(tmp_path):
    test_file = tmp_path / "sample.mp4"
    test_file.write_bytes(b"sample video bytes for sha256 testing")
    h = compute_file_sha256(test_file)
    assert isinstance(h, str)
    assert len(h) == 64


def test_load_and_save_reference_analyses(tmp_path, monkeypatch):
    test_json = tmp_path / "reference_analysis.json"
    monkeypatch.setattr("src.reference.ANALYSIS_FILE", test_json)
    monkeypatch.setattr("src.reference.DATA_DIR", tmp_path)

    data = {"sample.mp4": {"sha256": "abcdef", "structure": {"topic": "AI"}}}
    save_reference_analyses(data)
    loaded = load_reference_analyses()
    assert "sample.mp4" in loaded
    assert loaded["sample.mp4"]["structure"]["topic"] == "AI"


@patch("subprocess.run")
def test_analyze_technical_parsing(mock_sub):
    mock_sub.return_value = MagicMock(
        stderr="Duration: 00:00:15.50, start: 0.000000\nStream #0:0: Video: h264, 1080x1920, 30 fps\npts_time:2.5\npts_time:5.0\n"
    )
    res = analyze_technical(Path("dummy.mp4"), "ffmpeg")
    assert res["duration"] == 15.5
    assert res["width"] == 1080
    assert res["height"] == 1920
    assert res["fps"] == 30.0
    assert res["scene_cuts_count"] == 2


@patch("src.reference.get_groq_client")
@patch("subprocess.run")
def test_analyze_audio_parsing(mock_sub, mock_groq, tmp_path):
    audio_file = tmp_path / "ref_audio.mp3"
    audio_file.write_bytes(b"dummy audio")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Hello world this is a test narration"
    mock_resp.words = [{"word": "Hello", "start": 0.0, "end": 0.5}]
    mock_client.audio.transcriptions.create.return_value = mock_resp
    mock_groq.return_value = mock_client

    res = analyze_audio(Path("dummy.mp4"), "ffmpeg", tmp_path)
    assert res["has_voiceover"] is True
    assert res["word_count"] > 0


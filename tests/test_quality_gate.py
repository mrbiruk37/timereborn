"""Unit tests for automatic quality gate."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from src.quality_gate import run_llm_script_review, run_quality_gate


def test_run_llm_script_review_detects_placeholder():
    script = "In 2026, [Insert name] woke up and saw the city."
    hook = "What happens next?"
    passed, issues = run_llm_script_review(script=script, hook=hook)
    assert passed is False


@patch("src.quality_gate.get_default_model", return_value="openai/gpt-oss-120b")
@patch("src.quality_gate.get_groq_client")
def test_run_llm_script_review_passes(mock_client, mock_model):
    mock_res = MagicMock()
    mock_res.choices = [
        MagicMock(message=MagicMock(content='{"passed": true, "issues": []}'))
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_res

    script = "Nikola Tesla stood in awe as he examined modern wireless communication."
    hook = "What if Nikola Tesla saw modern smartphones?"
    passed, issues = run_llm_script_review(script=script, hook=hook)
    assert passed is True
    assert len(issues) == 0


@patch("src.quality_gate.check_black_segments", return_value=False)
@patch("src.quality_gate.probe_video_duration", return_value=25.0)
@patch("src.quality_gate.run_llm_script_review", return_value=(True, []))
def test_run_quality_gate_all_pass(mock_llm, mock_probe, mock_black, tmp_path: Path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"0" * (600 * 1024))

    dummy_audio = tmp_path / "audio.mp3"
    dummy_audio.write_bytes(b"0" * (20 * 1024))

    dummy_sub = tmp_path / "sub.ass"
    dummy_sub.write_text("Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello world\n")

    passed, issues = run_quality_gate(
        video_path=dummy_video,
        script="Hello world, this is a clean script.",
        hook="Hello world",
        subtitles_path=dummy_sub,
        audio_path=dummy_audio,
        target_duration=25.0,
    )
    assert passed is True
    assert len(issues) == 0

"""Unit tests for captions.py subtitle generation and ASS formatting."""

from pathlib import Path
from src.captions import (
    WordTimestamp,
    chunk_words,
    format_ass_timestamp,
    get_ass_header,
    generate_fallback_subtitles,
)


def test_format_ass_timestamp():
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(1.5) == "0:00:01.50"
    assert format_ass_timestamp(65.25) == "0:01:05.25"
    assert format_ass_timestamp(3661.12) == "1:01:01.12"


def test_chunk_words():
    words = [
        WordTimestamp(word="Focus", start=0.0, end=0.4),
        WordTimestamp(word="on", start=0.4, end=0.7),
        WordTimestamp(word="what", start=0.7, end=1.0),
        WordTimestamp(word="you", start=1.0, end=1.3),
        WordTimestamp(word="control", start=1.3, end=1.8),
    ]
    chunks = chunk_words(words, max_words=3, max_duration=1.5)
    assert len(chunks) == 2
    assert len(chunks[0]) == 3
    assert len(chunks[1]) == 2
    assert chunks[0][0].word == "Focus"
    assert chunks[1][-1].word == "control"


def test_fallback_subtitles_file(tmp_path: Path):
    out_file = tmp_path / "test.ass"
    script = "You have power over your mind not outside events"
    generated = generate_fallback_subtitles(script=script, total_duration=4.0, output_path=out_file)

    assert generated.exists()
    content = generated.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[Events]" in content
    assert "Dialogue:" in content
    assert "POWER OVER" in content or "YOU HAVE" in content


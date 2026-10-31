"""Word-level subtitles generation using faster-whisper to .ass format."""

import logging
from pathlib import Path
from typing import List, NamedTuple, Optional

logger = logging.getLogger("timereborn.captions")


class WordTimestamp(NamedTuple):
    word: str
    start: float
    end: float


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp format: H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis -= 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def get_ass_header(width: int = 1080, height: int = 1920) -> str:
    """Generate modern ASS script header with centered high-contrast styling."""
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,2,2,60,60,420,1
Style: Hook,Arial Black,72,&H0000FFFF,&H00000000,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,6,3,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def chunk_words(words: List[WordTimestamp], max_words: int = 3, max_duration: float = 1.6) -> List[List[WordTimestamp]]:
    """Group words into punchy short phrases of 2-3 words for high viewer retention."""
    chunks: List[List[WordTimestamp]] = []
    current_chunk: List[WordTimestamp] = []

    for word in words:
        if not current_chunk:
            current_chunk.append(word)
            continue

        chunk_dur = word.end - current_chunk[0].start
        if len(current_chunk) >= max_words or chunk_dur >= max_duration:
            chunks.append(current_chunk)
            current_chunk = [word]
        else:
            current_chunk.append(word)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_ass_events(chunks: List[List[WordTimestamp]]) -> str:
    """Format word chunks into ASS dialogue lines with uppercase punchy text."""
    lines = []
    for chunk in chunks:
        start_time = format_ass_timestamp(chunk[0].start)
        end_time = format_ass_timestamp(chunk[-1].end)
        text = " ".join(w.word.strip().upper() for w in chunk)
        lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
    return "\n".join(lines)


def generate_fallback_subtitles(script: str, total_duration: float, output_path: Path) -> Path:
    """Generate evenly spaced subtitles if whisper is unavailable or fails."""
    logger.info("Generating fallback proportional subtitles...")
    words = script.split()
    if not words or total_duration <= 0:
        words = ["TIMEREBORN"]
        total_duration = 5.0

    word_dur = total_duration / len(words)
    word_timestamps = [
        WordTimestamp(word=w, start=i * word_dur, end=(i + 1) * word_dur)
        for i, w in enumerate(words)
    ]
    chunks = chunk_words(word_timestamps, max_words=3)
    content = get_ass_header() + build_ass_events(chunks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def create_subtitles(
    audio_path: Path,
    output_ass_path: Path,
    script_fallback: Optional[str] = None,
    total_duration: Optional[float] = None,
    model_size: str = "tiny",
) -> Path:
    """Transcribe audio with faster-whisper to generate word-level ASS subtitles."""
    output_ass_path = Path(output_ass_path)
    output_ass_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel
        logger.info(f"Loading faster-whisper model '{model_size}' on CPU...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), word_timestamps=True)

        extracted_words: List[WordTimestamp] = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    extracted_words.append(WordTimestamp(word=w.word, start=w.start, end=w.end))

        if not extracted_words:
            raise ValueError("No words extracted by whisper")

        chunks = chunk_words(extracted_words, max_words=3)
        ass_content = get_ass_header() + build_ass_events(chunks)

        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info(f"Subtitles written successfully to {output_ass_path}")
        return output_ass_path

    except Exception as e:
        logger.warning(f"faster-whisper transcription failed or unavailable: {e}. Using fallback alignment.")
        from src.voice import get_audio_duration
        duration = total_duration or get_audio_duration(audio_path)
        return generate_fallback_subtitles(
            script=script_fallback or "Timereborn",
            total_duration=duration,
            output_path=output_ass_path,
        )


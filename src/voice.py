"""Voiceover synthesis using edge-tts (100% free neural voices)."""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional
import edge_tts

from src.state import load_settings

logger = logging.getLogger("timereborn.voice")


def get_default_voice_config() -> dict:
    """Read voice configuration from settings."""
    settings = load_settings()
    voice_cfg = settings.get("voice", {})
    return {
        "name": voice_cfg.get("name", "en-US-ChristopherNeural"),
        "rate": voice_cfg.get("rate", "+0%"),
        "pitch": voice_cfg.get("pitch", "+0Hz"),
    }


async def _synthesize_async(text: str, output_path: Path, voice: str, rate: str, pitch: str) -> None:
    """Asynchronously synthesize speech to mp3."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))


def get_audio_duration(audio_path: Path) -> float:
    """Measure exact duration of an audio file in seconds using ffprobe or ffmpeg fallback."""
    from src.render import get_ffmpeg_binary
    ffmpeg_bin = get_ffmpeg_binary()
    ffprobe_bin = ffmpeg_bin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")

    # Try ffprobe if available alongside ffmpeg
    try:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        pass

    # Fallback to parsing ffmpeg stderr output
    try:
        cmd = [ffmpeg_bin, "-i", str(audio_path)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Search for Duration: 00:00:15.34
        for line in result.stderr.splitlines():
            if "Duration:" in line:
                parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
                hours = float(parts[0])
                mins = float(parts[1])
                secs = float(parts[2])
                return hours * 3600 + mins * 60 + secs
    except Exception as e:
        logger.warning(f"Could not probe duration with ffmpeg: {e}")

    # Rough estimate fallback: ~150 words per minute if probing fails
    return 30.0


def generate_voiceover(
    text: str,
    output_path: Path,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    pitch: Optional[str] = None,
) -> float:
    """Synthesize voiceover for given text and return duration in seconds."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cfg = get_default_voice_config()
    chosen_voice = voice or cfg["name"]
    chosen_rate = rate or cfg["rate"]
    chosen_pitch = pitch or cfg["pitch"]

    logger.info(f"Generating voiceover with voice '{chosen_voice}' for {len(text.split())} words...")
    asyncio.run(_synthesize_async(text, output_path, chosen_voice, chosen_rate, chosen_pitch))

    duration = get_audio_duration(output_path)
    logger.info(f"Voiceover successfully generated at {output_path} (Duration: {duration:.2f}s)")
    return duration

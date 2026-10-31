"""Reference video analysis engine.

Scans video_idea/ directory, computes SHA-256 hashes, extracts technical,
audio, and visual properties, and synthesizes a full structural breakdown
into data/reference_analysis.json without re-analyzing cached files.
"""

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

from src.render import get_ffmpeg_binary
from src.scriptgen import get_default_model, get_groq_client
from src.state import load_settings

load_dotenv()
logger = logging.getLogger("timereborn.reference")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANALYSIS_FILE = DATA_DIR / "reference_analysis.json"


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file for change tracking."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_reference_analyses() -> Dict[str, Any]:
    """Load existing reference analysis cache."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ANALYSIS_FILE.exists():
        try:
            with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read {ANALYSIS_FILE}: {e}")
    return {}


def save_reference_analyses(data: Dict[str, Any]) -> None:
    """Save reference analysis cache atomically."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = ANALYSIS_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    temp_file.replace(ANALYSIS_FILE)


def analyze_technical(video_path: Path, ffmpeg_bin: str) -> Dict[str, Any]:
    """Extract technical video properties and detect scene cuts."""
    # Probe duration, resolution, fps via ffmpeg/ffprobe or reading container info
    probe_cmd = [ffmpeg_bin, "-i", str(video_path)]
    res = subprocess.run(
        probe_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    stderr = res.stderr

    duration = 0.0
    width = 1080
    height = 1920
    fps = 30.0

    dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", stderr)
    if dur_match:
        h, m, s = dur_match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    res_match = re.search(r"Stream.*Video:.*,\s*(\d{3,5})x(\d{3,5})", stderr)
    if res_match:
        width = int(res_match.group(1))
        height = int(res_match.group(2))

    fps_match = re.search(r"([\d\.]+)\s*fps", stderr)
    if fps_match:
        fps = float(fps_match.group(1))

    aspect_ratio = f"{width}:{height}" if width and height else "9:16"

    # Detect scene cuts using FFmpeg scene filter
    scene_cmd = [
        ffmpeg_bin,
        "-i", str(video_path),
        "-vf", "select=gt(scene\\,0.3),showinfo",
        "-f", "null",
        "-",
    ]
    scene_res = subprocess.run(
        scene_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    cut_timestamps = []
    for line in scene_res.stderr.splitlines():
        if "pts_time:" in line:
            m = re.search(r"pts_time:([\d\.]+)", line)
            if m:
                cut_timestamps.append(float(m.group(1)))

    cut_timestamps = sorted(list(set(cut_timestamps)))
    scene_cuts_count = len(cut_timestamps)
    avg_shot_length = (duration / max(1, scene_cuts_count + 1)) if duration > 0 else 2.5

    return {
        "duration": round(duration, 2),
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "fps": round(fps, 2),
        "scene_cuts_count": scene_cuts_count,
        "cut_timestamps": cut_timestamps,
        "average_shot_length_sec": round(avg_shot_length, 2),
    }


def analyze_audio(video_path: Path, ffmpeg_bin: str, temp_dir: Path) -> Dict[str, Any]:
    """Extract audio, generate word-level transcript, and compute pacing (WPM)."""
    audio_path = temp_dir / "ref_audio.mp3"
    extract_cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path),
    ]
    subprocess.run(extract_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return {
            "transcript": "",
            "words": [],
            "speaking_pace_wpm": 0,
            "has_voiceover": False,
            "has_music_only": False,
            "audio_mode": "no_audio",
        }

    # Transcribe audio using Groq Whisper API
    transcript_text = ""
    words_data = []
    try:
        client = get_groq_client()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                file=(audio_path.name, f.read()),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
            )
        transcript_text = resp.text.strip() if hasattr(resp, "text") else ""
        if hasattr(resp, "words") and resp.words:
            words_data = resp.words
    except Exception as e:
        logger.warning(f"Audio transcription failed: {e}")

    # Determine audio characteristics
    word_count = len(transcript_text.split()) if transcript_text else 0
    duration_match = len(words_data) > 0
    has_voiceover = word_count > 3

    # Check for music-only indicators (e.g. "Outro Music", "(music)")
    music_indicators = ["music", "outro", "instrumental", "applause"]
    has_music_only = (
        word_count == 0
        or (word_count < 5 and any(m in transcript_text.lower() for m in music_indicators))
    )
    if has_music_only:
        has_voiceover = False

    wpm = 0
    if has_voiceover and word_count > 0:
        # Approximate WPM
        wpm = int((word_count / max(1.0, words_data[-1].get("end", 15) if words_data else 15)) * 60)

    return {
        "transcript": transcript_text,
        "word_count": word_count,
        "speaking_pace_wpm": wpm,
        "has_voiceover": has_voiceover,
        "has_music_only": has_music_only,
        "audio_mode": "voiceover" if has_voiceover else ("music_only" if has_music_only else "silent"),
    }


def extract_keyframes(
    video_path: Path,
    cut_timestamps: List[float],
    duration: float,
    ffmpeg_bin: str,
    temp_dir: Path,
    max_frames: int = 12,
) -> List[Path]:
    """Extract up to max_frames keyframes across the video."""
    frames_dir = temp_dir / "keyframes"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Select representative timestamps
    if cut_timestamps:
        selected_times = cut_timestamps[:max_frames]
    else:
        # Sample evenly across duration
        step = duration / max(2, max_frames)
        selected_times = [step * (i + 1) for i in range(min(max_frames, 6))]

    frame_paths = []
    for i, t in enumerate(selected_times):
        out_frame = frames_dir / f"frame_{i}_{t:.1f}.jpg"
        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss", str(max(0.1, t)),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(out_frame),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out_frame.exists() and out_frame.stat().st_size > 0:
            frame_paths.append(out_frame)

    return frame_paths


def describe_keyframes_with_vision(frame_paths: List[Path]) -> List[str]:
    """Describe keyframes using Gemini API or swappable vision provider."""
    settings = load_settings()
    vision_cfg = settings.get("vision", {})
    provider = vision_cfg.get("provider", "gemini")

    gemini_key = os.getenv("GEMINI_API_KEY")

    if provider == "gemini" and gemini_key and frame_paths:
        try:
            # Sample up to 4 representative frames to minimize payload
            sampled_frames = frame_paths[:4]
            parts = []
            for fp in sampled_frames:
                with open(fp, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_data,
                    }
                })
            parts.append({
                "text": "Describe the visual style, characters, text overlays, color grading, and setting of these video frames in 3 concise sentences."
            })

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": parts}]}
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                res_data = resp.json()
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return [text.strip()]
        except Exception as e:
            logger.warning(f"Gemini vision call failed: {e}")

    # Fallback structural frame descriptions
    return [
        f"Frame {i+1} captured at scene cut. Resolution standard vertical format with high-contrast visual framing."
        for i in range(min(4, len(frame_paths)))
    ]


def synthesize_structure_with_llm(
    filename: str,
    tech: Dict[str, Any],
    audio: Dict[str, Any],
    visual_descriptions: List[str],
) -> Dict[str, Any]:
    """Turn technical, audio, and visual observations into structured analysis JSON."""
    client = get_groq_client()
    model = get_default_model()

    system_prompt = """You are an elite video format analyst.
Analyze the extracted video metrics, audio transcript, and visual descriptions of a reference video.
Your job is to reverse-engineer its core idea, narrative structure, pacing, captioning, and style.

Return strictly valid JSON with this exact schema:
{
  "topic": "Core topic name",
  "core_idea": "The underlying premise or curiosity paradox driving the video",
  "target_audience": "Target demographic and interest group",
  "hook_type_and_text": "Type of hook (e.g. pattern interrupt, bold assertion) and opening words",
  "story_structure": [
    {"timestamp_sec": 0.0, "beat": "Opening hook and pattern interrupt"},
    {"timestamp_sec": 4.0, "beat": "First revelation / tension escalation"},
    {"timestamp_sec": 10.0, "beat": "Climax / core insight"},
    {"timestamp_sec": 14.0, "beat": "Looping conclusion or call to action"}
  ],
  "caption_style": {
    "position": "center",
    "size": "large bold",
    "color": "white with black outline",
    "highlight_words": true
  },
  "pacing": "fast-paced (cut every 1-2s)",
  "tone": "cinematic and dramatic",
  "call_to_action": "engagement question or follow prompt",
  "length_seconds": 15.0,
  "visual_style": "Dramatic cinematic visuals with high-tension contrasts"
}
"""

    user_prompt = f"""File: {filename}
Duration: {tech['duration']}s | Resolution: {tech['width']}x{tech['height']} ({tech['aspect_ratio']})
Scene Cuts: {tech['scene_cuts_count']} | Average Shot Length: {tech['average_shot_length_sec']}s
Audio Mode: {audio['audio_mode']} | Word Count: {audio['word_count']} | Speaking Pace: {audio['speaking_pace_wpm']} WPM
Transcript: "{audio['transcript']}"
Visual Descriptions: {visual_descriptions}

Reverse-engineer this reference video and output the structured JSON analysis."""

    try:
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        content = res.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM structure synthesis failed: {e}")
        return {
            "topic": filename.rsplit(".", 1)[0].replace("_", " ").title(),
            "core_idea": "High-tension visual and historical storytelling",
            "target_audience": "General audience interested in viral history and modern paradoxes",
            "hook_type_and_text": "Opening visual hook and pattern interrupt",
            "story_structure": [
                {"timestamp_sec": 0.0, "beat": "Hook"},
                {"timestamp_sec": tech["duration"] * 0.5, "beat": "Body"},
                {"timestamp_sec": tech["duration"] * 0.9, "beat": "Conclusion"},
            ],
            "caption_style": {
                "position": "center",
                "size": "large bold",
                "color": "white with black outline",
                "highlight_words": True,
            },
            "pacing": "fast-paced",
            "tone": "cinematic",
            "call_to_action": "Follow for more",
            "length_seconds": tech["duration"],
            "visual_style": "High-contrast dynamic scenes",
        }


def analyze_reference_video(video_path: Path) -> Dict[str, Any]:
    """Perform complete analysis on a single reference video."""
    ffmpeg_bin = get_ffmpeg_binary()
    file_hash = compute_file_sha256(video_path)

    logger.info(f"Analyzing reference video: {video_path.name} (SHA-256: {file_hash[:12]}...)")

    with tempfile.TemporaryDirectory(prefix="ref_analysis_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Technical
        tech = analyze_technical(video_path, ffmpeg_bin)

        # 2. Audio
        audio = analyze_audio(video_path, ffmpeg_bin, tmp_dir)

        # 3. Visual Keyframes
        keyframes = extract_keyframes(
            video_path=video_path,
            cut_timestamps=tech["cut_timestamps"],
            duration=tech["duration"],
            ffmpeg_bin=ffmpeg_bin,
            temp_dir=tmp_dir,
        )
        visual_desc = describe_keyframes_with_vision(keyframes)

        # 4. Synthesize Structure
        structure = synthesize_structure_with_llm(
            filename=video_path.name,
            tech=tech,
            audio=audio,
            visual_descriptions=visual_desc,
        )

    return {
        "file_name": video_path.name,
        "sha256": file_hash,
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "technical": tech,
        "audio": audio,
        "structure": structure,
    }


def scan_and_update_references(reference_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Scan video_idea/ directory and analyze only NEW or CHANGED files."""
    settings = load_settings()
    ref_dir_name = settings.get("reference_dir", "video_idea")
    ref_dir = reference_dir or Path(__file__).resolve().parent.parent / ref_dir_name

    analyses = load_reference_analyses()
    if not ref_dir.exists():
        logger.warning(f"Reference directory does not exist: {ref_dir}")
        return analyses

    supported_exts = {".mp4", ".mov", ".webm"}
    video_files = [f for f in ref_dir.iterdir() if f.is_file() and f.suffix.lower() in supported_exts]

    updated = False
    for video_file in video_files:
        current_hash = compute_file_sha256(video_file)
        cached = analyses.get(video_file.name)

        if cached and cached.get("sha256") == current_hash:
            logger.info(f"Reference '{video_file.name}' is up to date in cache. Skipping.")
            continue

        try:
            analysis = analyze_reference_video(video_file)
            analyses[video_file.name] = analysis
            updated = True
            logger.info(f"Successfully analyzed and cached reference '{video_file.name}'")
        except Exception as e:
            logger.error(f"Failed to analyze reference '{video_file.name}': {e}")

    if updated:
        save_reference_analyses(analyses)

    return analyses


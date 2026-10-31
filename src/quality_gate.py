"""Automatic Quality Gate for fully autonomous publishing."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.recreate import compute_script_similarity
from src.render import get_ffmpeg_binary
from src.scriptgen import get_default_model, get_groq_client
from src.state import load_settings

logger = logging.getLogger("timereborn.quality_gate")


def probe_video_duration(video_path: Path, ffmpeg_bin: str) -> float:
    """Probe video duration using ffmpeg stderr output."""
    cmd = [ffmpeg_bin, "-i", str(video_path)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", res.stderr)
    if m:
        h, mn, s = m.groups()
        return int(h) * 3600 + int(mn) * 60 + float(s)
    return 0.0


def check_black_segments(video_path: Path, ffmpeg_bin: str) -> bool:
    """Check if video contains continuous black segments > 1.5 seconds."""
    cmd = [
        ffmpeg_bin,
        "-i", str(video_path),
        "-vf", "blackdetect=d=1.5:pix_th=0.10",
        "-f", "null",
        "-",
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
    if "black_start:" in res.stderr:
        logger.warning(f"Black segment detected in {video_path.name}")
        return True
    return False


def run_llm_script_review(script: str, hook: str) -> Tuple[bool, List[str]]:
    """Self-review script using LLM for hook strength, placeholder text, and hallucination."""
    client = get_groq_client()
    model = get_default_model()

    system_prompt = """You are a strict editorial quality inspector for short vertical videos.
Inspect this video script and hook.
REJECT if:
1. Contains placeholder text (e.g. '[Insert name]', 'TODO', '...', '[Link]', '[Author]').
2. Has no clear hook in the opening line to stop the scroll.
3. Contains absurd or obviously fabricated historical dates/facts.

Return strictly a JSON object:
{
  "passed": true|false,
  "issues": ["Issue 1", "Issue 2"]
}
"""
    user_prompt = f"Hook: {hook}\nScript: {script}"

    try:
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(res.choices[0].message.content)
        return bool(data.get("passed", True)), data.get("issues", [])
    except Exception as e:
        logger.warning(f"LLM quality review failed, defaulting to heuristic check: {e}")
        # Basic heuristic fallback
        placeholders = ["[", "]", "todo", "insert", "xxx"]
        lower = script.lower()
        if any(p in lower for p in placeholders):
            return False, ["Placeholder detected in script text"]
        return True, []


def run_quality_gate(
    video_path: Path,
    script: str,
    hook: str,
    subtitles_path: Path,
    audio_path: Path,
    target_duration: float,
    reference_transcript: str = "",
) -> Tuple[bool, List[str]]:
    """Run full automated quality gate before publishing."""
    settings = load_settings()
    qg_cfg = settings.get("quality_gate", {})
    min_dur = qg_cfg.get("min_duration_sec", 12)
    max_dur = qg_cfg.get("max_duration_sec", 60)
    max_similarity = qg_cfg.get("max_ngram_similarity", 0.15)

    ffmpeg_bin = get_ffmpeg_binary()
    issues: List[str] = []

    # 1. Video file existence and size
    if not video_path.exists() or video_path.stat().st_size < 500 * 1024:
        issues.append("Video file missing or corrupt (<500KB)")
        return False, issues

    # 2. Duration check
    actual_dur = probe_video_duration(video_path, ffmpeg_bin)
    if actual_dur < min_dur or actual_dur > max_dur:
        issues.append(f"Duration {actual_dur:.1f}s is out of range ({min_dur}-{max_dur}s)")

    # 3. Audio track check
    if not audio_path.exists() or audio_path.stat().st_size < 10 * 1024:
        issues.append("Audio track missing or empty")

    # 4. Captions check
    if not subtitles_path.exists() or subtitles_path.stat().st_size < 50:
        issues.append("Subtitles file (.ass) missing or empty")
    else:
        content = subtitles_path.read_text(encoding="utf-8", errors="replace")
        if "Dialogue:" not in content:
            issues.append("Subtitles file contains no dialogue entries")

    # 5. Black segments check
    if check_black_segments(video_path, ffmpeg_bin):
        issues.append("Video contains continuous black or blank frames")

    # 6. Script similarity check against reference
    sim = compute_script_similarity(script, reference_transcript)
    if sim > max_similarity:
        issues.append(f"Script similarity {sim:.3f} exceeds threshold {max_similarity}")

    # 7. LLM self-review
    llm_passed, llm_issues = run_llm_script_review(script=script, hook=hook)
    if not llm_passed:
        issues.extend(llm_issues)

    passed = len(issues) == 0
    if passed:
        logger.info(f"Quality gate PASSED for {video_path.name} (Duration: {actual_dur:.1f}s)")
    else:
        logger.warning(f"Quality gate FAILED for {video_path.name}: {issues}")

    return passed, issues


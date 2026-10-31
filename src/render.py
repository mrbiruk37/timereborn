"""FFmpeg-based rendering pipeline for vertical Shorts and horizontal long videos."""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("timereborn.render")


def get_ffmpeg_binary() -> str:
    """Locate ffmpeg binary across system PATH, env var, or imageio-ffmpeg."""
    env_bin = os.getenv("FFMPEG_BINARY")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    which_bin = shutil.which("ffmpeg")
    if which_bin:
        return which_bin

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    raise RuntimeError(
        "FFmpeg binary not found. Please install ffmpeg or run 'pip install imageio-ffmpeg'."
    )


def escape_ffmpeg_path(path: Path) -> str:
    """Escape file path for FFmpeg filter arguments (especially on Windows)."""
    # Replace backslashes with slashes and escape colon for drive letters (e.g. C\:/path)
    p_str = str(path.resolve()).replace("\\", "/")
    return p_str.replace(":", "\\:")


def render_scene_clip(
    scene: Dict[str, Any],
    index: int,
    output_clip_path: Path,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> Path:
    """Render a single normalized video segment for concatenation."""
    ffmpeg_bin = get_ffmpeg_binary()
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)
    duration = scene.get("duration", 5.0)
    scene_type = scene.get("type", "generated")
    src_path = scene.get("path")

    if scene_type == "video" and src_path and os.path.exists(src_path):
        # Scale, crop to fill screen, trim to duration
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps}"
        cmd = [
            ffmpeg_bin, "-y",
            "-stream_loop", "-1",
            "-i", str(src_path),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_clip_path),
        ]
    elif scene_type == "image" and src_path and os.path.exists(src_path):
        # Ken Burns smooth zoom animation
        frames = int(duration * fps)
        vf = (
            f"scale=8000:-1,zoompan=z='min(zoom+0.0015,1.25)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
            f"setsar=1"
        )
        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(src_path),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_clip_path),
        ]
    else:
        # Sleek dark cinematic fallback gradient/canvas
        vf = f"color=c=0x0D1117:s={width}x{height}:d={duration},fps={fps},setsar=1"
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_clip_path),
        ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return output_clip_path


def inject_hook_into_ass(ass_path: Path, hook_text: str, duration: float = 2.5) -> None:
    """Prepend an animated hook badge into the ASS subtitle events."""
    if not ass_path.exists() or not hook_text:
        return

    try:
        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        clean_hook = hook_text.strip().replace("\n", " ").upper()
        # Word wrap hook text if long
        hook_words = clean_hook.split()
        if len(hook_words) > 5:
            mid = len(hook_words) // 2
            clean_hook = " ".join(hook_words[:mid]) + "\\N" + " ".join(hook_words[mid:])

        hook_line = (
            f"Dialogue: 1,0:00:00.00,0:00:{duration:05.2f},Hook,,0,0,0,,"
            f"{{\\an8\\pos(540,240)\\fad(150,250)\\c&H00FFFF&\\bord5\\shad3}}{clean_hook}\n"
        )

        if "[Events]" in content:
            parts = content.split("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            if len(parts) == 2:
                updated = parts[0] + "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + hook_line + parts[1]
                with open(ass_path, "w", encoding="utf-8") as f:
                    f.write(updated)
    except Exception as e:
        logger.warning(f"Could not inject hook overlay into subtitles: {e}")


def render_video(
    scenes: List[Dict[str, Any]],
    voiceover_path: Path,
    subtitles_path: Path,
    output_path: Path,
    hook_text: Optional[str] = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> Path:
    """Render full video with burned subtitles, visual clips, and voiceover audio."""
    ffmpeg_bin = get_ffmpeg_binary()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_path.parent / "temp_render"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if hook_text and subtitles_path.exists():
        inject_hook_into_ass(subtitles_path, hook_text, duration=2.5)

    # 1. Normalize each scene clip
    rendered_clips = []
    for idx, scene in enumerate(scenes):
        clip_dest = temp_dir / f"clip_{idx}.mp4"
        logger.info(f"Rendering scene clip {idx + 1}/{len(scenes)} ({scene.get('type')})...")
        render_scene_clip(scene, idx, clip_dest, width=width, height=height, fps=fps)
        rendered_clips.append(clip_dest)

    # 2. Build concat demuxer file
    concat_list_file = temp_dir / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for c in rendered_clips:
            # Escape path for concat demuxer
            safe_c = str(c.resolve()).replace("\\", "/")
            f.write(f"file '{safe_c}'\n")

    # 3. Concatenate video clips into a base video
    raw_video = temp_dir / "raw_concat.mp4"
    concat_cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(raw_video),
    ]
    subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    # 4. Final assembly: merge raw video + audio + burn subtitles (.ass)
    escaped_ass = escape_ffmpeg_path(subtitles_path)
    vf = f"ass='{escaped_ass}'"

    final_cmd = [
        ffmpeg_bin, "-y",
        "-i", str(raw_video),
        "-i", str(voiceover_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ]

    logger.info(f"Rendering final assembled video to {output_path}...")
    res = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg render error: {res.stderr}")
        raise RuntimeError(f"FFmpeg failed with exit code {res.returncode}: {res.stderr}")

    logger.info(f"Video rendering complete: {output_path}")

    # Cleanup temp directory
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return output_path

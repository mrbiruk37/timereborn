"""TikTok Repost Engine: Downloads, sanitizes, rewrites metadata, and publishes to YouTube Shorts & TikTok."""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import imageio_ffmpeg
from groq import Groq

from src.state import DATA_DIR, add_post
from src.telegram import send_message, send_video
from src.tiktok import format_tiktok_caption, post_to_tiktok
from src.youtube import upload_video

logger = logging.getLogger("timereborn.repost")

REPOSTS_FILE = DATA_DIR / "reposts.json"


def load_reposts() -> List[Dict[str, Any]]:
    """Load list of processed repost records."""
    if not REPOSTS_FILE.exists():
        return []
    try:
        with open(REPOSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read reposts.json: {e}")
        return []


def is_already_reposted(video_id_or_url: str) -> bool:
    """Check if a video ID or URL has already been processed."""
    reposts = load_reposts()
    clean_target = video_id_or_url.strip().lower()
    for item in reposts:
        if clean_target == item.get("video_id", "").strip().lower():
            return True
        if clean_target in item.get("original_url", "").strip().lower():
            return True
    return False


def record_repost(record: Dict[str, Any]) -> None:
    """Save a processed repost record to prevent duplicates."""
    reposts = load_reposts()
    reposts.append(record)
    REPOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPOSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reposts, f, indent=2)


def extract_tiktok_url(text: str) -> Optional[str]:
    """Find the first TikTok URL in a text message."""
    pattern = r"(https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+)"
    match = re.search(pattern, text)
    if match:
        # Strip trailing punctuation if accidentally included
        url = match.group(1).rstrip(".,;!?'\"")
        return url
    return None


def download_tiktok_video(url: str, output_dir: Path) -> Dict[str, Any]:
    """Download a TikTok video without watermark using yt-dlp."""
    import yt_dlp

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_template = str(output_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }

    logger.info(f"Downloading TikTok video from {url}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError(f"Failed to extract info from TikTok URL: {url}")

        downloaded_file = Path(ydl.prepare_filename(info))
        # Handle case where extension might differ
        if not downloaded_file.exists():
            matches = list(output_dir.glob(f"{info.get('id')}*"))
            if matches:
                downloaded_file = matches[0]

        return {
            "video_path": downloaded_file,
            "video_id": str(info.get("id") or ""),
            "title": str(info.get("title") or ""),
            "description": str(info.get("description") or ""),
            "duration": float(info.get("duration") or 0.0),
            "uploader": str(info.get("uploader") or info.get("channel") or ""),
            "original_url": str(info.get("webpage_url") or url),
        }


def sanitize_and_reencode_video(input_path: Path, output_path: Path) -> Path:
    """Sanitize and subtly re-encode video to bypass duplicate-content detection.
    
    Operations:
    - Strips all original metadata (-map_metadata -1).
    - Subtle speed shift (1.01x) to create a unique audio fingerprint and PTS.
    - Forces 1080x1920 vertical format with centered padding.
    - Encodes clean H.264 video with AAC audio.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(input_path),
        "-vf", "setpts=PTS/1.01,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-af", "atempo=1.01",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info(f"Re-encoding video {input_path.name} to {output_path.name} with anti-duplicate filters...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"FFmpeg re-encoding failed: {result.stderr}")

    return output_path


def generate_repost_metadata(original_title: str, original_description: str, uploader: str) -> Dict[str, Any]:
    """Generate fresh viral title, description, and hashtags using Groq LLM."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    client = Groq(api_key=api_key)

    prompt = f"""You are an elite short-form content growth strategist.
Analyze this TikTok video's original concept and create 100% FRESH, VIRAL metadata for YouTube Shorts and TikTok.
Do NOT copy the original words or titles verbatim. Reframe the core idea with maximum curiosity, suspense, and emotional hook.

Original Context:
- Creator/Channel: {uploader}
- Original Title: {original_title}
- Original Description: {original_description}

Return ONLY valid JSON with no markdown wrapping:
{{
  "title": "Compelling Title under 80 chars (do NOT include #Shorts, system will add it)",
  "hook": "Punchy 1-sentence opening curiosity hook",
  "description": "Engaging 2-3 sentence description with key takeaway and call to subscribe/follow",
  "hashtags": ["#Shorts", "#TimeReborn", "#Viral", "#Storytelling", "#History", "#Mindset"],
  "tags": ["Shorts", "TimeReborn", "Stoicism", "Mindset", "Wisdom", "History", "ViralShorts"]
}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=600,
    )

    raw_text = response.choices[0].message.content or "{}"
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    try:
        data = json.loads(raw_text)
    except Exception as e:
        logger.warning(f"JSON parsing error: {e}. Fallback metadata used.")
        data = {
            "title": f"The Untold Reality Behind This Story",
            "hook": "What they never told you changes everything.",
            "description": "Discover the hidden truth behind this timeless paradox. #Shorts #TimeReborn",
            "hashtags": ["#Shorts", "#TimeReborn", "#Viral", "#History"],
            "tags": ["Shorts", "TimeReborn", "History", "Viral"],
        }

    return data


def repost_from_url(
    tiktok_url: str,
    slot: str = "telegram_trigger",
    dry_run: bool = False,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute full repost pipeline: Download -> Sanitize -> Rewrite -> Upload to YouTube Shorts & TikTok -> Telegram receipt."""
    logger.info(f"=== Starting TikTok Repost for URL: {tiktok_url} (dry_run={dry_run}) ===")

    with tempfile.TemporaryDirectory(prefix="timereborn_repost_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Download source video
        send_message("Step 1/4: Downloading video from TikTok...", chat_id=chat_id, dry_run=dry_run)
        dl_info = download_tiktok_video(tiktok_url, tmp_dir)
        vid_id = dl_info["video_id"]
        source_vid = dl_info["video_path"]

        if is_already_reposted(vid_id):
            logger.info(f"Video ID {vid_id} was already reposted. Skipping to avoid duplicate upload.")
            send_message(f"Skipped: Video ID {vid_id} has already been reposted.", chat_id=chat_id, dry_run=dry_run)
            return {"status": "skipped", "reason": "already_reposted", "video_id": vid_id}

        # 2. Generate completely fresh viral metadata
        send_message("Step 2/4: Generating fresh viral title & hashtags with AI...", chat_id=chat_id, dry_run=dry_run)
        meta = generate_repost_metadata(
            original_title=dl_info["title"],
            original_description=dl_info["description"],
            uploader=dl_info["uploader"],
        )

        chosen_title = meta.get("title", "The Untold Story").strip()
        safe_name = "".join(c if c.isalnum() else "_" for c in chosen_title[:30]).strip("_")
        
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        final_video = output_dir / f"repost_{safe_name}.mp4"

        # 3. Sanitize and re-encode with anti-duplicate filters
        send_message("Step 3/4: Re-encoding video with anti-duplicate filters...", chat_id=chat_id, dry_run=dry_run)
        sanitize_and_reencode_video(source_vid, final_video)

        # 4. Upload to YouTube as a Public Short
        send_message("Step 4/4: Uploading public video to YouTube Shorts...", chat_id=chat_id, dry_run=dry_run)
        if dry_run:
            yt_id = "dry_run_repost"
            yt_url = "https://youtu.be/dry_run_repost"
            actual_privacy = "public"
            logger.info(f"[DRY-RUN] Would upload to YouTube Shorts: {chosen_title}")
        else:
            logger.info(f"Uploading to YouTube Shorts: '{chosen_title}'...")
            yt_res = upload_video(
                video_path=final_video,
                title=chosen_title,
                description=meta["description"],
                tags=meta.get("tags", ["Shorts", "TimeReborn"]),
                privacy_status="public",
            )
            yt_id = yt_res["video_id"]
            yt_url = yt_res["video_url"]
            actual_privacy = yt_res.get("privacy_status", "public")

        # 5. Format TikTok Caption
        tags_list = meta.get("hashtags", ["#Shorts", "#TimeReborn", "#Viral", "#FYP"])
        tag_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tags_list[:7]])
        tiktok_copy_text = f"{chosen_title}\n\n{meta.get('hook', '')}\n\n{tag_str}".strip()
        tiktok_status = "delivered_to_telegram"

        # 6. Telegram Dispatch: Deliver ready-to-post MP4 and plain receipt
        send_video(
            video_path=final_video,
            caption=f"TikTok Ready\n\nTitle: {chosen_title}\n\n{tag_str}"[:1024],
            chat_id=chat_id,
            dry_run=dry_run,
        )

        receipt = (
            "Posted to YouTube (Shorts)\n"
            f"Title: {chosen_title}\n"
            f"Link: {yt_url}\n"
            f"Slot: {slot}\n"
            f"Source: {dl_info.get('uploader', 'TikTok')} ({vid_id})\n\n"
            "TikTok Caption (Copy & Paste):\n"
            f"{tiktok_copy_text}"
        )
        send_message(receipt, chat_id=chat_id, dry_run=dry_run)

        # 7. Record post in posts.json and reposts.json
        post_record = {
            "id": yt_id,
            "youtube_id": yt_id,
            "youtube_url": yt_url,
            "platform": "YouTube Shorts",
            "title": chosen_title,
            "hook": meta.get("hook", ""),
            "original_tiktok_id": vid_id,
            "original_author": dl_info.get("uploader", ""),
            "original_url": dl_info.get("original_url", tiktok_url),
            "slot": slot,
            "privacy_status": actual_privacy,
            "status": "published",
            "tiktok_status": tiktok_status,
            "video_path": str(final_video),
            "duration_seconds": dl_info.get("duration", 0.0),
        }
        add_post(post_record)
        record_repost({
            "video_id": vid_id,
            "original_url": dl_info.get("original_url", tiktok_url),
            "original_author": dl_info.get("uploader", ""),
            "title": chosen_title,
            "youtube_url": yt_url,
            "reposted_at": post_record.get("created_at", ""),
        })

        return post_record


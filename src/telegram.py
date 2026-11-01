"""Official Telegram Bot API client for real post reports and alert dispatch.

Enforces:
- Strict real data only (no placeholders, test messages, fake numbers, or celebratory emojis)
- Dry-run mode (--dry-run or DRY_RUN=1) printing to console without network calls
- Plain-text post receipts and failure alerts
"""

import html
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("timereborn.telegram")


def is_dry_run() -> bool:
    """Check if dry-run mode is active via environment or setting."""
    return os.getenv("DRY_RUN", "0") in ("1", "true", "True")


def get_telegram_config() -> Dict[str, str]:
    """Retrieve and validate Telegram token and chat ID."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError(
            "Missing Telegram credentials. Please set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in your environment or .env file."
        )
    return {"token": token, "chat_id": chat_id}


def format_real_post_message(post_record: Dict[str, Any]) -> str:
    """Generate plain-text post message strictly from a real post record.
    
    Refuses to send if required fields are missing or look like placeholders.
    """
    title = post_record.get("title", "").strip()
    url = post_record.get("youtube_url", "").strip()
    platform = post_record.get("platform", "YouTube")
    ref_file = post_record.get("reference_file", "none")
    style_variant = post_record.get("style_variant", "standard")
    slot = post_record.get("slot_time_utc") or post_record.get("slot", "auto")

    # Strict validation: prevent any placeholder or incomplete record from sending
    placeholder_triggers = ["<", ">", "[", "]", "placeholder", "untitled", "test video"]
    if not title or any(t in title.lower() for t in placeholder_triggers):
        raise ValueError(f"Invalid post title for Telegram notification: '{title}'")
    if not url or not url.startswith("http"):
        raise ValueError(f"Invalid post URL for Telegram notification: '{url}'")

    msg = (
        f"Posted to {platform}\n"
        f"Title: {title}\n"
        f"Link: {url}\n"
        f"Slot: {slot}\n"
        f"Based on: {ref_file} | Style: {style_variant}"
    )

    tags_list = post_record.get("hashtags") or ["#Shorts", "#TimeReborn", "#Viral", "#FYP"]
    tag_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tags_list[:7]])
    msg += (
        f"\n\nTikTok Ready (Copy & Paste):\n"
        f"Title: {title}\n"
        f"{tag_str}"
    )
    return msg


def send_message(
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = None,
    chat_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Send text message to Telegram or print to console if dry-run."""
    if dry_run or is_dry_run():
        print(f"[DRY-RUN TELEGRAM MESSAGE]\n{text}\n")
        return {"ok": True, "dry_run": True}

    cfg = get_telegram_config()
    target_chat = chat_id or cfg["chat_id"]
    url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"

    payload: Dict[str, Any] = {
        "chat_id": target_chat,
        "text": text,
        "disable_web_page_preview": False,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    backoff = 1.0
    for attempt in range(3):
        try:
            resp = requests.post(url, data=payload, timeout=20)
            res_data = resp.json()
            if resp.status_code == 200 and res_data.get("ok"):
                return res_data
            elif resp.status_code == 429:
                retry_after = res_data.get("parameters", {}).get("retry_after", backoff)
                time.sleep(retry_after)
            else:
                logger.error(f"Telegram error {resp.status_code}: {resp.text}")
                return res_data
        except requests.RequestException as e:
            logger.warning(f"Telegram request failed (attempt {attempt + 1}): {e}")
            time.sleep(backoff)
            backoff *= 2

    return {"ok": False, "description": "Failed to send message after retries"}


def send_video(
    video_path: Path,
    caption: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    chat_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Send video file to Telegram chat (used for TikTok dispatch)."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    if dry_run or is_dry_run():
        print(f"[DRY-RUN TELEGRAM VIDEO] {video_path.name} | Caption: {caption[:60]}...")
        return {"ok": True, "dry_run": True}

    cfg = get_telegram_config()
    target_chat = chat_id or cfg["chat_id"]

    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        logger.warning(f"Video file ({size_mb:.1f}MB) exceeds Telegram 50MB limit.")
        send_message(f"Video exceeds Telegram 50MB limit: {video_path.name}")
        return {"ok": False, "description": "File exceeds 50MB limit"}

    url = f"https://api.telegram.org/bot{cfg['token']}/sendVideo"
    data: Dict[str, Any] = {
        "chat_id": target_chat,
        "caption": caption[:1024],
        "supports_streaming": True,
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    with open(video_path, "rb") as video_file:
        files = {"video": (video_path.name, video_file, "video/mp4")}
        resp = requests.post(url, data=data, files=files, timeout=120)

    res_data = resp.json()
    return res_data


def send_post_notification(post_record: Dict[str, Any], dry_run: bool = False) -> None:
    """Send real post receipt to Telegram."""
    msg = format_real_post_message(post_record)
    send_message(text=msg, dry_run=dry_run)


def send_alert(error_summary: str, details: Optional[str] = None, dry_run: bool = False) -> None:
    """Send a plain, short 1-2 line failure alert."""
    clean_summary = str(error_summary).replace("\n", " ").strip()
    text = f"Pipeline error: {clean_summary}"
    if details:
        clean_details = str(details).replace("\n", " ").strip()
        text += f"\nDetails: {clean_details[:150]}"

    try:
        send_message(text=text, dry_run=dry_run)
    except Exception as e:
        logger.error(f"Could not send Telegram alert: {e}")


def get_updates(offset: Optional[int] = None, timeout: int = 10) -> List[Dict[str, Any]]:
    """Poll Telegram getUpdates for commands (/pause, /resume, /stats, /idea)."""
    cfg = get_telegram_config()
    url = f"https://api.telegram.org/bot{cfg['token']}/getUpdates"
    params: Dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=timeout + 20)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", [])
        return []
    except Exception as e:
        logger.warning(f"Error fetching Telegram updates: {e}")
        return []

"""Official Telegram Bot API client for reports, TikTok video delivery, and approval flow."""

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


def send_message(
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "HTML",
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send text message to Telegram chat with exponential backoff."""
    cfg = get_telegram_config()
    target_chat = chat_id or cfg["chat_id"]
    url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"

    payload: Dict[str, Any] = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    backoff = 1.0
    for attempt in range(4):
        try:
            resp = requests.post(url, data=payload, timeout=20)
            res_data = resp.json()
            if resp.status_code == 200 and res_data.get("ok"):
                return res_data
            elif resp.status_code == 429:
                retry_after = res_data.get("parameters", {}).get("retry_after", backoff)
                logger.warning(f"Telegram rate limited. Waiting {retry_after}s...")
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
) -> Dict[str, Any]:
    """Send video file to Telegram chat (used for manual TikTok publishing)."""
    cfg = get_telegram_config()
    target_chat = chat_id or cfg["chat_id"]
    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    # Check file size (Telegram Bot API standard limit is 50MB)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        logger.warning(f"Video file ({size_mb:.1f}MB) exceeds Telegram 50MB limit.")
        send_message(
            f"⚠️ <b>Video too large for Telegram ({size_mb:.1f}MB)</b>\n"
            f"File: <code>{video_path.name}</code>\n"
            f"Caption: {caption}"
        )
        return {"ok": False, "description": "File exceeds 50MB limit"}

    url = f"https://api.telegram.org/bot{cfg['token']}/sendVideo"
    data: Dict[str, Any] = {
        "chat_id": target_chat,
        "caption": caption[:1024],  # Telegram caption max length
        "parse_mode": "HTML",
        "supports_streaming": True,
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    logger.info(f"Uploading video {video_path.name} ({size_mb:.2f}MB) to Telegram...")
    with open(video_path, "rb") as video_file:
        files = {"video": (video_path.name, video_file, "video/mp4")}
        resp = requests.post(url, data=data, files=files, timeout=120)

    res_data = resp.json()
    if resp.status_code == 200 and res_data.get("ok"):
        logger.info("Video successfully delivered to Telegram!")
    else:
        logger.error(f"Failed to upload video to Telegram: {resp.text}")

    return res_data


def send_approval_request(
    video_id: str,
    title: str,
    youtube_url: str,
    video_path: Path,
    caption: str,
    slot: str = "manual",
    concept_notes: str = "",
) -> None:
    """Send TikTok-ready video and YouTube approval request with inline buttons."""
    # 1. Send the TikTok video with caption and hashtags
    tiktok_caption = (
        f"📱 <b>TikTok-Ready Video</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Caption:</b>\n{caption}"
    )
    send_video(video_path=video_path, caption=tiktok_caption)

    # 2. Send YouTube report with inline approval buttons
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve (Publish)", "callback_data": f"approve:{video_id}"},
                {"text": "❌ Reject (Delete)", "callback_data": f"reject:{video_id}"},
            ]
        ]
    }

    report_text = (
        f"🎬 <b>New Video Uploaded (Private)</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Slot:</b> <code>{slot}</code>\n"
        f"<b>YouTube Link:</b> <a href=\"{youtube_url}\">{youtube_url}</a>\n"
        f"<b>Concept/Pattern:</b> {concept_notes or 'Algorithmic curiosity hook'}\n\n"
        f"Review the private YouTube upload or the attached MP4. Click below to approve for public release or reject."
    )

    send_message(text=report_text, reply_markup=keyboard)


def send_alert(error_summary: str, details: Optional[str] = None) -> None:
    """Send an immediate alert on any pipeline failure (Hard Rule)."""
    text = f"🚨 <b>TIMEREBORN FAILURE ALERT</b>\n\n<b>Error:</b> {error_summary}"
    if details:
        text += f"\n\n<pre>{details[:500]}</pre>"
    try:
        send_message(text=text)
    except Exception as e:
        logger.error(f"Could not send Telegram alert: {e}")

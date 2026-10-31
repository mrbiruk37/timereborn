"""Official Telegram Bot API client for reports, TikTok delivery, approval flow, and polling."""

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


def edit_message_text(
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "HTML",
) -> Dict[str, Any]:
    """Edit an existing message text in Telegram."""
    cfg = get_telegram_config()
    url = f"https://api.telegram.org/bot{cfg['token']}/editMessageText"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        resp = requests.post(url, data=payload, timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to edit message {message_id}: {e}")
        return {"ok": False, "description": str(e)}


def answer_callback_query(callback_query_id: str, text: Optional[str] = None) -> Dict[str, Any]:
    """Acknowledge Telegram inline button click."""
    cfg = get_telegram_config()
    url = f"https://api.telegram.org/bot{cfg['token']}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        resp = requests.post(url, data=payload, timeout=10)
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")
        return {"ok": False}


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
        "caption": caption[:1024],
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
    tiktok_status: Optional[str] = None,
) -> None:
    """Send TikTok-ready video and YouTube approval request with inline buttons."""
    tiktok_caption = (
        f"📱 <b>TikTok Video & Template</b>\n\n"
        f"{caption}"
    )
    send_video(video_path=video_path, caption=tiktok_caption)

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve (Publish Live)", "callback_data": f"approve:{video_id}"},
                {"text": "❌ Reject (Delete)", "callback_data": f"reject:{video_id}"},
            ]
        ]
    }

    tiktok_info = f"\n<b>TikTok:</b> {tiktok_status}" if tiktok_status else ""

    escaped_title = html.escape(title)
    escaped_notes = html.escape(concept_notes or "TimeReborn perspective")

    report_text = (
        f"🎬 <b>New Video Uploaded!</b>\n\n"
        f"<b>Title:</b> {escaped_title}\n"
        f"<b>YouTube Link:</b> <a href=\"{youtube_url}\">{youtube_url}</a>{tiktok_info}\n"
        f"<b>Status:</b> 🔒 Private (Awaiting Approval)\n"
        f"<b>Slot:</b> <code>{slot}</code>\n"
        f"<b>Premise:</b> {escaped_notes}\n\n"
        f"<i>Tap Approve below to set YouTube video to Public!</i>"
    )

    send_message(text=report_text, reply_markup=keyboard)


def send_alert(error_summary: str, details: Optional[str] = None) -> None:
    """Send an immediate alert on any pipeline failure (Hard Rule)."""
    clean_summary = html.escape(str(error_summary))
    text = f"🚨 <b>TIMEREBORN FAILURE ALERT</b>\n\n<b>Error:</b> {clean_summary}"
    if details:
        clean_details = html.escape(str(details)[:500])
        text += f"\n\n<pre>{clean_details}</pre>"
    try:
        send_message(text=text)
    except Exception as e:
        logger.error(f"Could not send Telegram alert: {e}")


def get_updates(offset: Optional[int] = None, timeout: int = 10) -> List[Dict[str, Any]]:
    """Poll Telegram getUpdates for new messages and button callbacks."""
    cfg = get_telegram_config()
    url = f"https://api.telegram.org/bot{cfg['token']}/getUpdates"
    params: Dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", [])
        return []
    except Exception as e:
        logger.warning(f"Error fetching Telegram updates: {e}")
        return []

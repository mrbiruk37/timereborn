"""Telegram Polling Engine: Handles allowed bot commands (/pause, /resume, /stats, /idea)."""

import logging
import os
import time
from typing import Any, Dict, List, Optional
import yaml

from src.ideas import add_user_idea
from src.state import (
    SETTINGS_FILE,
    get_stats,
    load_settings,
)
from src.telegram import (
    get_telegram_config,
    get_updates,
    send_message,
)

logger = logging.getLogger("timereborn.telegram_poll")

POLL_STATE_FILE = SETTINGS_FILE.parent.parent / "data" / ".telegram_offset"


def get_last_offset() -> Optional[int]:
    """Retrieve last processed update_id offset."""
    if POLL_STATE_FILE.exists():
        try:
            return int(POLL_STATE_FILE.read_text().strip())
        except Exception:
            return None
    return None


def save_last_offset(offset: int) -> None:
    """Save processed update_id offset."""
    try:
        POLL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        POLL_STATE_FILE.write_text(str(offset))
    except Exception as e:
        logger.warning(f"Could not save telegram offset: {e}")


def update_settings_key(key: str, value: Any) -> None:
    """Safely update a top-level key in config/settings.yml."""
    settings = load_settings()
    settings[key] = value
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, default_flow_style=False)


def handle_command(text: str, chat_id: str) -> None:
    """Handle plain-text commands: /pause, /resume, /stats, /idea."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    logger.info(f"Processing command '{cmd}' (arg: '{arg}')")

    if cmd in ("/pause", "/pause@"):
        update_settings_key("status", "paused")
        send_message("Posting paused.", chat_id=chat_id)

    elif cmd in ("/resume", "/resume@"):
        update_settings_key("status", "active")
        send_message("Posting resumed.", chat_id=chat_id)

    elif cmd in ("/stats", "/stats@"):
        stats = get_stats()
        last_7 = stats.get("last_7_days")
        if not last_7 or last_7.get("total_videos", 0) == 0:
            send_message("No data yet.", chat_id=chat_id)
        else:
            msg = (
                "7-Day Stats\n"
                f"Videos: {last_7.get('total_videos', 0)}\n"
                f"Views: {last_7.get('total_views', 0)}\n"
                f"Likes: {last_7.get('total_likes', 0)}\n"
                f"Comments: {last_7.get('total_comments', 0)}"
            )
            send_message(msg, chat_id=chat_id)

    elif cmd in ("/idea", "/idea@"):
        if not arg:
            send_message("Usage: /idea <concept or link>", chat_id=chat_id)
            return

        idea = add_user_idea(arg)
        send_message(f"Idea added: {idea['title_seed']}", chat_id=chat_id)


def poll_telegram_events() -> int:
    """Execute a single polling sweep of Telegram getUpdates for commands."""
    try:
        cfg = get_telegram_config()
    except Exception as e:
        logger.warning(f"Telegram polling skipped: {e}")
        return 0

    owner_chat_id = str(cfg["chat_id"])
    last_offset = get_last_offset()
    updates = get_updates(offset=last_offset, timeout=5)

    if not updates:
        return 0

    max_update_id = last_offset or 0
    handled_count = 0

    for upd in updates:
        upd_id = upd.get("update_id", 0)
        if upd_id > max_update_id:
            max_update_id = upd_id

        msg = upd.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id"))
        text = msg.get("text", "")

        # Process commands only from authenticated owner chat
        if chat_id == owner_chat_id and text.startswith("/"):
            handle_command(text, chat_id)
            handled_count += 1

    if max_update_id:
        save_last_offset(max_update_id + 1)

    return handled_count

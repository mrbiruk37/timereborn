"""Telegram Polling Engine: Handles inline button callbacks and owner bot commands."""

import logging
import os
import time
from typing import Any, Dict, List, Optional
import yaml

from src.ideas import add_user_idea
from src.state import (
    SETTINGS_FILE,
    get_comments,
    get_posts,
    get_stats,
    load_settings,
    save_comments,
    save_posts,
)
from src.telegram import (
    answer_callback_query,
    edit_message_text,
    get_telegram_config,
    get_updates,
    send_message,
)
from src.youtube import delete_video, update_video_privacy

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


def handle_callback_query(cq: Dict[str, Any]) -> None:
    """Handle interactive button presses: Approve, Reject, Reply Approve/Reject."""
    cq_id = cq["id"]
    data = cq.get("data", "")
    msg = cq.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id"))
    msg_id = msg.get("message_id")

    logger.info(f"Received Telegram callback: '{data}'")

    if data.startswith("approve:"):
        vid_id = data.split("approve:")[1]
        try:
            update_video_privacy(vid_id, "public")
            posts = get_posts()
            for p in posts:
                if p.get("youtube_id") == vid_id or p.get("id") == vid_id:
                    p["status"] = "published"
                    p["privacy_status"] = "public"
            save_posts(posts)

            answer_callback_query(cq_id, text="Video approved and published!")
            if msg_id:
                edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"✅ <b>Video Published Live!</b>\n\nYouTube Video ID: <code>{vid_id}</code> is now public.",
                )
        except Exception as e:
            logger.error(f"Error publishing video {vid_id}: {e}")
            answer_callback_query(cq_id, text=f"Error: {e}")

    elif data.startswith("reject:"):
        vid_id = data.split("reject:")[1]
        try:
            delete_video(vid_id)
            posts = get_posts()
            for p in posts:
                if p.get("youtube_id") == vid_id or p.get("id") == vid_id:
                    p["status"] = "rejected"
            save_posts(posts)

            answer_callback_query(cq_id, text="Video deleted.")
            if msg_id:
                edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"❌ <b>Video Rejected and Deleted</b>\n\nYouTube Video ID: <code>{vid_id}</code> has been removed.",
                )
        except Exception as e:
            logger.error(f"Error deleting video {vid_id}: {e}")
            answer_callback_query(cq_id, text=f"Error: {e}")

    elif data.startswith("reply_approve:"):
        cid = data.split("reply_approve:")[1]
        from src.comments import post_youtube_reply
        comments = get_comments()
        reply_posted = False
        for c in comments:
            if c.get("comment_id") == cid:
                draft = c.get("draft_reply")
                if draft:
                    reply_posted = post_youtube_reply(cid, draft)
                    c["status"] = "replied"
                    c["replied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_comments(comments)

        if reply_posted:
            answer_callback_query(cq_id, text="Reply posted on YouTube!")
            if msg_id:
                edit_message_text(chat_id=chat_id, message_id=msg_id, text="✅ <b>Reply successfully posted on YouTube.</b>")
        else:
            answer_callback_query(cq_id, text="Failed to post reply.")

    elif data.startswith("reply_reject:"):
        cid = data.split("reply_reject:")[1]
        comments = get_comments()
        for c in comments:
            if c.get("comment_id") == cid:
                c["status"] = "dismissed"
        save_comments(comments)
        answer_callback_query(cq_id, text="Reply dismissed.")
        if msg_id:
            edit_message_text(chat_id=chat_id, message_id=msg_id, text="❌ <b>Reply dismissed.</b>")


def handle_command(text: str, chat_id: str) -> None:
    """Handle text commands: /pause, /resume, /stats, /idea, /mode."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    logger.info(f"Processing command '{cmd}' (arg: '{arg}')")

    if cmd in ("/pause", "/pause@"):
        update_settings_key("status", "paused")
        send_message("⏸️ <b>Timereborn is now PAUSED.</b>\nScheduled video slots are suspended until resumed.", chat_id=chat_id)

    elif cmd in ("/resume", "/resume@"):
        update_settings_key("status", "active")
        send_message("▶️ <b>Timereborn is now ACTIVE.</b>\nScheduled video posting resumed.", chat_id=chat_id)

    elif cmd in ("/mode", "/mode@"):
        if arg.lower() in ("approve", "auto"):
            update_settings_key("mode", arg.lower())
            send_message(f"⚙️ <b>Posting mode set to: <code>{arg.lower()}</code></b>", chat_id=chat_id)
        else:
            send_message("Usage: <code>/mode approve</code> or <code>/mode auto</code>", chat_id=chat_id)

    elif cmd in ("/stats", "/stats@"):
        stats = get_stats()
        last_7 = stats.get("last_7_days", {})
        vids = last_7.get("total_videos", 0)
        views = last_7.get("total_views", 0)
        likes = last_7.get("total_likes", 0)
        comments = last_7.get("total_comments", 0)

        msg = (
            f"📈 <b>Timereborn 7-Day Performance Stats</b>\n\n"
            f"• <b>Videos Published:</b> {vids}\n"
            f"• <b>Total Views:</b> {views:,}\n"
            f"• <b>Total Likes:</b> {likes:,}\n"
            f"• <b>Total Comments:</b> {comments:,}\n\n"
            f"<i>Keep growing consistently.</i>"
        )
        send_message(msg, chat_id=chat_id)

    elif cmd in ("/idea", "/idea@"):
        if not arg:
            send_message("Usage: <code>/idea &lt;your concept or reference link&gt;</code>", chat_id=chat_id)
            return

        idea = add_user_idea(arg)
        send_message(
            f"💡 <b>Idea Added to Backlog!</b>\n\n"
            f"<b>Title Seed:</b> {idea['title_seed']}\n"
            f"<b>Topic:</b> {idea['topic']}\n"
            f"<b>Opening Hook:</b> <i>\"{idea['hook_seed']}\"</i>",
            chat_id=chat_id,
        )


def poll_telegram_events() -> int:
    """Execute a single polling sweep of Telegram getUpdates."""
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
        u_id = upd.get("update_id", 0)
        if u_id > max_update_id:
            max_update_id = u_id

        # 1. Handle Inline Button Callbacks
        if "callback_query" in upd:
            handle_callback_query(upd["callback_query"])
            handled_count += 1

        # 2. Handle Text Messages and Commands
        elif "message" in upd:
            msg = upd["message"]
            sender_chat = str(msg.get("chat", {}).get("id"))
            text = msg.get("text", "")

            # Only accept commands from configured owner chat ID
            if sender_chat == owner_chat_id and text.startswith("/"):
                handle_command(text, chat_id=sender_chat)
                handled_count += 1

    save_last_offset(max_update_id + 1)
    logger.info(f"Handled {handled_count} Telegram events.")
    return handled_count


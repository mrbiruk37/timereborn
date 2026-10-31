"""Comment processing, Groq sentiment/intent classification, and reply automation."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from src.scriptgen import get_default_model, get_groq_client
from src.state import get_comments, load_settings, save_comments
from src.telegram import answer_callback_query, send_message
from src.youtube import get_authenticated_service

logger = logging.getLogger("timereborn.comments")


class CommentClassification(BaseModel):
    category: str = Field(..., description="One of: question, request, praise, complaint, spam")
    sentiment: str = Field(..., description="One of: positive, neutral, negative")
    is_genuine_engagement: bool = Field(..., description="True if real viewer asking something relevant")
    topic_request: Optional[str] = Field(None, description="Extracted video topic if viewer requested one")
    draft_reply: Optional[str] = Field(None, description="Friendly, helpful reply without links or spam")


def fetch_recent_channel_comments(max_results: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent top-level comments using YouTube Data API v3 commentThreads."""
    try:
        youtube = get_authenticated_service()
        # Fetch comment threads for the authenticated channel's videos
        request = youtube.commentThreads().list(
            part="snippet",
            allThreadsRelatedToChannelId="mine",
            maxResults=max_results,
            order="time",
        )
        response = request.execute()

        comments = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            top_level = snippet.get("topLevelComment", {}).get("snippet", {})
            comment_id = item.get("id")
            comments.append({
                "comment_id": comment_id,
                "video_id": snippet.get("videoId"),
                "author": top_level.get("authorDisplayName", "Anonymous"),
                "text": top_level.get("textDisplay", ""),
                "published_at": top_level.get("publishedAt"),
            })
        return comments
    except HttpError as e:
        logger.warning(f"YouTube Data API error fetching comments: {e}")
        return []
    except Exception as e:
        logger.warning(f"Error fetching comments: {e}")
        return []


def classify_comment_with_groq(comment_text: str, author: str) -> CommentClassification:
    """Use Groq to classify comment intent and draft polite, link-free replies for questions/requests."""
    client = get_groq_client()
    model = get_default_model()

    system_prompt = """You are a respectful community manager for the Timereborn YouTube channel.
Analyze the viewer comment and determine its category and sentiment.

RULES:
1. Category must be one of: question, request, praise, complaint, spam.
2. DRAFT REPLIES ONLY for genuine questions or content requests.
3. NEVER include links or URLs in the reply.
4. Keep the reply friendly, varied in wording, grounded in stoic and thoughtful perspectives, under 30 words.
5. For praise, complaint, or spam: leave draft_reply null or empty.
6. Return strictly valid JSON matching the schema.
"""

    user_prompt = f"""Author: {author}
Comment: "{comment_text}"

Return JSON:
{{
  "category": "question|request|praise|complaint|spam",
  "sentiment": "positive|neutral|negative",
  "is_genuine_engagement": true|false,
  "topic_request": "extracted topic if requested or null",
  "draft_reply": "draft response or null"
}}
"""

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
        data = json.loads(res.choices[0].message.content)
        return CommentClassification(**data)
    except Exception as e:
        logger.warning(f"Groq comment classification failed: {e}")
        return CommentClassification(
            category="praise",
            sentiment="positive",
            is_genuine_engagement=False,
            topic_request=None,
            draft_reply=None,
        )


def post_youtube_reply(comment_id: str, reply_text: str) -> bool:
    """Post an official reply to a YouTube comment thread using YouTube Data API v3."""
    # Hard Rule: Never post links in replies
    if "http://" in reply_text or "https://" in reply_text or "www." in reply_text:
        logger.warning("Blocked reply containing prohibited link.")
        return False

    try:
        youtube = get_authenticated_service()
        youtube.comments().insert(
            part="snippet",
            body={
                "snippet": {
                    "parentId": comment_id,
                    "textOriginal": reply_text.strip(),
                }
            },
        ).execute()
        logger.info(f"Successfully posted reply to comment {comment_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to post YouTube reply: {e}")
        return False


def process_comments_pipeline() -> List[Dict[str, Any]]:
    """Fetch new comments, classify them, enforce daily reply limits, and dispatch/post replies."""
    settings = load_settings()
    mode = settings.get("mode", "approve")
    max_replies_day = settings.get("limits", {}).get("max_comments_replied_per_day", 15)

    stored_comments = get_comments()
    processed_ids = {c["comment_id"] for c in stored_comments if "comment_id" in c}

    # Count replies sent today
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    replies_today = sum(
        1 for c in stored_comments
        if c.get("replied_at", "").startswith(today_str)
    )

    incoming = fetch_recent_channel_comments(max_results=15)
    new_comments_found = []

    for item in incoming:
        cid = item["comment_id"]
        if cid in processed_ids:
            continue

        analysis = classify_comment_with_groq(item["text"], item["author"])
        record = {
            "comment_id": cid,
            "video_id": item.get("video_id"),
            "author": item.get("author"),
            "text": item.get("text"),
            "category": analysis.category,
            "sentiment": analysis.sentiment,
            "topic": analysis.topic_request,
            "draft_reply": analysis.draft_reply,
            "status": "pending_reply" if analysis.draft_reply else "classified",
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Check if we should reply
        if analysis.draft_reply and replies_today < max_replies_day:
            if mode == "auto":
                success = post_youtube_reply(cid, analysis.draft_reply)
                if success:
                    record["status"] = "replied"
                    record["replied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    replies_today += 1
            else:
                # Approve mode: Send draft to Telegram with Approve / Dismiss buttons
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Send Reply", "callback_data": f"reply_approve:{cid}"},
                            {"text": "❌ Dismiss", "callback_data": f"reply_reject:{cid}"},
                        ]
                    ]
                }
                msg_text = (
                    f"💬 <b>Viewer Question on YouTube</b>\n\n"
                    f"<b>From:</b> {item.get('author')}\n"
                    f"<b>Comment:</b> \"{item.get('text')}\"\n\n"
                    f"<b>Drafted Reply:</b>\n<i>\"{analysis.draft_reply}\"</i>\n\n"
                    f"Approve to post this reply on YouTube."
                )
                try:
                    send_message(text=msg_text, reply_markup=keyboard)
                except Exception as e:
                    logger.warning(f"Could not send comment approval to Telegram: {e}")

        stored_comments.append(record)
        new_comments_found.append(record)

    save_comments(stored_comments)
    logger.info(f"Processed {len(new_comments_found)} new comments. Total replies today: {replies_today}/{max_replies_day}")
    return new_comments_found


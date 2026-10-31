"""TikTok uploader and publishing automation module."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("timereborn.tiktok")


def is_tiktok_configured() -> bool:
    """Check if TikTok session credentials are configured."""
    return bool(os.getenv("TIKTOK_SESSION_ID") or os.getenv("TIKTOK_COOKIES_PATH"))


def format_tiktok_caption(title: str, hook: str, hashtags: Optional[List[str]] = None) -> str:
    """Format high-virality TikTok caption template."""
    tags = hashtags or ["#Shorts", "#TimeReborn", "#History", "#AI", "#Future", "#Viral", "#FYP"]
    tag_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tags[:7]])
    
    caption = (
        f"🔥 {title}\n\n"
        f"\"{hook}\"\n\n"
        f"What would happen if they saw our world today? Drop your thoughts below 👇\n\n"
        f"{tag_str}"
    )
    return caption[:2200]  # TikTok caption limit


def post_to_tiktok(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Attempt direct upload to TikTok using session ID or cookies.
    
    If TIKTOK_SESSION_ID is present in environment/secrets, uploads headlessly.
    Otherwise, returns pending status with setup instructions.
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    session_id = os.getenv("TIKTOK_SESSION_ID")
    cookies_path = os.getenv("TIKTOK_COOKIES_PATH")

    if not session_id and not cookies_path:
        logger.info("TIKTOK_SESSION_ID not configured. Direct TikTok headless upload skipped.")
        return {
            "status": "pending_credentials",
            "platform": "tiktok",
            "message": "Set TIKTOK_SESSION_ID in .env or GitHub Secrets for 100% automated posting.",
        }

    try:
        from tiktok_uploader.upload import upload_video
        
        logger.info(f"Attempting headless TikTok upload for '{title}'...")
        # Prepare caption
        caption = description or format_tiktok_caption(title=title, hook="", hashtags=tags)

        kwargs: Dict[str, Any] = {
            "filename": str(video_path),
            "description": caption,
            "headless": True,
        }
        if session_id:
            kwargs["sessionid"] = session_id
        elif cookies_path:
            kwargs["cookies"] = cookies_path

        # upload_video returns list of results
        result = upload_video(**kwargs)
        logger.info(f"TikTok upload completed successfully: {result}")
        return {
            "status": "published",
            "platform": "tiktok",
            "details": str(result),
        }

    except Exception as e:
        logger.error(f"TikTok upload failed: {e}")
        return {
            "status": "failed",
            "platform": "tiktok",
            "error": str(e),
        }

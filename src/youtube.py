"""Official YouTube Data API v3 client for upload, status management, and metadata."""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

load_dotenv()
logger = logging.getLogger("timereborn.youtube")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_authenticated_service() -> Resource:
    """Build authenticated YouTube service from environment credentials."""
    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    refresh_token = os.getenv("YT_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        raise ValueError(
            "Missing YouTube credentials. Please set YT_CLIENT_ID, YT_CLIENT_SECRET, "
            "and YT_REFRESH_TOKEN in your environment or .env file."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    category_id: str = "27",  # 27 = Education, 22 = People & Blogs
    privacy_status: str = "private",
    max_retries: int = 5,
) -> Dict[str, Any]:
    """Perform resumable video upload using official YouTube Data API v3.
    
    Hard Rules:
    - Never hardcode secrets.
    - Disclose AI-generated content in metadata and description.
    - Free-tier safety: Resumable chunking and exponential backoff retry.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    # Ensure disclosure line is present in description
    ai_disclosure = "Created with AI assistance (script generation & voiceover)."
    if ai_disclosure not in description:
        description = f"{description.strip()}\n\n---\n{ai_disclosure}"

    # YouTube limits title to 100 chars
    clean_title = title[:100].strip()

    body = {
        "snippet": {
            "title": clean_title,
            "description": description,
            "tags": tags or ["Shorts", "Stoicism", "Wisdom"],
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    youtube = get_authenticated_service()
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=1024 * 1024 * 2,  # 2MB chunks for safe free-tier uploads
        resumable=True,
    )

    logger.info(f"Initiating resumable upload for '{clean_title}' (Privacy: {privacy_status})...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry_delay = 1.0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload progress: {progress}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504, 429] and max_retries > 0:
                logger.warning(f"HTTP {e.resp.status} during upload. Retrying in {retry_delay:.1f}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
                max_retries -= 1
            else:
                logger.error(f"Fatal YouTube API HttpError: {e}")
                raise
        except Exception as e:
            if max_retries > 0:
                logger.warning(f"Network error during upload: {e}. Retrying in {retry_delay:.1f}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
                max_retries -= 1
            else:
                raise

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    actual_privacy = response.get("status", {}).get("privacyStatus", privacy_status)
    logger.info(f"Upload complete! Video ID: {video_id} ({video_url}) [Privacy: {actual_privacy}]")

    # If YouTube forced upload to private due to unverified API project, notify once
    if privacy_status == "public" and actual_privacy == "private":
        try:
            from src.state import load_settings, save_settings
            from src.telegram import send_message
            settings = load_settings()
            if not settings.get("youtube_audit_notified"):
                settings["youtube_audit_notified"] = True
                save_settings(settings)
                send_message("YouTube API project in testing mode. Uploads restricted to private until audited in Google Cloud Console.")
        except Exception as e:
            logger.warning(f"Could not check/send audit notification: {e}")

    return {
        "video_id": video_id,
        "video_url": video_url,
        "title": clean_title,
        "privacy_status": actual_privacy,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def update_video_privacy(video_id: str, privacy_status: str) -> Dict[str, Any]:
    """Update privacy status of an uploaded video (e.g. 'private' to 'public')."""
    youtube = get_authenticated_service()
    logger.info(f"Updating video {video_id} privacy to: {privacy_status}")

    request = youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        },
    )
    res = request.execute()
    return res


def delete_video(video_id: str) -> None:
    """Delete an uploaded video (used when rejected in approve mode)."""
    youtube = get_authenticated_service()
    logger.info(f"Deleting video {video_id}...")
    youtube.videos().delete(id=video_id).execute()


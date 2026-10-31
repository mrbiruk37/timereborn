"""Performance analytics collector for 24h and 72h milestones."""

import datetime
import logging
import time
from typing import Any, Dict, List, Optional
from googleapiclient.errors import HttpError

from src.state import get_posts, get_stats, save_posts, save_stats
from src.youtube import get_authenticated_service

logger = logging.getLogger("timereborn.analytics")


def parse_iso_datetime(dt_str: str) -> Optional[datetime.datetime]:
    """Safely parse ISO datetime string."""
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(dt_str)
    except Exception:
        return None


def fetch_video_metrics(video_id: str) -> Optional[Dict[str, Any]]:
    """Fetch live statistics from YouTube Data API v3."""
    try:
        youtube = get_authenticated_service()
        resp = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            logger.warning(f"No video found on YouTube for ID: {video_id}")
            return None

        stats = items[0].get("statistics", {})
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except HttpError as e:
        logger.warning(f"YouTube API HttpError fetching stats for {video_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching stats for {video_id}: {e}")
        return None


def collect_milestone_analytics() -> Dict[str, Any]:
    """Scan posts.json, fetch 24h and 72h stats, and update metrics."""
    posts = get_posts()
    now = datetime.datetime.now(datetime.timezone.utc)
    updated_count = 0

    logger.info(f"Checking milestone analytics for {len(posts)} recorded posts...")

    for post in posts:
        yt_id = post.get("youtube_id")
        created_str = post.get("created_at")
        if not yt_id or not created_str:
            continue

        created_dt = parse_iso_datetime(created_str)
        if not created_dt:
            continue

        age_hours = (now - created_dt).total_seconds() / 3600.0
        metrics = post.setdefault("metrics", {})

        # Check 24h milestone (between 24h and 48h, if not recorded yet)
        if age_hours >= 24 and "24h" not in metrics:
            logger.info(f"Collecting 24h metrics for '{post.get('title')}' ({yt_id})...")
            m_data = fetch_video_metrics(yt_id)
            if m_data:
                metrics["24h"] = m_data
                updated_count += 1

        # Check 72h milestone (between 72h and 96h, if not recorded yet)
        if age_hours >= 72 and "72h" not in metrics:
            logger.info(f"Collecting 72h metrics for '{post.get('title')}' ({yt_id})...")
            m_data = fetch_video_metrics(yt_id)
            if m_data:
                metrics["72h"] = m_data
                updated_count += 1

    if updated_count > 0:
        save_posts(posts)
        logger.info(f"Updated milestone metrics for {updated_count} post milestones.")

    # Build and update stats snapshot
    stats_snapshot = build_stats_snapshot(posts)
    save_stats(stats_snapshot)
    return stats_snapshot


def build_stats_snapshot(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate overall 7-day performance snapshot for Telegram /stats command."""
    now = datetime.datetime.now(datetime.timezone.utc)
    seven_days_ago = now - datetime.timedelta(days=7)

    recent_posts = []
    total_views = 0
    total_likes = 0
    total_comments = 0

    for p in posts:
        c_dt = parse_iso_datetime(p.get("created_at", ""))
        if c_dt and c_dt >= seven_days_ago:
            metrics = p.get("metrics", {})
            latest_m = metrics.get("72h") or metrics.get("24h") or {}
            v = latest_m.get("views", 0)
            l = latest_m.get("likes", 0)
            c = latest_m.get("comments", 0)

            total_views += v
            total_likes += l
            total_comments += c
            recent_posts.append({
                "title": p.get("title"),
                "views": v,
                "likes": l,
            })

    return {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_7_days": {
            "total_videos": len(recent_posts),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "recent_posts": recent_posts[-5:],
        },
    }

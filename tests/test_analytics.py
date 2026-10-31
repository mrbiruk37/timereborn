"""Unit tests for analytics.py metrics collection."""

from unittest.mock import MagicMock, patch
import datetime
from src.analytics import (
    parse_iso_datetime,
    build_stats_snapshot,
    collect_milestone_analytics,
)


def test_parse_iso_datetime():
    dt = parse_iso_datetime("2026-10-31T12:00:00Z")
    assert dt is not None
    assert dt.hour == 12


def test_build_stats_snapshot():
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    posts = [
        {
            "title": "Video 1",
            "created_at": now_str,
            "metrics": {"24h": {"views": 1500, "likes": 200, "comments": 25}},
        },
        {
            "title": "Video 2",
            "created_at": now_str,
            "metrics": {"72h": {"views": 3000, "likes": 400, "comments": 50}},
        },
    ]

    snapshot = build_stats_snapshot(posts)
    last_7 = snapshot["last_7_days"]
    assert last_7["total_videos"] == 2
    assert last_7["total_views"] == 4500
    assert last_7["total_likes"] == 600
    assert last_7["total_comments"] == 75


@patch("src.analytics.fetch_video_metrics")
@patch("src.analytics.get_posts")
@patch("src.analytics.save_posts")
@patch("src.analytics.save_stats")
def test_collect_milestone_analytics(mock_save_stats, mock_save_posts, mock_get_posts, mock_fetch):
    # Video published 28 hours ago
    created = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=28)).isoformat()
    mock_get_posts.return_value = [
        {
            "youtube_id": "yt_100",
            "title": "History Reborn Episode",
            "created_at": created,
            "metrics": {},
        }
    ]
    mock_fetch.return_value = {"views": 1200, "likes": 150, "comments": 12}

    collect_milestone_analytics()
    assert mock_fetch.called
    assert mock_save_posts.called
    assert mock_save_stats.called


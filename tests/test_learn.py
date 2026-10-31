"""Unit tests for learn.py performance scoring and loop updates."""

from unittest.mock import MagicMock, patch
from src.learn import (
    compute_post_score,
    run_learning_loop,
    send_daily_summary,
)


def test_compute_post_score():
    post = {
        "metrics": {
            "24h": {"views": 1000, "likes": 50, "comments": 10}
        }
    }
    # 1000 + (50 * 4) + (10 * 8) = 1000 + 200 + 80 = 1280
    assert compute_post_score(post) == 1280.0


@patch("src.learn.get_posts")
@patch("src.learn.get_comments")
@patch("src.learn.save_learning")
@patch("src.learn.generate_llm_insights", return_value=["Focus on high retention pacing."])
def test_run_learning_loop(mock_insights, mock_save, mock_comments, mock_posts):
    mock_posts.return_value = [
        {
            "title": "Stoic Morning Rule",
            "hook": "Do this every morning.",
            "duration_seconds": 32,
            "metrics": {"24h": {"views": 5000, "likes": 500, "comments": 50}},
        }
    ]
    mock_comments.return_value = []

    res = run_learning_loop()
    assert len(res["top_videos"]) == 1
    assert "Do this every morning." in res["winning_hooks"]
    assert mock_save.called


@patch("src.learn.send_message")
@patch("src.learn.get_learning")
@patch("src.learn.get_posts")
def test_send_daily_summary(mock_posts, mock_learning, mock_send_msg):
    mock_learning.return_value = {
        "top_videos": [{"title": "Winning Video"}],
        "best_lengths_sec": {"short": [25, 40]},
        "key_insights": ["Keep intros under 2 seconds"],
    }
    mock_posts.return_value = [{"title": "Post 1"}]

    send_daily_summary()
    assert mock_send_msg.called
    text = mock_send_msg.call_args[1]["text"]
    assert "Timereborn Daily Report" in text
    assert "Winning Video" in text


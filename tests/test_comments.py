"""Unit tests for comments.py classification and auto-replies."""

import json
from unittest.mock import MagicMock, patch
from src.comments import (
    CommentClassification,
    classify_comment_with_groq,
    post_youtube_reply,
)


def test_comment_classification_schema():
    data = {
        "category": "question",
        "sentiment": "positive",
        "is_genuine_engagement": True,
        "topic_request": "How to start journaling",
        "draft_reply": "Start with 3 things you are grateful for each morning.",
    }
    model = CommentClassification(**data)
    assert model.category == "question"
    assert model.draft_reply is not None


def test_post_youtube_reply_blocks_links():
    # Hard Rule: Never post links in replies
    assert post_youtube_reply("c123", "Check out https://mysite.com for more!") is False
    assert post_youtube_reply("c123", "Visit www.example.com") is False


@patch("src.comments.get_groq_client")
def test_classify_comment_mocked(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "category": "question",
            "sentiment": "neutral",
            "is_genuine_engagement": True,
            "topic_request": "Stoic books",
            "draft_reply": "Meditations by Marcus Aurelius is the best place to start."
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    res = classify_comment_with_groq("Which stoic book should I read first?", author="Alex")
    assert res.category == "question"
    assert "Meditations" in res.draft_reply


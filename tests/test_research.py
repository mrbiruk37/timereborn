"""Unit tests for research.py concept analysis and synthesis."""

import json
from unittest.mock import MagicMock, patch
from src.research import synthesize_ideas_from_research


def test_synthesize_ideas_fallback():
    # Empty videos should return valid fallback seeds
    ideas = synthesize_ideas_from_research([])
    assert len(ideas) >= 1
    assert "topic" in ideas[0]
    assert ideas[0]["proven_score"] > 0


@patch("src.research.get_groq_client")
def test_synthesize_ideas_mocked(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "ideas": [
                {
                    "title_seed": "The Daily Stoic Rule",
                    "topic": "Stoic discipline in the morning",
                    "hook_seed": "Marcus Aurelius never hit snooze.",
                    "proven_score": 0.88
                }
            ]
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    sample_videos = [
        {"title": "How to Be Disciplined", "views": 100000, "likes": 5000}
    ]
    ideas = synthesize_ideas_from_research(sample_videos)
    assert len(ideas) == 1
    assert ideas[0]["title_seed"] == "The Daily Stoic Rule"
    assert ideas[0]["proven_score"] == 0.88

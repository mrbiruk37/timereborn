"""Unit tests for ideas.py deduplication and 70/30 selection."""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.ideas import (
    normalize_text,
    is_duplicate,
    deduplicate_ideas,
    select_next_idea,
    add_user_idea,
)


def test_normalize_text():
    assert normalize_text("The 2,000-Year-Old Stoic Secret!") == "the 2000yearold stoic secret"


def test_is_duplicate():
    existing = ["Marcus Aurelius Morning Habit", "Stoic Secrets To Overcoming Anxiety"]
    assert is_duplicate("Marcus Aurelius Morning Habit", existing) is True
    assert is_duplicate("Completely Different Video Concept", existing) is False


@patch("src.ideas.get_posts", return_value=[{"title": "The Art of Stoic Focus"}])
@patch("src.ideas.get_ideas", return_value=[{"title_seed": "How Marcus Aurelius Journaled"}])
def test_deduplicate_ideas(mock_get_ideas, mock_get_posts):
    candidates = [
        {"title_seed": "The Art of Stoic Focus"},  # duplicate
        {"title_seed": "Why Epictetus Never Complained"},  # unique
    ]
    unique = deduplicate_ideas(candidates)
    assert len(unique) == 1
    assert unique[0]["title_seed"] == "Why Epictetus Never Complained"


@patch("src.ideas.get_ideas")
@patch("src.ideas.save_ideas")
def test_select_next_idea(mock_save_ideas, mock_get_ideas):
    mock_get_ideas.return_value = [
        {"id": "idea_1", "title_seed": "Idea 1", "proven_score": 0.95, "hook_seed": "Hook 1"},
        {"id": "idea_2", "title_seed": "Idea 2", "proven_score": 0.50, "hook_seed": "Hook 2"},
    ]
    selected = select_next_idea()
    assert selected["id"] in ("idea_1", "idea_2")
    assert mock_save_ideas.called


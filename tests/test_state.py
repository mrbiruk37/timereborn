"""Unit tests for state.py atomic reads, writes, and defaults."""

import json
from pathlib import Path
import pytest
from src.state import (
    load_json,
    save_json,
    load_settings,
    get_learning,
    save_learning,
    get_posts,
    add_post,
)


def test_atomic_save_and_load(tmp_path: Path):
    test_file = tmp_path / "test_data.json"
    data = {"sample_key": "sample_val", "numbers": [1, 2, 3]}

    save_json(test_file, data)
    assert test_file.exists()

    loaded = load_json(test_file)
    assert loaded == data


def test_corrupt_json_fallback(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{invalid json format: missing quotes")

    result = load_json(corrupt_file, default_factory=list)
    assert result == []


def test_settings_loader():
    settings = load_settings()
    assert isinstance(settings, dict)
    assert "niche" in settings
    assert "mode" in settings


def test_learning_defaults():
    learning = get_learning()
    assert isinstance(learning, dict)
    assert "winning_hooks" in learning
    assert "best_lengths_sec" in learning


def test_add_post(tmp_path: Path, monkeypatch):
    test_posts_file = tmp_path / "posts.json"
    import src.state as state_mod
    monkeypatch.setattr(state_mod, "POSTS_FILE", test_posts_file)

    post_entry = {
        "id": "post_123",
        "title": "Stoic Secret",
        "status": "uploaded",
    }
    state_mod.add_post(post_entry)

    posts = state_mod.get_posts()
    assert len(posts) == 1
    assert posts[0]["id"] == "post_123"


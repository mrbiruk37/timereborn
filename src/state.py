"""Safe state management for data files and settings."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import yaml

logger = logging.getLogger("timereborn.state")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

IDEAS_FILE = DATA_DIR / "ideas.json"
POSTS_FILE = DATA_DIR / "posts.json"
STATS_FILE = DATA_DIR / "stats.json"
COMMENTS_FILE = DATA_DIR / "comments.json"
LEARNING_FILE = DATA_DIR / "learning.json"
SETTINGS_FILE = CONFIG_DIR / "settings.yml"
SOURCES_FILE = CONFIG_DIR / "sources.yml"


def ensure_data_dirs() -> None:
    """Ensure data and config directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default_factory: Optional[Callable[[], Any]] = None) -> Any:
    """Safely load JSON from file with atomic read and fallback."""
    ensure_data_dirs()
    if not path.exists():
        default_val = default_factory() if default_factory else []
        save_json(path, default_val)
        return default_val

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON file {path}: {e}. Returning default.")
        return default_factory() if default_factory else []
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
        return default_factory() if default_factory else []


def save_json(path: Path, data: Any) -> None:
    """Safely and atomically save JSON data to disk using temporary file replacement."""
    ensure_data_dirs()
    dir_name = path.parent
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            temp_file = tf.name

        # On Windows, replace requires the destination to be replaced safely
        if os.path.exists(path):
            os.replace(temp_file, path)
        else:
            os.rename(temp_file, path)
    except Exception as e:
        logger.error(f"Failed to safely write JSON to {path}: {e}")
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass
        raise


def load_settings() -> Dict[str, Any]:
    """Load settings from config/settings.yml with sensible defaults."""
    if not SETTINGS_FILE.exists():
        logger.warning(f"Settings file not found at {SETTINGS_FILE}, using defaults.")
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data or {}
    except Exception as e:
        logger.error(f"Failed to load settings from {SETTINGS_FILE}: {e}")
        return {}


def load_sources() -> Dict[str, Any]:
    """Load source channels from config/sources.yml."""
    if not SOURCES_FILE.exists():
        return {"channels": []}
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data or {"channels": []}
    except Exception as e:
        logger.error(f"Failed to load sources from {SOURCES_FILE}: {e}")
        return {"channels": []}


def get_ideas() -> List[Dict[str, Any]]:
    """Retrieve all pending ideas."""
    return load_json(IDEAS_FILE, list)


def save_ideas(ideas: List[Dict[str, Any]]) -> None:
    """Persist the ideas list."""
    save_json(IDEAS_FILE, ideas)


def get_posts() -> List[Dict[str, Any]]:
    """Retrieve all recorded posts."""
    return load_json(POSTS_FILE, list)


def add_post(post_record: Dict[str, Any]) -> None:
    """Append a newly created/uploaded post to posts.json."""
    posts = get_posts()
    posts.append(post_record)
    save_json(POSTS_FILE, posts)


def save_posts(posts: List[Dict[str, Any]]) -> None:
    """Persist all posts."""
    save_json(POSTS_FILE, posts)


def get_stats() -> Dict[str, Any]:
    """Retrieve analytics stats snapshot."""
    return load_json(STATS_FILE, dict)


def save_stats(stats: Dict[str, Any]) -> None:
    """Persist analytics stats."""
    save_json(STATS_FILE, stats)


def get_comments() -> List[Dict[str, Any]]:
    """Retrieve processed comments."""
    return load_json(COMMENTS_FILE, list)


def save_comments(comments: List[Dict[str, Any]]) -> None:
    """Persist comments."""
    save_json(COMMENTS_FILE, comments)


def get_learning() -> Dict[str, Any]:
    """Retrieve the learning loop insights."""
    default_learning = {
        "last_updated": None,
        "top_videos": [],
        "bottom_videos": [],
        "winning_hooks": [],
        "losing_hooks": [],
        "best_lengths_sec": {"short": [25, 45], "long": [300, 480]},
        "best_posting_times_utc": ["13:00", "17:00", "22:00"],
        "requested_topics": [],
        "key_insights": [],
    }
    return load_json(LEARNING_FILE, lambda: default_learning)


def save_learning(learning: Dict[str, Any]) -> None:
    """Persist the learning loop insights."""
    save_json(LEARNING_FILE, learning)

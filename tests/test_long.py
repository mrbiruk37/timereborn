"""Unit tests for long-form video script generation and chapter structures."""

import json
from unittest.mock import MagicMock, patch
from src.scriptgen import ChapterScript, LongScriptResponse, generate_long_script


def test_long_script_response_schema():
    data = {
        "title_options": ["The Complete Stoic Guide", "Master Your Mind", "Roman Stoicism"],
        "hook": "For two thousand years, emperors and slaves practiced one secret.",
        "chapters": [
            {
                "title": "Chapter 1: The Core Principle",
                "script": "Some things are in our control and others not.",
                "scene_keywords": ["ancient rome", "statue"]
            },
            {
                "title": "Chapter 2: The Practical Daily Exercise",
                "script": "Every morning anticipate the difficult interactions.",
                "scene_keywords": ["sunrise", "journal"]
            },
            {
                "title": "Chapter 3: The Unconquerable Citadel",
                "script": "Protect your inner peace above all external goods.",
                "scene_keywords": ["citadel", "mountain"]
            }
        ],
        "description": "Full documentary on Stoic Philosophy. Created with AI assistance (script generation & voiceover).",
        "tags": ["stoicism", "documentary", "philosophy"]
    }

    parsed = LongScriptResponse(**data)
    assert len(parsed.title_options) == 3
    assert len(parsed.chapters) == 3
    assert "two thousand years" in parsed.hook


@patch("src.scriptgen.get_groq_client")
def test_generate_long_script_mocked(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "title_options": ["Marcus Aurelius Documentary"],
            "hook": "Why did the most powerful man in the world write to himself in secret?",
            "chapters": [
                {
                    "title": "Chapter 1: The Philosopher King",
                    "script": "Marcus Aurelius ruled an empire of millions.",
                    "scene_keywords": ["ancient empire", "emperor"]
                },
                {
                    "title": "Chapter 2: The Private Journal",
                    "script": "He never intended Meditations to be published.",
                    "scene_keywords": ["ancient scroll", "candlelight"]
                },
                {
                    "title": "Chapter 3: The Lesson For Today",
                    "script": "True sovereignty begins with mastery over your own mind.",
                    "scene_keywords": ["mountain view", "calm ocean"]
                }
            ],
            "description": "Documentary on Marcus Aurelius. Created with AI assistance (script generation & voiceover).",
            "tags": ["documentary", "stoicism"]
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = generate_long_script(topic="Marcus Aurelius Life")
    assert result.title_options[0] == "Marcus Aurelius Documentary"
    assert len(result.chapters) == 3
    assert "most powerful man" in result.hook

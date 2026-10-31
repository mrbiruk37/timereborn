"""Unit tests for scriptgen.py Pydantic models and LLM response parsing."""

import json
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from src.scriptgen import ShortScriptResponse, generate_short_script


def test_short_script_response_valid():
    sample_data = {
        "title_options": [
            "The 2000-Year-Old Stoic Secret",
            "Why Marcus Aurelius Wrote To Himself",
            "The Daily Rule That Stops Anxiety"
        ],
        "hook": "You are suffering more in imagination than in reality.",
        "script": "Marcus Aurelius reminded himself daily that other people's opinions cannot touch your inner peace. Focus exclusively on what is within your direct control today, and disregard the rest.",
        "scene_keywords": ["ancient rome", "stoic statue", "writing journal", "deep focus", "inner peace"],
        "description": "Discover the timeless Stoic lesson on mental resilience. Created with AI assistance (script & voiceover). #Shorts #Stoicism",
        "tags": ["stoicism", "mindset", "wisdom"],
        "hashtags": ["#Shorts", "#Stoicism", "#Philosophy"]
    }

    parsed = ShortScriptResponse(**sample_data)
    assert len(parsed.title_options) == 3
    assert "suffering" in parsed.hook
    assert len(parsed.scene_keywords) == 5


def test_short_script_response_missing_hook():
    invalid_data = {
        "title_options": ["Title 1"],
        # Missing hook
        "script": "Some script text here.",
        "scene_keywords": ["keyword1", "keyword2", "keyword3"],
        "description": "Description",
    }
    with pytest.raises(ValidationError):
        ShortScriptResponse(**invalid_data)


def test_short_script_response_empty_titles():
    invalid_data = {
        "title_options": [], # Min length is 1
        "hook": "Hook text",
        "script": "Some script text here.",
        "scene_keywords": ["keyword1", "keyword2", "keyword3"],
        "description": "Description",
    }
    with pytest.raises(ValidationError):
        ShortScriptResponse(**invalid_data)


@patch("src.scriptgen.get_groq_client")
def test_generate_short_script_mocked(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "title_options": ["Control What You Can"],
            "hook": "Stop wasting energy on things you cannot change.",
            "script": "Epictetus taught that serenity begins the moment you accept what you cannot control.",
            "scene_keywords": ["ancient library", "calm ocean", "statue"],
            "description": "Stoic wisdom. Created with AI assistance (script & voiceover).",
            "tags": ["stoic"],
            "hashtags": ["#Shorts"]
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = generate_short_script(topic="Control")
    assert result.title_options[0] == "Control What You Can"
    assert "Stop wasting" in result.hook
    assert len(result.scene_keywords) == 3

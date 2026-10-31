"""Script generator using Groq API and structured JSON validation."""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import groq
from dotenv import load_dotenv

from src.state import get_learning, load_settings

load_dotenv()
logger = logging.getLogger("timereborn.scriptgen")


class ShortScriptResponse(BaseModel):
    title_options: List[str] = Field(..., min_length=1, max_length=5, description="3 high-CTR title options")
    hook: str = Field(..., description="Opening punchy hook line for the first 2 seconds")
    script: str = Field(..., description="Full spoken narration script without stage directions or brackets")
    scene_keywords: List[str] = Field(..., min_length=3, max_length=10, description="Visual search keywords for each scene")
    description: str = Field(..., description="YouTube video description including AI disclosure")
    tags: List[str] = Field(default_factory=list, description="YouTube search tags")
    hashtags: List[str] = Field(default_factory=list, description="Trending hashtags including #Shorts")


class ChapterScript(BaseModel):
    title: str = Field(..., description="Chapter title (e.g. 'Chapter 1: The Dichotomy of Control')")
    script: str = Field(..., description="Narration text for this section (~120-180 words)")
    scene_keywords: List[str] = Field(..., min_length=2, max_length=6, description="Visual keywords for this chapter")


class LongScriptResponse(BaseModel):
    title_options: List[str] = Field(..., min_length=1, max_length=5, description="3 high-CTR long-form title options")
    hook: str = Field(..., description="Opening hook narrative for first 15 seconds")
    chapters: List[ChapterScript] = Field(..., min_length=3, max_length=7, description="Structured chapters for 5-8 min video")
    description: str = Field(..., description="Full YouTube description with chapters/timestamps and AI disclosure")
    tags: List[str] = Field(default_factory=list, description="YouTube search tags")


def get_groq_client() -> groq.Groq:
    """Initialize Groq client from environment."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is required.")
    return groq.Groq(api_key=api_key)


def get_default_model() -> str:
    """Get Groq model from environment or settings with safe fallbacks."""
    env_model = os.getenv("GROQ_MODEL")
    if env_model:
        return env_model
    settings = load_settings()
    return settings.get("llm", {}).get("model", "openai/gpt-oss-120b")


def generate_short_script(topic: str, context: Optional[str] = None) -> ShortScriptResponse:
    """Generate an original short video script using Groq and validate with Pydantic."""
    client = get_groq_client()
    model = get_default_model()
    settings = load_settings()
    learning = get_learning()

    niche = settings.get("niche", "Stoic wisdom, timeless perspectives, history and productivity")
    winning_hooks = learning.get("winning_hooks", [])
    key_insights = learning.get("key_insights", [])

    system_prompt = f"""You are an elite YouTube Shorts and TikTok scriptwriter specializing in {niche}.
Your goal is to write captivating, viral, and 100% original vertical video scripts.

HARD RULES:
1. ORIGINALITY: Never copy existing text or scripts. Write completely fresh, compelling narration.
2. DURATION: The narration MUST be between 65 and 105 words (aiming for 25-45 seconds when spoken at normal pace).
3. STRUCTURE:
   - Hook (first 2 seconds): A pattern interrupt or curiosity-gap question that stops the scroll immediately.
   - Core insight: A sharp, insightful philosophical or practical lesson. No fluff or generic filler.
   - Loop ending: End with a concluding thought that seamlessly loops back to the start.
4. FORMAT: Narration script MUST contain ONLY words to be spoken aloud. NO stage directions, NO asterisks, NO speaker labels.
5. DISCLOSURE: YouTube requires disclosing AI-generated content. In the description, include: 'Created with AI assistance (script & voiceover).'
6. OUTPUT: Return strictly valid JSON adhering to the specified schema.
"""

    user_prompt = f"""Topic: {topic}
{"Additional context/idea: " + context if context else ""}

LEARNING INSIGHTS FROM PAST TOP PERFORMERS:
- Winning hook patterns: {winning_hooks[:3] if winning_hooks else "Bold questions, counter-intuitive truths, historical quotes"}
- Strategic notes: {key_insights[:3] if key_insights else "High retention pacing, direct emotional resonance"}

Generate a JSON object with:
{{
  "title_options": ["Title 1", "Title 2", "Title 3"],
  "hook": "Opening 2-second hook line",
  "script": "Full narration text to speak (65-105 words, no stage directions)",
  "scene_keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"],
  "description": "Engaging description with summary, takeaways, hashtags, and AI disclosure",
  "tags": ["stoicism", "mindset", "wisdom", "focus", "history"],
  "hashtags": ["#Shorts", "#Stoicism", "#Wisdom", "#Philosophy"]
}}
"""

    logger.info(f"Generating Short script for topic: '{topic}' using model {model}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("Groq returned an empty response.")

    try:
        data = json.loads(content)
        parsed = ShortScriptResponse(**data)
        logger.info(f"Successfully generated script with hook: '{parsed.hook}'")
        return parsed
    except Exception as e:
        logger.error(f"Failed to validate script JSON: {e}\nRaw content: {content}")
        raise ValueError(f"Invalid script generated by LLM: {e}") from e


def generate_long_script(topic: str, context: Optional[str] = None) -> LongScriptResponse:
    """Generate an original structured long-form video script (5-8 minutes) in chapters."""
    client = get_groq_client()
    model = get_default_model()
    settings = load_settings()
    learning = get_learning()

    niche = settings.get("niche", "Stoic wisdom, timeless perspectives, history and productivity")

    system_prompt = f"""You are a master essayist and documentary scriptwriter specializing in {niche}.
Write an engaging, deep, 5 to 8 minute long-form YouTube documentary script structured cleanly in chapters.

HARD RULES:
1. ORIGINALITY: 100% original prose, historical anecdotes, and philosophical analysis.
2. LENGTH: 4 to 5 chapters totaling approximately 650 to 950 words (5-7 minutes spoken duration).
3. FORMAT: Each chapter must contain only spoken narration without bracketed stage directions.
4. DISCLOSURE: In the description, include: 'Created with AI assistance (script generation & voiceover).'
5. OUTPUT: Return strictly valid JSON adhering to the LongScriptResponse schema.
"""

    user_prompt = f"""Topic: {topic}
{"Additional context: " + context if context else ""}

Generate a JSON object with:
{{
  "title_options": ["Engaging Document Title 1", "Title 2", "Title 3"],
  "hook": "Compelling 15-second opening question or paradox",
  "chapters": [
    {{
      "title": "Introduction: The Hidden Struggle",
      "script": "Spoken narration for intro...",
      "scene_keywords": ["ancient city", "night reflection", "deep thought"]
    }},
    {{
      "title": "Chapter 1: The Core Principle",
      "script": "Spoken narration for chapter 1...",
      "scene_keywords": ["philosophy books", "meditation statue", "mountain peak"]
    }},
    {{
      "title": "Chapter 2: The Historical Lesson",
      "script": "Spoken narration for chapter 2...",
      "scene_keywords": ["ancient rome", "stoic writings", "historical landscape"]
    }},
    {{
      "title": "Chapter 3: Practical Modern Application",
      "script": "Spoken narration for chapter 3...",
      "scene_keywords": ["modern city", "focused worker", "calm mind"]
    }},
    {{
      "title": "Conclusion: The Unconquerable Mind",
      "script": "Spoken narration for conclusion...",
      "scene_keywords": ["ocean horizon", "sunrise landscape"]
    }}
  ],
  "description": "Full documentary description with chapter timestamps and AI disclosure.",
  "tags": ["documentary", "stoicism", "philosophy", "history", "mindset", "productivity"]
}}
"""

    logger.info(f"Generating Long script for topic: '{topic}' using model {model}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
        parsed = LongScriptResponse(**data)
        logger.info(f"Successfully generated long script with {len(parsed.chapters)} chapters.")
        return parsed
    except Exception as e:
        logger.error(f"Failed to validate long script JSON: {e}\nRaw content: {content}")
        raise ValueError(f"Invalid long script generated: {e}") from e

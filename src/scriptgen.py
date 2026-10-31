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


def get_groq_client() -> groq.Groq:
    """Initialize Groq client from environment."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is required.")
    return groq.Groq(api_key=api_key)


def get_default_model() -> str:
    """Get Groq model from environment or settings."""
    env_model = os.getenv("GROQ_MODEL")
    if env_model:
        return env_model
    settings = load_settings()
    return settings.get("llm", {}).get("model", "llama-3.3-70b-versatile")


def generate_short_script(topic: str, context: Optional[str] = None) -> ShortScriptResponse:
    """Generate an original short video script using Groq and validate with Pydantic.
    
    Hard Rule: Every script must be 100% original. Never reuse third-party transcripts.
    Shorts duration: 25 to 45 seconds (approx. 65-110 spoken words).
    """
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


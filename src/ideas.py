"""Ideas management, deduplication against past posts, and 70/30 selection policy."""

import logging
import random
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from src.research import run_research
from src.scriptgen import get_default_model, get_groq_client
from src.state import get_ideas, get_learning, get_posts, save_ideas

logger = logging.getLogger("timereborn.ideas")


def normalize_text(text: str) -> str:
    """Normalize text for basic deduplication and comparison."""
    clean = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(clean.split())


def is_duplicate(candidate_title: str, existing_titles: List[str], threshold: float = 0.7) -> bool:
    """Check if candidate title is too similar to any existing or past titles."""
    cand_words = set(normalize_text(candidate_title).split())
    if not cand_words:
        return False

    for exist in existing_titles:
        exist_words = set(normalize_text(exist).split())
        if not exist_words:
            continue
        intersection = cand_words.intersection(exist_words)
        union = cand_words.union(exist_words)
        jaccard = len(intersection) / len(union)
        if jaccard >= threshold:
            return True

    return False


def deduplicate_ideas(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate candidates against posts.json and current ideas queue."""
    posts = get_posts()
    past_titles = [p.get("title", "") for p in posts]
    current_ideas = get_ideas()
    queued_titles = [i.get("title_seed", "") for i in current_ideas]

    all_existing = past_titles + queued_titles
    unique_candidates = []

    for item in candidates:
        title = item.get("title_seed", "")
        if not is_duplicate(title, all_existing):
            unique_candidates.append(item)
            all_existing.append(title)
        else:
            logger.info(f"Skipping duplicate idea candidate: '{title}'")

    return unique_candidates


def add_user_idea(raw_text: str) -> Dict[str, Any]:
    """Parse raw text or link submitted via Telegram /idea into a structured candidate."""
    client = get_groq_client()
    model = get_default_model()

    prompt = f"""The creator submitted this raw video idea or inspiration link via Telegram:
"{raw_text}"

Convert this into a structured, high-potential YouTube Shorts idea.
Return strictly valid JSON:
{{
  "title_seed": "Punchy working title",
  "topic": "Core topic/lesson",
  "hook_seed": "First 2-second hook line to grab attention",
  "proven_score": 0.90
}}
"""
    try:
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        import json
        data = json.loads(res.choices[0].message.content)
        idea = {
            "id": str(uuid.uuid4())[:8],
            "title_seed": data.get("title_seed", raw_text[:40]),
            "topic": data.get("topic", raw_text),
            "hook_seed": data.get("hook_seed", "Wait until you hear this."),
            "source": "telegram_user",
            "proven_score": float(data.get("proven_score", 0.9)),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception as e:
        logger.warning(f"Could not parse user idea with LLM, using fallback: {e}")
        idea = {
            "id": str(uuid.uuid4())[:8],
            "title_seed": raw_text[:50],
            "topic": raw_text,
            "hook_seed": "Here is what no one told you.",
            "source": "telegram_user",
            "proven_score": 0.8,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    ideas = get_ideas()
    ideas.append(idea)
    save_ideas(ideas)
    logger.info(f"User idea added to backlog: '{idea['title_seed']}'")
    return idea


def replenish_ideas() -> None:
    """Run research and populate ideas backlog if low."""
    candidates = run_research()
    unique = deduplicate_ideas(candidates)
    if unique:
        current = get_ideas()
        current.extend(unique)
        save_ideas(current)
        logger.info(f"Replenished backlog with {len(unique)} new unique ideas.")


def select_next_idea() -> Dict[str, Any]:
    """Select next idea using 70% proven patterns / 30% experimental distribution."""
    ideas = get_ideas()

    # Replenish if backlog is empty or low (< 2 items)
    if len(ideas) < 2:
        replenish_ideas()
        ideas = get_ideas()

    if not ideas:
        # Ultimate fallback seed if both backlog and research fail
        return {
            "id": str(uuid.uuid4())[:8],
            "title_seed": "The Daily Stoic Habit for Mental Toughness",
            "topic": "Marcus Aurelius on preparing for difficult people each morning",
            "hook_seed": "When you wake up in the morning, expect people to be difficult.",
            "source": "system_default",
            "proven_score": 0.9,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    learning = get_learning()
    winning_hooks = learning.get("winning_hooks", [])

    is_proven = random.random() < 0.70

    if is_proven:
        # Sort by proven score and preference for winning hook keywords
        def score_func(item: Dict[str, Any]) -> float:
            score = float(item.get("proven_score", 0.5))
            hook = item.get("hook_seed", "").lower()
            if any(w.lower() in hook for w in winning_hooks):
                score += 0.2
            return score

        selected = max(ideas, key=score_func)
        logger.info(f"Selected PROVEN idea (score {selected.get('proven_score')}): '{selected['title_seed']}'")
    else:
        # Pick experimental idea (random or lowest proven_score)
        selected = random.choice(ideas)
        logger.info(f"Selected EXPERIMENTAL idea: '{selected['title_seed']}'")

    # Remove selected idea from active backlog
    remaining = [i for i in ideas if i.get("id") != selected.get("id")]
    save_ideas(remaining)

    return selected


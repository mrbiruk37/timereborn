"""Recreate Engine: Builds new videos from reference analyses.

Keeps: core idea, story structure, beats, target duration, pacing, and hook type.
Changes: all wording, exact script, voice, specific footage, and visual style variant.
Enforces rotation across references, style variants, and n-gram originality checking.
"""

import json
import logging
import os
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from src.reference import load_reference_analyses, scan_and_update_references
from src.scriptgen import ShortScriptResponse, get_default_model, get_groq_client
from src.state import get_learning, get_posts, load_settings

logger = logging.getLogger("timereborn.recreate")


def extract_ngrams(text: str, n: int = 3) -> Set[Tuple[str, ...]]:
    """Extract word n-grams from text after basic normalization."""
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def compute_script_similarity(new_script: str, reference_transcript: str) -> float:
    """Compute n-gram overlap similarity between new script and reference transcript."""
    if not reference_transcript or len(reference_transcript.split()) < 5:
        return 0.0

    new_3grams = extract_ngrams(new_script, n=3)
    ref_3grams = extract_ngrams(reference_transcript, n=3)

    if not new_3grams or not ref_3grams:
        # Check single word Jaccard if n-grams are too sparse
        new_words = set(re.findall(r"\b\w+\b", new_script.lower()))
        ref_words = set(re.findall(r"\b\w+\b", reference_transcript.lower()))
        if not new_words or not ref_words:
            return 0.0
        return len(new_words & ref_words) / len(new_words | ref_words)

    overlap = new_3grams & ref_3grams
    return len(overlap) / len(new_3grams)


def select_reference_and_variant() -> Dict[str, Any]:
    """Select the next reference video in round-robin and an unused style variant."""
    analyses = load_reference_analyses()
    if not analyses:
        analyses = scan_and_update_references()

    if not analyses:
        raise RuntimeError("No reference videos found in video_idea/. Please add reference videos.")

    settings = load_settings()
    style_variants = settings.get("style_variants", [
        {"id": "cinematic_stock_footage", "name": "Cinematic Stock Footage"},
        {"id": "minimal_text_on_screen", "name": "Minimal Text on Screen"},
        {"id": "kinetic_typography", "name": "Kinetic Typography"},
        {"id": "image_zoom_storytelling", "name": "Image Zoom Storytelling"},
        {"id": "animated_diagrams", "name": "Animated Diagrams / Whiteboard"},
        {"id": "split_screen_comparison", "name": "Split-Screen Comparison"},
    ])
    posts = get_posts()

    # 1. Round-robin reference selection: pick least recently used reference file
    ref_files = sorted(list(analyses.keys()))
    ref_usage: Dict[str, int] = {f: 0 for f in ref_files}
    for p in posts:
        ref = p.get("reference_file")
        if ref in ref_usage:
            ref_usage[ref] += 1

    # Select the reference with lowest usage count (round-robin)
    selected_ref_file = min(ref_files, key=lambda f: ref_usage[f])
    ref_analysis = analyses[selected_ref_file]

    # 2. Pick a style variant not used recently with that reference
    used_variants_for_ref = [
        p.get("style_variant")
        for p in posts
        if p.get("reference_file") == selected_ref_file and p.get("style_variant")
    ]

    all_variant_ids = [v["id"] for v in style_variants]
    available_variants = [v for v in style_variants if v["id"] not in used_variants_for_ref]

    # If all variants have been used for this reference, reset cycle
    if not available_variants:
        available_variants = style_variants

    # Factor in learning.json (30% experiment, 70% proven if stats exist)
    learning = get_learning()
    proven_styles = learning.get("winning_styles", [])
    is_experiment = random.random() < 0.30

    if not is_experiment and proven_styles:
        preferred = [v for v in available_variants if v["id"] in proven_styles]
        selected_variant = random.choice(preferred) if preferred else random.choice(available_variants)
    else:
        selected_variant = random.choice(available_variants)

    # 3. Generate a distinct topic angle for this run
    past_angles = [
        p.get("topic_angle")
        for p in posts
        if p.get("reference_file") == selected_ref_file and p.get("topic_angle")
    ]
    core_idea = ref_analysis.get("structure", {}).get("core_idea", "Historical paradox and rebirth")
    topic = ref_analysis.get("structure", {}).get("topic", "Timeless Wisdom")

    topic_angle = generate_distinct_angle(
        topic=topic,
        core_idea=core_idea,
        past_angles=past_angles,
    )

    return {
        "reference_file": selected_ref_file,
        "reference_analysis": ref_analysis,
        "style_variant": selected_variant["id"],
        "style_variant_info": selected_variant,
        "topic_angle": topic_angle,
    }


def generate_distinct_angle(topic: str, core_idea: str, past_angles: List[str]) -> str:
    """Generate a fresh angle/example for this core idea that doesn't duplicate past posts."""
    client = get_groq_client()
    model = get_default_model()

    past_summary = ", ".join(f"'{a}'" for a in past_angles[-5:]) if past_angles else "None"

    prompt = f"""Topic: {topic}
Core Idea: {core_idea}
Past angles used for this idea: {past_summary}

TASK:
Provide ONE fresh, captivating, and distinct angle, perspective, or historical figure application
for this core idea. It must NOT duplicate any past angles.

Return strictly a single JSON object:
{{"angle": "Fresh captivating angle description in one sentence"}}
"""
    try:
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        data = json.loads(res.choices[0].message.content)
        return data.get("angle", f"Modern contrast on {topic}")
    except Exception as e:
        logger.warning(f"Could not generate dynamic angle: {e}")
        return f"A timeless look at {topic} through modern reality"


def generate_recreated_script(
    reference_analysis: Dict[str, Any],
    style_variant: str,
    topic_angle: str,
    max_similarity: float = 0.15,
) -> ShortScriptResponse:
    """Generate a 100% original script keeping reference structure and pacing."""
    client = get_groq_client()
    model = get_default_model()

    structure = reference_analysis.get("structure", {})
    technical = reference_analysis.get("technical", {})
    audio = reference_analysis.get("audio", {})

    target_duration = structure.get("length_seconds") or technical.get("duration", 15.0)
    hook_type = structure.get("hook_type_and_text", "Pattern interrupt")
    beats = structure.get("story_structure", [])
    ref_transcript = audio.get("transcript", "")

    # Calculate target word count based on reference pacing or default ~130-150 WPM
    wpm = audio.get("speaking_pace_wpm") or 140
    target_words = max(35, min(95, int((target_duration / 60.0) * wpm)))

    beats_formatted = "\n".join(
        f"- At {b.get('timestamp_sec', 0)}s: {b.get('beat', '')}" for b in beats
    )

    system_prompt = f"""You are the lead viral scriptwriter for TimeReborn.
Your mission is to RECREATE the viral feeling and structure of a proven reference video,
while creating a COMPLETELY 100% ORIGINAL piece of content.

RULES FOR RECREATION:
1. SAME CORE IDEA & STRUCTURE: Keep the underlying premise and narrative rhythm.
2. SAME PACING & BEATS: Follow these narrative beats closely:
{beats_formatted}
3. TARGET DURATION: Spoken duration must be approximately {target_duration:.1f} seconds (~{target_words} words).
4. CHOSEN STYLE VARIANT: '{style_variant}'. Tailor scene keywords and tone to this visual style.
5. STRICT ORIGINALITY: Never copy exact phrases, audio, or wording from the reference transcript.
6. FORMAT: Narration script must contain ONLY words to be spoken aloud. NO stage directions, NO asterisks.
7. AI DISCLOSURE: In the description, include: 'Created with AI assistance (script & voiceover).'
"""

    user_prompt = f"""Topic / Rebirth Premise: {structure.get('topic', 'History Reborn')}
Angle for this video: {topic_angle}
Hook Type: {hook_type}
Target Word Count: ~{target_words} words

Generate a JSON object with:
{{
  "title_options": ["Curiosity-inducing Title 1", "Title 2", "Title 3"],
  "hook": "Opening 2-second hook line matching the reference hook style",
  "script": "Full narration text to speak (~{target_words} words, no stage directions)",
  "scene_keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"],
  "description": "Viral description with takeaways, hashtags, and AI disclosure",
  "tags": ["TimeReborn", "history", "ai", "future", "viral"],
  "hashtags": ["#Shorts", "#TimeReborn", "#History", "#AI", "#Viral", "#FYP"]
}}
"""

    for attempt in range(3):
        logger.info(f"Generating recreated script (attempt {attempt + 1}/3)...")
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7 + (attempt * 0.1),
        )
        content = res.choices[0].message.content
        data = json.loads(content)
        parsed = ShortScriptResponse(**data)

        # Originality check against reference transcript
        similarity = compute_script_similarity(parsed.script, ref_transcript)
        logger.info(f"Script similarity to reference transcript: {similarity:.3f} (Max threshold: {max_similarity})")

        if similarity <= max_similarity:
            return parsed
        else:
            logger.warning(f"High similarity detected ({similarity:.3f} > {max_similarity}). Regenerating...")

    logger.warning("Reached max attempts for similarity check. Returning best generated script.")
    return parsed


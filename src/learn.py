"""Self-learning loop: Builds learning.json and dispatches daily Telegram summaries."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from src.scriptgen import get_default_model, get_groq_client
from src.state import get_comments, get_learning, get_posts, save_learning
from src.telegram import send_message

load_dotenv()
logger = logging.getLogger("timereborn.learn")


def compute_post_score(post: Dict[str, Any]) -> float:
    """Calculate engagement score for ranking top and bottom videos."""
    metrics = post.get("metrics", {})
    m = metrics.get("72h") or metrics.get("24h") or {}
    views = m.get("views", 0)
    likes = m.get("likes", 0)
    comments = m.get("comments", 0)
    return float(views + (likes * 4) + (comments * 8))


def generate_llm_insights(top_videos: List[Dict[str, Any]], bottom_videos: List[Dict[str, Any]]) -> List[str]:
    """Use Groq LLM to derive strategic directives from winning and losing videos."""
    if not top_videos:
        return [
            "Use curiosity gap questions in the first 2 seconds.",
            "Focus on actionable stoic wisdom and emotional clarity.",
        ]

    client = get_groq_client()
    model = get_default_model()

    summary_text = "TOP PERFORMING VIDEOS:\n"
    for v in top_videos[:3]:
        summary_text += f"- Title: {v.get('title')} | Hook: {v.get('hook')} | Duration: {v.get('duration_seconds')}s\n"

    if bottom_videos:
        summary_text += "\nUNDERPERFORMING VIDEOS:\n"
        for v in bottom_videos[:2]:
            summary_text += f"- Title: {v.get('title')} | Hook: {v.get('hook')} | Duration: {v.get('duration_seconds')}s\n"

    prompt = f"""You are the strategic brain of Timereborn, an autonomous video channel.
Analyze the performance differences below:

{summary_text}

Provide 3 concise, highly actionable directives for the next video scripts (e.g. hook style, pacing, emotional tone).
Return strictly a JSON array of strings:
["Directive 1", "Directive 2", "Directive 3"]
"""

    try:
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        content = res.choices[0].message.content
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and v:
                    return [str(item) for item in v[:4]]
    except Exception as e:
        logger.warning(f"Could not generate LLM insights: {e}")

    return [
        "Deliver immediate value in the first 2 seconds without greetings.",
        "Emphasize tangible personal agency over passive reflection.",
    ]


def run_learning_loop() -> Dict[str, Any]:
    """Analyze performance history, update learning.json, and return updated insights."""
    posts = get_posts()
    comments = get_comments()

    # Filter posts with scored metrics
    scored_posts = sorted(posts, key=compute_post_score, reverse=True)

    top_posts = scored_posts[:5] if scored_posts else []
    bottom_posts = scored_posts[-5:] if len(scored_posts) > 5 else []

    winning_hooks = [p.get("hook") for p in top_posts if p.get("hook")]
    losing_hooks = [p.get("hook") for p in bottom_posts if p.get("hook")]

    # Calculate optimal length
    durations = [p.get("duration_seconds", 30) for p in top_posts if p.get("duration_seconds")]
    min_len = int(min(durations)) if durations else 25
    max_len = int(max(durations)) if durations else 45

    # Extract requested topics from comments
    requested = [c.get("topic") for c in comments if c.get("classification") == "request" and c.get("topic")]

    key_insights = generate_llm_insights(top_posts, bottom_posts)

    learning_data = {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "top_videos": [
            {
                "title": p.get("title"),
                "hook": p.get("hook"),
                "duration_seconds": p.get("duration_seconds"),
                "score": compute_post_score(p),
            }
            for p in top_posts
        ],
        "bottom_videos": [
            {
                "title": p.get("title"),
                "hook": p.get("hook"),
                "duration_seconds": p.get("duration_seconds"),
                "score": compute_post_score(p),
            }
            for p in bottom_posts
        ],
        "winning_hooks": winning_hooks[:5],
        "losing_hooks": losing_hooks[:5],
        "best_lengths_sec": {
            "short": [max(25, min_len), min(45, max_len)],
            "long": [300, 480],
        },
        "best_posting_times_utc": ["13:00", "17:00", "22:00"],
        "requested_topics": requested[:10],
        "key_insights": key_insights,
    }

    save_learning(learning_data)
    logger.info("Updated learning.json with latest performance insights.")
    return learning_data


def send_daily_summary(dry_run: bool = False) -> None:
    """Send daily performance summary in plain text strictly if real stats exist."""
    learning = get_learning()
    posts = get_posts()

    # Only send if real stats exist
    posts_with_views = []
    for p in posts:
        m = p.get("metrics", {}).get("72h") or p.get("metrics", {}).get("24h") or {}
        v = m.get("views")
        if v is not None and v > 0:
            posts_with_views.append((p.get("title", "Untitled"), v))

    if not posts_with_views:
        logger.info("No real video stats available yet. Daily summary skipped.")
        return

    posts_with_views.sort(key=lambda x: x[1], reverse=True)
    best_vid = posts_with_views[0]
    worst_vid = posts_with_views[-1]
    insights = learning.get("key_insights", [])

    lines = [
        "Daily Performance Summary",
        f"Total Videos Tracked: {len(posts)}",
        f"Best Video: {best_vid[0]} ({best_vid[1]} views)",
        f"Lowest Video: {worst_vid[0]} ({worst_vid[1]} views)",
        "Planned Adjustments:",
    ]
    for ins in insights[:3]:
        lines.append(f"- {ins}")

    summary_msg = "\n".join(lines)

    try:
        send_message(text=summary_msg, dry_run=dry_run)
        logger.info("Daily summary successfully delivered to Telegram.")
    except Exception as e:
        logger.warning(f"Failed to send daily summary: {e}")


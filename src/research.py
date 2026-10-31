"""Research module: Analyzes top performing videos from reference channels for inspiration.

Hard Rule 1: Only titles, topics, hooks, stats, and transcripts are studied for concepts.
Never download, copy, re-upload, or edit other creators' audio/footage/script text.
"""

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from src.scriptgen import get_groq_client, get_default_model
from src.state import load_sources
from src.youtube import get_authenticated_service

load_dotenv()
logger = logging.getLogger("timereborn.research")


def fetch_channel_recent_videos(channel_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Fetch top recent videos using YouTube Data API v3 uploads playlist (quota-efficient)."""
    try:
        youtube = get_authenticated_service()
        # 1. Fetch channel's contentDetails to find uploads playlist ID (costs 1 unit)
        ch_resp = youtube.channels().list(
            part="contentDetails,statistics",
            id=channel_id,
        ).execute()

        items = ch_resp.get("items", [])
        if not items:
            logger.warning(f"No channel found for ID: {channel_id}")
            return []

        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Fetch playlist items (costs 1 unit)
        pl_resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
        ).execute()

        video_ids = [item["snippet"]["resourceId"]["videoId"] for item in pl_resp.get("items", [])]
        if not video_ids:
            return []

        # 3. Fetch statistics for these videos (costs 1 unit)
        vid_resp = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids),
        ).execute()

        videos_data = []
        for vid in vid_resp.get("items", []):
            snippet = vid.get("snippet", {})
            stats = vid.get("statistics", {})
            video_id = vid.get("id")

            # Optional transcript extraction (guarded in try/except)
            transcript_text = None
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                t_list = YouTubeTranscriptApi.get_transcript(video_id)
                transcript_text = " ".join(t["text"] for t in t_list[:15])  # First ~45s of transcript
            except Exception:
                pass

            videos_data.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200],
                "tags": snippet.get("tags", []),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "published_at": snippet.get("publishedAt"),
                "sample_transcript": transcript_text,
            })

        return videos_data

    except HttpError as e:
        logger.warning(f"YouTube API quota or HTTP error in research: {e}")
        return []
    except Exception as e:
        logger.warning(f"Error fetching channel videos: {e}")
        return []


def synthesize_ideas_from_research(researched_videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Use Groq LLM to study patterns from researched videos and produce 100% ORIGINAL ideas."""
    if not researched_videos:
        # Fallback inspirational seeds if API unavailable
        return [
            {
                "id": str(uuid.uuid4())[:8],
                "title_seed": "Marcus Aurelius on Controlling Your Mind",
                "topic": "Stoic emotional resilience and inner citadel",
                "hook_seed": "You have power over your mind, not outside events.",
                "source": "fallback_seed",
                "proven_score": 0.85,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        ]

    client = get_groq_client()
    model = get_default_model()

    titles_summary = "\n".join(
        f"- Title: {v['title']} (Views: {v['views']}, Likes: {v['likes']})"
        for v in researched_videos[:8]
    )

    prompt = f"""Study these top-performing video titles and engagement stats:
{titles_summary}

TASK:
Identify why these concepts resonated with viewers (curiosity gaps, psychological triggers, timeless lessons).
Then, brainstorm 3 completely ORIGINAL, fresh video ideas inspired by these high-level themes.

HARD RULE: Never copy, plagiarize, or reuse titles verbatim. Generate completely original concepts and angles.

Return strictly a JSON object with format:
{{
  "ideas": [
    {{
      "title_seed": "Original captivating working title",
      "topic": "Specific philosophical/practical topic to cover",
      "hook_seed": "Curiosity-sparking opening premise or question",
      "proven_score": 0.85
    }}
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        ideas_list = data.get("ideas", [])

        results = []
        for item in ideas_list:
            results.append({
                "id": str(uuid.uuid4())[:8],
                "title_seed": item.get("title_seed", "Untitled Idea"),
                "topic": item.get("topic", "Timeless Wisdom"),
                "hook_seed": item.get("hook_seed", "Stop scrolling."),
                "source": "research",
                "proven_score": float(item.get("proven_score", 0.75)),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        return results
    except Exception as e:
        logger.error(f"Failed to synthesize ideas via Groq: {e}")
        return []


def synthesize_tiktok_inspiration(tiktok_creators: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synthesize fresh, original video ideas inspired by reference TikTok creator niches."""
    if not tiktok_creators:
        return []

    client = get_groq_client()
    model = get_default_model()

    creators_desc = "\n".join(
        f"- {c['handle']} ({c.get('theme', 'Viral storytelling')})"
        for c in tiktok_creators
    )

    prompt = f"""You are the creative strategist for Timereborn.
We are studying the viral storytelling formats and hook structures of these top TikTok creators:
{creators_desc}

KEY ATTRIBUTES OF THESE CHANNELS:
- AI-driven historical scenes, mysterious what-if scenarios, and dramatic timeline paradoxes
- Deep narrative tension in the first 2 seconds (scroll-stopping pattern interrupts)
- Universal themes: time, empires, ancient secrets, psychological discipline

TASK:
Brainstorm 3 completely ORIGINAL, fresh video concepts that fit this exact high-retention viral style.
HARD RULE: 100% original. Never copy existing scripts, clips, or audio.

Return JSON:
{{
  "ideas": [
    {{
      "title_seed": "Original high-retention title",
      "topic": "Compelling historical or philosophical premise",
      "hook_seed": "Opening 2-second hook line to stop the scroll",
      "proven_score": 0.92
    }}
  ]
}}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        data = json.loads(response.choices[0].message.content)
        ideas_list = data.get("ideas", [])
        results = []
        for item in ideas_list:
            results.append({
                "id": str(uuid.uuid4())[:8],
                "title_seed": item.get("title_seed", "Untitled Idea"),
                "topic": item.get("topic", "Historical Paradox"),
                "hook_seed": item.get("hook_seed", "What history never told you."),
                "source": "tiktok_research",
                "proven_score": float(item.get("proven_score", 0.90)),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        return results
    except Exception as e:
        logger.error(f"Failed to synthesize TikTok ideas: {e}")
        return []


def run_research() -> List[Dict[str, Any]]:
    """Execute end-to-end research across configured YouTube and TikTok sources."""
    sources = load_sources()
    channels = sources.get("channels", [])
    tiktok_creators = sources.get("tiktok_creators", [])
    logger.info(f"Running research across {len(channels)} YouTube channels and {len(tiktok_creators)} TikTok creators...")

    all_ideas = []
    # 1. YouTube reference channels
    all_researched_videos = []
    for ch in channels:
        ch_id = ch.get("id")
        if ch_id:
            videos = fetch_channel_recent_videos(ch_id, max_results=3)
            all_researched_videos.extend(videos)

    yt_ideas = synthesize_ideas_from_research(all_researched_videos)
    all_ideas.extend(yt_ideas)

    # 2. TikTok reference creators
    if tiktok_creators:
        tt_ideas = synthesize_tiktok_inspiration(tiktok_creators)
        all_ideas.extend(tt_ideas)

    logger.info(f"Synthesized {len(all_ideas)} total original idea candidates.")
    return all_ideas


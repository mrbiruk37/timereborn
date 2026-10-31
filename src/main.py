"""Timereborn CLI: Autonomous content engine entrypoint."""

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("timereborn")

from src.captions import create_subtitles
from src.footage import prepare_scene_footage
from src.render import render_video
from src.scriptgen import generate_short_script
from src.state import add_post, load_settings
from src.voice import generate_voiceover


def cmd_make_short(topic: str, output_dir: Optional[Path] = None) -> Path:
    """Execute Phase 1 pipeline: generate an original Short video from topic."""
    logger.info(f"=== Starting Short Generation for Topic: '{topic}' ===")

    settings = load_settings()
    limits = settings.get("limits", {})
    min_dur = limits.get("shorts_min_duration_sec", 25)
    max_dur = limits.get("shorts_max_duration_sec", 45)

    out_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="timereborn_short_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Generate 100% original script via Groq
        logger.info("Step 1/5: Generating script with Groq LLM...")
        script_res = generate_short_script(topic=topic)
        chosen_title = script_res.title_options[0]
        logger.info(f"Selected Title: {chosen_title}")
        logger.info(f"Opening Hook: {script_res.hook}")
        logger.info(f"Scene Keywords: {script_res.scene_keywords}")

        # 2. Synthesize voiceover audio with edge-tts
        logger.info("Step 2/5: Synthesizing voiceover with edge-tts...")
        audio_path = tmp_dir / "voiceover.mp3"
        duration = generate_voiceover(text=script_res.script, output_path=audio_path)
        logger.info(f"Audio duration: {duration:.2f}s (Target: {min_dur}-{max_dur}s)")

        # 3. Generate subtitles with faster-whisper (.ass format)
        logger.info("Step 3/5: Generating word-level subtitles...")
        subtitles_path = tmp_dir / "subtitles.ass"
        create_subtitles(
            audio_path=audio_path,
            output_ass_path=subtitles_path,
            script_fallback=script_res.script,
            total_duration=duration,
        )

        # 4. Acquire footage clips via Pixabay
        logger.info("Step 4/5: Sourcing scene footage...")
        scenes = prepare_scene_footage(
            keywords=script_res.scene_keywords,
            total_duration=duration,
            temp_dir=tmp_dir,
            orientation="vertical",
        )

        # 5. Render final vertical video
        safe_name = "".join(c if c.isalnum() else "_" for c in chosen_title[:30]).strip("_")
        final_output = out_dir / f"short_{safe_name}.mp4"
        logger.info(f"Step 5/5: Rendering final video to {final_output}...")

        render_video(
            scenes=scenes,
            voiceover_path=audio_path,
            subtitles_path=subtitles_path,
            output_path=final_output,
            hook_text=script_res.hook,
            width=1080,
            height=1920,
            fps=30,
        )

        # Save metadata info file alongside output
        meta_file = final_output.with_suffix(".json")
        import json
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "title": chosen_title,
                "title_options": script_res.title_options,
                "hook": script_res.hook,
                "script": script_res.script,
                "description": script_res.description,
                "tags": script_res.tags,
                "hashtags": script_res.hashtags,
                "duration_seconds": duration,
                "video_file": str(final_output),
            }, f, indent=2)

        logger.info(f"=== SUCCESS: Short created at {final_output} ===")
        print(f"\n[TIMEREBORN] Video generated successfully!")
        print(f"Title: {chosen_title}")
        print(f"Hook: {script_res.hook}")
        print(f"Output File: {final_output}")
        print(f"Metadata File: {meta_file}")
        return final_output


def main():
    parser = argparse.ArgumentParser(description="Timereborn autonomous content agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # make-short
    p_short = subparsers.add_parser("make-short", help="Generate an original vertical short video")
    p_short.add_argument("--topic", required=True, help="Topic or concept for the video")
    p_short.add_argument("--output-dir", default="output", help="Directory to save finished MP4")

    # make-long (Phase 6)
    p_long = subparsers.add_parser("make-long", help="Generate an original long horizontal video")
    p_long.add_argument("--topic", required=True, help="Topic for long video")

    # post-slot (Phase 3)
    p_slot = subparsers.add_parser("post-slot", help="Execute scheduled posting slot")
    p_slot.add_argument("--slot", default="slot_1", help="Slot ID from settings.yml")

    # analytics (Phase 4)
    p_analytics = subparsers.add_parser("analytics", help="Collect metrics and run learning loop")

    # comments (Phase 5)
    p_comments = subparsers.add_parser("comments", help="Process and reply to comments")

    # poll-telegram (Phase 5)
    p_poll = subparsers.add_parser("poll-telegram", help="Poll Telegram for commands and approval callbacks")

    args = parser.parse_args()

    if args.command == "make-short":
        cmd_make_short(topic=args.topic, output_dir=Path(args.output_dir))
    elif args.command == "make-long":
        logger.info("make-long will be implemented in Phase 6.")
    elif args.command == "post-slot":
        logger.info("post-slot will be implemented in Phase 3.")
    elif args.command == "analytics":
        logger.info("analytics will be implemented in Phase 4.")
    elif args.command == "comments":
        logger.info("comments will be implemented in Phase 5.")
    elif args.command == "poll-telegram":
        logger.info("poll-telegram will be implemented in Phase 5.")


if __name__ == "__main__":
    main()

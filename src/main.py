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

# Ensure Windows console handles UTF-8 gracefully without charmap crashes
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("timereborn")

from src.analytics import collect_milestone_analytics
from src.captions import create_subtitles
from src.comments import process_comments_pipeline
from src.footage import prepare_scene_footage
from src.ideas import select_next_idea
from src.learn import run_learning_loop, send_daily_summary
from src.render import render_video
from src.scriptgen import generate_long_script, generate_short_script
from src.state import add_post, load_settings
from src.telegram import send_alert, send_approval_request, send_message, send_video
from src.telegram_poll import poll_telegram_events
from src.tiktok import format_tiktok_caption, is_tiktok_configured, post_to_tiktok
from src.voice import generate_voiceover
from src.youtube import upload_video


def cmd_make_short(
    topic: str,
    output_dir: Optional[Path] = None,
    upload: bool = False,
    slot: str = "manual",
) -> Path:
    """Execute Short generation pipeline, optional YouTube upload, and Telegram dispatch."""
    logger.info(f"=== Starting Short Generation for Topic: '{topic}' ===")

    settings = load_settings()
    limits = settings.get("limits", {})
    min_dur = limits.get("shorts_min_duration_sec", 25)
    max_dur = limits.get("shorts_max_duration_sec", 45)
    mode = settings.get("mode", "approve")

    out_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
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
            post_metadata = {
                "title": chosen_title,
                "title_options": script_res.title_options,
                "hook": script_res.hook,
                "script": script_res.script,
                "description": script_res.description,
                "tags": script_res.tags,
                "hashtags": script_res.hashtags,
                "duration_seconds": duration,
                "video_file": str(final_output),
                "topic": topic,
            }
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(post_metadata, f, indent=2)

            logger.info(f"=== SUCCESS: Short created at {final_output} ===")
            print(f"\n[TIMEREBORN] Video generated successfully!")
            print(f"Title: {chosen_title}")
            print(f"Hook: {script_res.hook}")
            print(f"Output File: {final_output}")

            # Phase 2: Upload to YouTube & Send to Telegram
            if upload:
                privacy = "private" if mode == "approve" else "public"
                logger.info(f"Uploading video to YouTube (privacy: {privacy})...")
                yt_res = upload_video(
                    video_path=final_output,
                    title=chosen_title,
                    description=script_res.description,
                    tags=script_res.tags,
                    privacy_status=privacy,
                )

                yt_id = yt_res["video_id"]
                yt_url = yt_res["video_url"]

                # High-virality TikTok caption template
                tiktok_caption = format_tiktok_caption(
                    title=chosen_title,
                    hook=script_res.hook,
                    hashtags=script_res.hashtags,
                )

                # Attempt direct automated TikTok upload if session is configured
                logger.info("Attempting TikTok publishing...")
                tiktok_res = post_to_tiktok(
                    video_path=final_output,
                    title=chosen_title,
                    description=tiktok_caption,
                    tags=script_res.tags,
                )
                
                if tiktok_res.get("status") == "published":
                    tiktok_status_desc = "✅ Live on TikTok!"
                elif tiktok_res.get("status") == "pending_credentials":
                    tiktok_status_desc = "📱 MP4 dispatched to Telegram (Add TIKTOK_SESSION_ID to auto-post)"
                else:
                    tiktok_status_desc = f"⚠️ {tiktok_res.get('error', 'Pending')}"

                # Deliver to Telegram
                if mode == "approve":
                    logger.info("Delivering approval request to Telegram...")
                    send_approval_request(
                        video_id=yt_id,
                        title=chosen_title,
                        youtube_url=yt_url,
                        video_path=final_output,
                        caption=tiktok_caption,
                        slot=slot,
                        concept_notes=f"Generated from topic: {topic}",
                        tiktok_status=tiktok_status_desc,
                    )
                else:
                    logger.info("Sending public video announcement and TikTok file to Telegram...")
                    send_video(video_path=final_output, caption=tiktok_caption)
                    send_message(
                        f"🚀 <b>Video Published Live!</b>\n\n"
                        f"<b>Title:</b> {chosen_title}\n"
                        f"<b>YouTube Link:</b> <a href=\"{yt_url}\">{yt_url}</a>\n"
                        f"<b>TikTok Status:</b> {tiktok_status_desc}\n"
                        f"<b>Hook:</b> <i>\"{script_res.hook}\"</i>\n"
                        f"<b>Slot:</b> <code>{slot}</code>\n\n"
                        f"📱 Attached above is your <b>TikTok-Ready MP4</b> with viral caption template."
                    )

                # Record in posts.json
                post_record = {
                    "id": yt_id,
                    "youtube_id": yt_id,
                    "youtube_url": yt_url,
                    "tiktok_status": tiktok_res.get("status"),
                    "title": chosen_title,
                    "hook": script_res.hook,
                    "description": script_res.description,
                    "privacy_status": privacy,
                    "status": "pending_approval" if mode == "approve" else "published",
                    "slot": slot,
                    "created_at": yt_res["uploaded_at"],
                    "video_path": str(final_output),
                    "duration_seconds": duration,
                }
                add_post(post_record)
                logger.info(f"Post recorded in posts.json with ID {yt_id}")

            return final_output

    except Exception as e:
        logger.exception(f"Pipeline failure: {e}")
        send_alert(error_summary=str(e), details=f"Topic: {topic}")
        raise


def cmd_post_slot(slot: str = "auto") -> Path:
    """Execute scheduled posting slot: pick idea, generate video, upload, and notify."""
    logger.info(f"=== Executing Scheduled Slot: '{slot}' ===")
    settings = load_settings()

    # Check if channel is paused via /pause command
    if settings.get("status") == "paused":
        logger.info("Posting is currently PAUSED via /pause command. Skipping slot.")
        return Path("")

    # Determine if slot is configured as long or short
    slot_type = "short"
    if slot in ("slot_2", "long"):
        # Check if slot 2 is configured for long videos
        slots_cfg = settings.get("schedule", {}).get("slots", [])
        for s in slots_cfg:
            if s.get("id") == slot and s.get("type") == "long":
                slot_type = "long"

    try:
        idea = select_next_idea()
        logger.info(f"Selected Idea for slot '{slot}': '{idea.get('title_seed')}' (Source: {idea.get('source')})")
        topic = idea.get("topic", idea.get("title_seed", "Stoic Wisdom"))

        if slot_type == "long":
            return cmd_make_long(topic=topic, upload=True, slot=slot)
        else:
            return cmd_make_short(topic=topic, upload=True, slot=slot)
    except Exception as e:
        logger.exception(f"Slot {slot} failed: {e}")
        send_alert(error_summary=f"Failed slot {slot}: {e}")
        raise


def cmd_make_long(
    topic: str,
    output_dir: Optional[Path] = None,
    upload: bool = False,
    slot: str = "slot_2",
) -> Path:
    """Execute Phase 6 long-form video pipeline: structured chapters, 16:9 render, YouTube upload."""
    logger.info(f"=== Starting Long-Form Video Generation for Topic: '{topic}' ===")

    settings = load_settings()
    mode = settings.get("mode", "approve")

    out_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="timereborn_long_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            # 1. Generate structured long-form script
            logger.info("Step 1/5: Generating chapter-based documentary script with Groq...")
            long_res = generate_long_script(topic=topic)
            chosen_title = long_res.title_options[0]
            logger.info(f"Selected Long Title: {chosen_title}")
            logger.info(f"Total Chapters: {len(long_res.chapters)}")

            # 2. Combine narration text and collect visual keywords
            all_keywords = []
            full_narration_parts = [long_res.hook]
            for ch in long_res.chapters:
                full_narration_parts.append(ch.script)
                all_keywords.extend(ch.scene_keywords)

            full_script = " ".join(full_narration_parts)

            # 3. Synthesize voiceover audio
            logger.info("Step 2/5: Synthesizing long voiceover with edge-tts...")
            audio_path = tmp_dir / "voiceover_long.mp3"
            duration = generate_voiceover(text=full_script, output_path=audio_path)
            logger.info(f"Long audio duration: {duration:.2f}s (~{duration/60:.1f} mins)")

            # 4. Generate widescreen subtitles (1920x1080)
            logger.info("Step 3/5: Generating 16:9 widescreen subtitles...")
            subtitles_path = tmp_dir / "subtitles_long.ass"
            create_subtitles(
                audio_path=audio_path,
                output_ass_path=subtitles_path,
                script_fallback=full_script,
                total_duration=duration,
                width=1920,
                height=1080,
            )

            # 5. Acquire horizontal footage clips
            logger.info("Step 4/5: Sourcing 16:9 landscape footage...")
            scenes = prepare_scene_footage(
                keywords=all_keywords[:12],
                total_duration=duration,
                temp_dir=tmp_dir,
                orientation="horizontal",
            )

            # 6. Render final horizontal video
            safe_name = "".join(c if c.isalnum() else "_" for c in chosen_title[:30]).strip("_")
            final_output = out_dir / f"long_{safe_name}.mp4"
            logger.info(f"Step 5/5: Rendering 1920x1080 widescreen video to {final_output}...")

            render_video(
                scenes=scenes,
                voiceover_path=audio_path,
                subtitles_path=subtitles_path,
                output_path=final_output,
                hook_text=long_res.hook[:60],
                width=1920,
                height=1080,
                fps=30,
            )

            # Metadata file
            meta_file = final_output.with_suffix(".json")
            import json
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump({
                    "title": chosen_title,
                    "title_options": long_res.title_options,
                    "hook": long_res.hook,
                    "chapters": [c.model_dump() for c in long_res.chapters],
                    "description": long_res.description,
                    "tags": long_res.tags,
                    "duration_seconds": duration,
                    "video_file": str(final_output),
                    "type": "long",
                }, f, indent=2)

            print(f"\n[TIMEREBORN] Long video generated successfully!")
            print(f"Title: {chosen_title}")
            print(f"Output File: {final_output}")

            # Upload if requested
            if upload:
                privacy = "private" if mode == "approve" else "public"
                logger.info(f"Uploading long video to YouTube (privacy: {privacy})...")
                yt_res = upload_video(
                    video_path=final_output,
                    title=chosen_title,
                    description=long_res.description,
                    tags=long_res.tags,
                    privacy_status=privacy,
                )
                yt_id = yt_res["video_id"]
                yt_url = yt_res["video_url"]

                if mode == "approve":
                    send_message(
                        f"🎬 <b>Long Video Uploaded (Private)</b>\n\n"
                        f"<b>Title:</b> {chosen_title}\n"
                        f"<b>Slot:</b> <code>{slot}</code>\n"
                        f"<b>Duration:</b> {duration/60:.1f} mins\n"
                        f"<b>YouTube Link:</b> <a href=\"{yt_url}\">{yt_url}</a>\n\n"
                        f"Click below to approve for public release or reject.",
                        reply_markup={
                            "inline_keyboard": [
                                [
                                    {"text": "✅ Approve (Publish)", "callback_data": f"approve:{yt_id}"},
                                    {"text": "❌ Reject (Delete)", "callback_data": f"reject:{yt_id}"},
                                ]
                            ]
                        },
                    )
                else:
                    send_message(
                        f"🚀 <b>Long Video Published Live!</b>\n\n"
                        f"<b>Title:</b> {chosen_title}\n"
                        f"<b>Link:</b> <a href=\"{yt_url}\">{yt_url}</a>"
                    )

                add_post({
                    "id": yt_id,
                    "youtube_id": yt_id,
                    "youtube_url": yt_url,
                    "title": chosen_title,
                    "hook": long_res.hook,
                    "description": long_res.description,
                    "privacy_status": privacy,
                    "status": "pending_approval" if mode == "approve" else "published",
                    "slot": slot,
                    "type": "long",
                    "created_at": yt_res["uploaded_at"],
                    "video_path": str(final_output),
                    "duration_seconds": duration,
                })

            return final_output

    except Exception as e:
        logger.exception(f"Long video failure: {e}")
        send_alert(error_summary=str(e), details=f"Topic: {topic}")
        raise


def cmd_comments() -> None:
    """Execute comments classification and auto-reply pipeline."""
    logger.info("=== Processing Viewer Comments ===")
    try:
        process_comments_pipeline()
    except Exception as e:
        logger.exception(f"Comment processing failed: {e}")
        send_alert(error_summary=f"Comment processing failed: {e}")
        raise


def cmd_poll_telegram() -> None:
    """Execute Telegram update polling for approval callbacks and commands."""
    logger.info("=== Polling Telegram Updates ===")
    try:
        poll_telegram_events()
    except Exception as e:
        logger.exception(f"Telegram polling failed: {e}")
        send_alert(error_summary=f"Telegram polling failed: {e}")
        raise


def cmd_analytics() -> None:
    """Execute daily analytics collection and learning loop."""
    logger.info("=== Executing Analytics & Learning Loop ===")
    try:
        collect_milestone_analytics()
        run_learning_loop()
        send_daily_summary()
    except Exception as e:
        logger.exception(f"Analytics run failed: {e}")
        send_alert(error_summary=f"Analytics failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Timereborn autonomous content agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # make-short
    p_short = subparsers.add_parser("make-short", help="Generate an original vertical short video")
    p_short.add_argument("--topic", required=True, help="Topic or concept for the video")
    p_short.add_argument("--output-dir", default="output", help="Directory to save finished MP4")
    p_short.add_argument("--upload", action="store_true", help="Upload to YouTube and deliver to Telegram")
    p_short.add_argument("--slot", default="manual", help="Posting slot label")

    # make-long (Phase 6)
    p_long = subparsers.add_parser("make-long", help="Generate an original long horizontal video")
    p_long.add_argument("--topic", required=True, help="Topic for long video")
    p_long.add_argument("--output-dir", default="output", help="Directory to save finished MP4")
    p_long.add_argument("--upload", action="store_true", help="Upload to YouTube and deliver to Telegram")
    p_long.add_argument("--slot", default="slot_2", help="Posting slot label")

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
        cmd_make_short(
            topic=args.topic,
            output_dir=Path(args.output_dir),
            upload=args.upload,
            slot=args.slot,
        )
    elif args.command == "make-long":
        cmd_make_long(
            topic=args.topic,
            output_dir=Path(args.output_dir),
            upload=args.upload,
            slot=args.slot,
        )
    elif args.command == "post-slot":
        cmd_post_slot(slot=args.slot)
    elif args.command == "analytics":
        cmd_analytics()
    elif args.command == "comments":
        cmd_comments()
    elif args.command == "poll-telegram":
        cmd_poll_telegram()


if __name__ == "__main__":
    main()

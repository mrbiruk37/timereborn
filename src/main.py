"""Timereborn CLI: Autonomous content engine entrypoint."""

import argparse
import json
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
from src.quality_gate import run_quality_gate
from src.recreate import generate_recreated_script, select_reference_and_variant
from src.render import render_video
from src.scriptgen import generate_long_script, generate_short_script
from src.state import add_post, load_settings
from src.telegram import (
    format_real_post_message,
    send_alert,
    send_message,
    send_post_notification,
    send_video,
)
from src.telegram_poll import poll_telegram_events
from src.tiktok import format_tiktok_caption, is_tiktok_configured, post_to_tiktok
from src.voice import generate_voiceover
from src.youtube import upload_video


def build_and_render_short(
    script_res,
    target_duration: float,
    out_dir: Path,
    reference_transcript: str = "",
) -> tuple[Path, Path, Path, float]:
    """Helper to synthesize audio, subtitles, footage, and render final short video."""
    with tempfile.TemporaryDirectory(prefix="timereborn_short_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Synthesize voiceover
        audio_path = tmp_dir / "voiceover.mp3"
        duration = generate_voiceover(text=script_res.script, output_path=audio_path)

        # 2. Generate subtitles (.ass)
        subtitles_path = tmp_dir / "subtitles.ass"
        create_subtitles(
            audio_path=audio_path,
            output_ass_path=subtitles_path,
            script_fallback=script_res.script,
            total_duration=duration,
        )

        # 3. Source scene footage
        scenes = prepare_scene_footage(
            keywords=script_res.scene_keywords,
            total_duration=duration,
            temp_dir=tmp_dir,
            orientation="vertical",
        )

        # 4. Render final video
        chosen_title = script_res.title_options[0]
        safe_name = "".join(c if c.isalnum() else "_" for c in chosen_title[:30]).strip("_")
        final_output = out_dir / f"short_{safe_name}.mp4"

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

        # Keep temporary audio and ass files alongside output for quality gate verification
        perm_audio = out_dir / f"audio_{safe_name}.mp3"
        perm_sub = out_dir / f"subtitles_{safe_name}.ass"
        perm_audio.write_bytes(audio_path.read_bytes())
        perm_sub.write_bytes(subtitles_path.read_bytes())

        return final_output, perm_audio, perm_sub, duration


def cmd_post_slot(slot: str = "auto", dry_run: bool = False) -> Path:
    """Execute scheduled posting slot: round-robin reference recreation, quality gate, public posting."""
    logger.info(f"=== Executing Scheduled Slot: '{slot}' (dry_run={dry_run}) ===")
    settings = load_settings()

    if settings.get("status") == "paused":
        logger.info("Posting is currently PAUSED via /pause. Skipping slot.")
        return Path("")

    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Select reference video and unused style variant in round-robin
    selection = select_reference_and_variant()
    ref_file = selection["reference_file"]
    ref_analysis = selection["reference_analysis"]
    style_variant = selection["style_variant"]
    topic_angle = selection["topic_angle"]
    ref_transcript = ref_analysis.get("audio", {}).get("transcript", "")
    target_duration = ref_analysis.get("structure", {}).get("length_seconds", 15.0)

    logger.info(f"Recreating based on reference: '{ref_file}' | Style: '{style_variant}' | Angle: '{topic_angle}'")

    # 2. Quality Gate with 1 retry attempt
    final_output = None
    passed_gate = False
    chosen_script_res = None
    final_duration = target_duration

    for attempt in range(2):
        logger.info(f"Generation attempt {attempt + 1}/2...")
        script_res = generate_recreated_script(
            reference_analysis=ref_analysis,
            style_variant=style_variant,
            topic_angle=topic_angle,
        )
        video_file, audio_file, sub_file, duration = build_and_render_short(
            script_res=script_res,
            target_duration=target_duration,
            out_dir=out_dir,
            reference_transcript=ref_transcript,
        )

        passed, issues = run_quality_gate(
            video_path=video_file,
            script=script_res.script,
            hook=script_res.hook,
            subtitles_path=sub_file,
            audio_path=audio_file,
            target_duration=target_duration,
            reference_transcript=ref_transcript,
        )

        if passed:
            passed_gate = True
            final_output = video_file
            chosen_script_res = script_res
            final_duration = duration
            break
        else:
            logger.warning(f"Quality gate attempt {attempt + 1} failed: {issues}")
            if attempt == 0:
                logger.info("Retrying generation once...")

    if not passed_gate or not final_output or not chosen_script_res:
        error_msg = f"Slot {slot} skipped: Quality gate failed after 2 attempts ({', '.join(issues[:2])})"
        logger.error(error_msg)
        send_alert(error_summary=error_msg, dry_run=dry_run)
        return Path("")

    chosen_title = chosen_script_res.title_options[0]

    # Save metadata info file
    meta_file = final_output.with_suffix(".json")
    post_metadata = {
        "title": chosen_title,
        "title_options": chosen_script_res.title_options,
        "hook": chosen_script_res.hook,
        "script": chosen_script_res.script,
        "description": chosen_script_res.description,
        "tags": chosen_script_res.tags,
        "hashtags": chosen_script_res.hashtags,
        "duration_seconds": final_duration,
        "reference_file": ref_file,
        "style_variant": style_variant,
        "topic_angle": topic_angle,
        "video_file": str(final_output),
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(post_metadata, f, indent=2)

    # 3. Publish Publicly Directly to YouTube
    if dry_run:
        yt_id = "dry_run_id"
        yt_url = "https://youtu.be/dry_run_preview"
        uploaded_at = "DRY_RUN"
        actual_privacy = "public"
        logger.info(f"[DRY-RUN] Would upload to YouTube: {chosen_title}")
    else:
        logger.info(f"Uploading public video directly to YouTube: '{chosen_title}'...")
        yt_res = upload_video(
            video_path=final_output,
            title=chosen_title,
            description=chosen_script_res.description,
            tags=chosen_script_res.tags,
            privacy_status="public",
        )
        yt_id = yt_res["video_id"]
        yt_url = yt_res["video_url"]
        uploaded_at = yt_res["uploaded_at"]
        actual_privacy = yt_res.get("privacy_status", "public")

    # 4. TikTok Dispatch
    tiktok_caption = format_tiktok_caption(
        title=chosen_title,
        hook=chosen_script_res.hook,
        hashtags=chosen_script_res.hashtags,
    )
    tiktok_status = "pending_credentials"
    if not dry_run:
        tiktok_res = post_to_tiktok(
            video_path=final_output,
            title=chosen_title,
            description=tiktok_caption,
            tags=chosen_script_res.tags,
        )
        tiktok_status = tiktok_res.get("status", "pending_credentials")

    # 5. Telegram Dispatch: Send TikTok MP4 file and Real Post Receipt
    send_video(video_path=final_output, caption=f"{chosen_title}\n\n{tiktok_caption}", dry_run=dry_run)

    post_record = {
        "id": yt_id,
        "youtube_id": yt_id,
        "youtube_url": yt_url,
        "platform": "YouTube",
        "title": chosen_title,
        "hook": chosen_script_res.hook,
        "reference_file": ref_file,
        "style_variant": style_variant,
        "topic_angle": topic_angle,
        "slot_time_utc": slot,
        "privacy_status": actual_privacy,
        "status": "published",
        "tiktok_status": tiktok_status,
        "created_at": uploaded_at,
        "video_path": str(final_output),
        "duration_seconds": final_duration,
    }

    send_post_notification(post_record=post_record, dry_run=dry_run)

    if not dry_run:
        add_post(post_record)

    logger.info(f"Slot {slot} successfully completed!")
    return final_output


def cmd_make_short(
    topic: str,
    output_dir: Optional[Path] = None,
    upload: bool = False,
    slot: str = "manual",
    dry_run: bool = False,
) -> Path:
    """Generate an original short video with quality gate and optional public upload."""
    logger.info(f"=== Starting Short Generation for Topic: '{topic}' ===")
    out_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    script_res = generate_short_script(topic=topic)
    final_output, audio_file, sub_file, duration = build_and_render_short(
        script_res=script_res,
        target_duration=30.0,
        out_dir=out_dir,
    )

    passed, issues = run_quality_gate(
        video_path=final_output,
        script=script_res.script,
        hook=script_res.hook,
        subtitles_path=sub_file,
        audio_path=audio_file,
        target_duration=30.0,
    )

    if not passed:
        error_msg = f"Quality gate failed: {', '.join(issues)}"
        logger.error(error_msg)
        send_alert(error_summary=error_msg, dry_run=dry_run)
        return final_output

    chosen_title = script_res.title_options[0]

    if upload:
        if dry_run:
            yt_id = "dry_run_id"
            yt_url = "https://youtu.be/dry_run_preview"
            uploaded_at = "DRY_RUN"
            actual_privacy = "public"
        else:
            yt_res = upload_video(
                video_path=final_output,
                title=chosen_title,
                description=script_res.description,
                tags=script_res.tags,
                privacy_status="public",
            )
            yt_id = yt_res["video_id"]
            yt_url = yt_res["video_url"]
            uploaded_at = yt_res["uploaded_at"]
            actual_privacy = yt_res.get("privacy_status", "public")

        post_record = {
            "id": yt_id,
            "youtube_id": yt_id,
            "youtube_url": yt_url,
            "platform": "YouTube",
            "title": chosen_title,
            "hook": script_res.hook,
            "reference_file": "direct_topic",
            "style_variant": "cinematic_stock_footage",
            "slot_time_utc": slot,
            "privacy_status": actual_privacy,
            "status": "published",
            "created_at": uploaded_at,
            "video_path": str(final_output),
            "duration_seconds": duration,
        }
        send_post_notification(post_record, dry_run=dry_run)
        if not dry_run:
            add_post(post_record)

    return final_output


def cmd_make_long(
    topic: str,
    output_dir: Optional[Path] = None,
    upload: bool = False,
    slot: str = "slot_2",
    dry_run: bool = False,
) -> Path:
    """Generate Phase 6 long-form video in chapters."""
    out_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    long_res = generate_long_script(topic=topic)
    chosen_title = long_res.title_options[0]

    with tempfile.TemporaryDirectory(prefix="timereborn_long_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        all_keywords = []
        full_narration_parts = [long_res.hook]
        for ch in long_res.chapters:
            full_narration_parts.append(ch.script)
            all_keywords.extend(ch.scene_keywords)

        full_script = " ".join(full_narration_parts)
        audio_path = tmp_dir / "voiceover_long.mp3"
        duration = generate_voiceover(text=full_script, output_path=audio_path)

        subtitles_path = tmp_dir / "subtitles_long.ass"
        create_subtitles(
            audio_path=audio_path,
            output_ass_path=subtitles_path,
            script_fallback=full_script,
            total_duration=duration,
            width=1920,
            height=1080,
        )

        scenes = prepare_scene_footage(
            keywords=all_keywords[:12],
            total_duration=duration,
            temp_dir=tmp_dir,
            orientation="horizontal",
        )

        safe_name = "".join(c if c.isalnum() else "_" for c in chosen_title[:30]).strip("_")
        final_output = out_dir / f"long_{safe_name}.mp4"

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

        if upload:
            if dry_run:
                yt_id = "dry_long_id"
                yt_url = "https://youtu.be/dry_long"
                uploaded_at = "DRY_RUN"
            else:
                yt_res = upload_video(
                    video_path=final_output,
                    title=chosen_title,
                    description=long_res.description,
                    tags=long_res.tags,
                    privacy_status="public",
                )
                yt_id = yt_res["video_id"]
                yt_url = yt_res["video_url"]
                uploaded_at = yt_res["uploaded_at"]

            post_record = {
                "id": yt_id,
                "youtube_id": yt_id,
                "youtube_url": yt_url,
                "platform": "YouTube",
                "title": chosen_title,
                "hook": long_res.hook,
                "reference_file": "long_documentary",
                "style_variant": "widescreen_documentary",
                "slot_time_utc": slot,
                "privacy_status": "public",
                "status": "published",
                "created_at": uploaded_at,
                "video_path": str(final_output),
                "duration_seconds": duration,
            }
            send_post_notification(post_record, dry_run=dry_run)
            if not dry_run:
                add_post(post_record)

        return final_output


def cmd_poll_telegram():
    """Poll Telegram for user commands."""
    handled = poll_telegram_events()
    logger.info(f"Processed {handled} telegram updates.")


def cmd_comments():
    """Process comments pipeline."""
    count = process_comments_pipeline()
    logger.info(f"Processed {count} comments.")


def cmd_analytics(dry_run: bool = False):
    """Run analytics and learning loop."""
    collect_milestone_analytics()
    run_learning_loop()
    send_daily_summary(dry_run=dry_run)


def cmd_repost(url: str, slot: str = "manual", dry_run: bool = False):
    """Execute TikTok repost pipeline."""
    from src.repost import repost_from_url
    res = repost_from_url(tiktok_url=url, slot=slot, dry_run=dry_run)
    logger.info(f"Repost completed with result: {res.get('status', 'success')}")


def main():
    parser = argparse.ArgumentParser(description="Timereborn autonomous content agent CLI")
    parser.add_argument("--dry-run", action="store_true", help="Print messages to console instead of sending to Telegram/YouTube")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # make-short
    p_short = subparsers.add_parser("make-short", help="Generate an original vertical short video")
    p_short.add_argument("--topic", required=True, help="Topic or concept for the video")
    p_short.add_argument("--output-dir", default="output", help="Directory to save finished MP4")
    p_short.add_argument("--upload", action="store_true", help="Upload to YouTube and deliver to Telegram")
    p_short.add_argument("--slot", default="manual", help="Posting slot label")
    p_short.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # make-long
    p_long = subparsers.add_parser("make-long", help="Generate an original long horizontal video")
    p_long.add_argument("--topic", required=True, help="Topic for long video")
    p_long.add_argument("--output-dir", default="output", help="Directory to save finished MP4")
    p_long.add_argument("--upload", action="store_true", help="Upload to YouTube and deliver to Telegram")
    p_long.add_argument("--slot", default="slot_2", help="Posting slot label")
    p_long.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # post-slot
    p_slot = subparsers.add_parser("post-slot", help="Execute scheduled posting slot")
    p_slot.add_argument("--slot", default="slot_1", help="Slot ID from settings.yml")
    p_slot.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # repost
    p_repost = subparsers.add_parser("repost", help="Repost a TikTok video with fresh metadata to YouTube Shorts & TikTok")
    p_repost.add_argument("--url", required=True, help="TikTok video URL to repost")
    p_repost.add_argument("--slot", default="manual", help="Posting slot label")
    p_repost.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # analytics
    p_analytics = subparsers.add_parser("analytics", help="Collect metrics and run learning loop")
    p_analytics.add_argument("--dry-run", action="store_true", help="Dry run mode")

    # comments
    subparsers.add_parser("comments", help="Process and reply to comments")

    # poll-telegram
    subparsers.add_parser("poll-telegram", help="Poll Telegram for commands")

    args = parser.parse_args()
    is_dry = args.dry_run or getattr(args, "dry_run", False)
    if is_dry:
        os.environ["DRY_RUN"] = "1"

    if args.command == "make-short":
        cmd_make_short(
            topic=args.topic,
            output_dir=Path(args.output_dir),
            upload=args.upload,
            slot=args.slot,
            dry_run=is_dry,
        )
    elif args.command == "make-long":
        cmd_make_long(
            topic=args.topic,
            output_dir=Path(args.output_dir),
            upload=args.upload,
            slot=args.slot,
            dry_run=is_dry,
        )
    elif args.command == "post-slot":
        cmd_post_slot(slot=args.slot, dry_run=is_dry)
    elif args.command == "repost":
        cmd_repost(url=args.url, slot=args.slot, dry_run=is_dry)
    elif args.command == "analytics":
        cmd_analytics(dry_run=is_dry)
    elif args.command == "comments":
        cmd_comments()
    elif args.command == "poll-telegram":
        cmd_poll_telegram()


if __name__ == "__main__":
    main()

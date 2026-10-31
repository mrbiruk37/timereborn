# Timereborn ⏳

**Timereborn** is an autonomous, $0-budget AI content engine running on GitHub Actions with your PC turned off. It studies reference videos from `video_idea/`, analyzes their structure, and recreates 100% original vertical videos matching their pacing and hook while rotating across distinct visual styles. Videos are vetted by an automated Quality Gate and published directly to YouTube and dispatched to Telegram with real metrics and plain text reports.

---

## 🔒 Hard Rules & Ethics

1. **Originality Guarantee:** Reference videos in `video_idea/` are studied strictly for structural pacing, beats, and hooks. **Zero** footage, audio, voice, or text from references is reused. All scripts are written fresh by the LLM and vetted by an n-gram similarity check before rendering.
2. **Real Data Only:** No test, demo, sample, mock, or placeholder messages are ever sent to Telegram. Milestone celebrations and emojis are omitted. Numbers (views, likes, comments) originate strictly from real API responses saved in `stats.json`.
3. **Automated Quality Gate:** Every video passes automated checks (duration bounds, audio track presence, subtitle dialogues, no black frames, script length matching pacing, and LLM self-review) before posting.
4. **Public Posting:** Videos are published directly as Public on YouTube, and the TikTok-ready MP4 is delivered to Telegram.
5. **Zero Secrets in Git:** All API keys and tokens are stored in environment variables (local `.env` in development, GitHub Secrets in CI).

---

## 📁 Adding Reference Videos (`video_idea/`)

The repository includes a `video_idea/` folder containing reference videos (`.mp4`, `.mov`, `.webm`):

1. Place your reference video into the `video_idea/` folder.
2. Ensure each file is under **50 MB** (GitHub limit is 100 MB).
3. Commit and push:
   ```bash
   git add video_idea/
   git commit -m "add reference video"
   git push origin main
   ```
4. On the next scheduled run, the engine computes the SHA-256 hash, extracts technical and audio metrics, reverse-engineers the beats and hook, and caches the result in `data/reference_analysis.json`. Files with matching hashes are never re-analyzed.

---

## 🎨 Recreate Engine & Visual Styles

Each run selects the next reference video in a round-robin rotation and pairs it with an unused visual style from `config/settings.yml`:

- `cinematic_stock_footage`: High-contrast dynamic B-roll with pan/zoom.
- `minimal_text_on_screen`: Moody backgrounds with typographic highlights.
- `kinetic_typography`: Fast-moving rhythmic animated text sequences.
- `image_zoom_storytelling`: Push-in/pull-back pans across statues and artworks.
- `animated_diagrams`: Minimalist schematics and blueprint motion.
- `split_screen_comparison`: Side-by-side contrast between ancient reality and modern tech.

Style selection incorporates performance insights from `data/learning.json` with a 30% exploration rate for experimental styles.

---

## 🛡️ Automated Quality Gate

Before any video is published, `src/quality_gate.py` runs automated verification:

1. **Duration Bounds:** Confirms duration is within `min_duration_sec` and `max_duration_sec` from `settings.yml`.
2. **Audio Track:** Probes the rendered file to verify audio track existence and volume.
3. **Captions:** Ensures the generated `.ass` file contains valid dialogue entries.
4. **Black Segments:** Scans the stream for continuous black frames via FFmpeg `blackdetect`.
5. **Script Similarity:** Verifies n-gram similarity against the reference transcript is below `0.15`.
6. **LLM Editorial Review:** Checks for strong opening hooks, detects placeholder text, and flags factual anomalies.

If a video fails the gate, the engine regenerates it once. If it fails a second time, the slot is skipped and a short 1-line error message is sent to Telegram.

---

## 📱 Telegram Commands & Notifications

Owner Telegram commands:
- `/pause` – Suspends scheduled posting slots.
- `/resume` – Resumes scheduled posting slots.
- `/stats` – Reports real 7-day stats (videos, views, likes, comments) from `stats.json`.
- `/idea <concept>` – Adds a user idea to the backlog.

Post notification format:
```text
Posted to YouTube
Title: <title>
Link: <url>
Slot: <slot>
Based on: <reference_file> | Style: <style_variant>
```

---

## 🧪 Local Testing & Dry-Run Mode

You can test any command locally without publishing or sending real Telegram messages using `--dry-run`:

```bash
# Test scheduled slot recreation in dry-run mode
python -m src.main post-slot --slot slot_1 --dry-run

# Test generating a standalone short in dry-run mode
python -m src.main make-short --topic "Nikola Tesla reborn" --dry-run

# Run full pytest test suite (all tests mock Telegram network calls)
python -m pytest
```

---

## ⚙️ Configuration (`config/settings.yml`)

```yaml
niche: "TimeReborn: Iconic historical figures reborn in the modern world"
reference_dir: "video_idea"

quality_gate:
  min_duration_sec: 12
  max_duration_sec: 60
  max_ngram_similarity: 0.15
  require_audio: true
  require_captions: true

vision:
  provider: "gemini"
  model: "gemini-1.5-flash"
```

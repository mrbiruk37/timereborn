# Timereborn ⏳✨

**Timereborn** is an autonomous, $0-budget AI content engine designed to run 24/7 on GitHub Actions with your PC turned off. It researches viral patterns, generates 100% original video scripts, synthesizes natural neural voices, burns synchronized word-level captions, fetches free licensed stock footage, renders vertical Shorts & horizontal videos, and distributes them to YouTube and Telegram.

---

## 🔒 Hard Rules & Ethics

1. **Originality Guarantee:** Reference channels are studied strictly for titles, hooks, stats, and transcripts to identify winning themes. **Zero** creator audio, video, or script text is ever reused. All scripts are written fresh by the LLM.
2. **Official APIs Only:** Uses official YouTube Data API v3, YouTube Analytics API, Telegram Bot API, Pixabay API, and Groq API. No browser automation or brittle scraping.
3. **Zero Secrets in Git:** Secrets are read strictly from environment variables (local `.env` in development, GitHub Repository Secrets in CI).
4. **AI Content Disclosure:** Transparently discloses AI generation in YouTube metadata and description.
5. **Free-Tier Protection:** Respects YouTube's 10,000 daily quota units, caches stock footage, and retries with exponential backoff.

---

## 🛠 Tech Stack

- **Runtime:** Python 3.11+
- **LLM Engine:** Groq API (`llama-3.3-70b-versatile`) with structured JSON validation
- **Voiceover:** `edge-tts` (Microsoft neural voices, 100% free, no key required)
- **Subtitles:** `faster-whisper` (word-level timestamps to `.ass` subtitles)
- **Footage:** Pixabay API (HD video clips & Ken Burns pan/zoom images)
- **Video Rendering:** FFmpeg (1080x1920 9:16 Shorts & 1920x1080 16:9 videos)
- **Automation:** GitHub Actions (scheduled UTC slots + daily commit keepalive)

---

## 🔑 Required Secrets & Environment Variables

| Variable | Description | Where to Obtain |
|---|---|---|
| `GROQ_API_KEY` | Groq Cloud API Key | [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | LLM Model (Default: `llama-3.3-70b-versatile`) | Groq Console |
| `PIXABAY_API_KEY` | Pixabay API Key for free stock video/images | [pixabay.com/api/docs](https://pixabay.com/api/docs/) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Your Telegram Chat ID for alerts and videos | `@userinfobot` on Telegram |
| `YT_CLIENT_ID` | Google OAuth 2.0 Client ID | Google Cloud Console |
| `YT_CLIENT_SECRET` | Google OAuth 2.0 Client Secret | Google Cloud Console |
| `YT_REFRESH_TOKEN` | YouTube OAuth Refresh Token | Generated via `scripts/get_youtube_token.py` |

---

## 📁 Repository Structure

```
timereborn/
├── .github/workflows/
│   ├── post.yml              # Scheduled video generation & posting slots
│   ├── analytics.yml         # 24h & 72h stats collection and learning loop
│   └── telegram_poll.yml     # Interactive approval & Telegram bot commands
├── config/
│   ├── settings.yml          # Niche, language, slots, voice, limits, mode (approve/auto)
│   └── sources.yml           # Reference YouTube channels to study for ideas
├── data/
│   ├── ideas.json            # Backlog of queued and brainstormed video ideas
│   ├── posts.json            # History of rendered and published videos
│   ├── stats.json            # Analytics snapshots (views, likes, retention)
│   ├── comments.json         # Viewer comments, sentiment, and drafted replies
│   └── learning.json         # Self-improving insights (winning hooks, topics, lengths)
├── src/
│   ├── state.py              # Safe atomic state management
│   ├── scriptgen.py          # Groq LLM script generation with JSON validation
│   ├── voice.py              # edge-tts voiceover generation
│   ├── captions.py           # faster-whisper word-level subtitle generation (.ass)
│   ├── footage.py            # Pixabay provider, cache, and Ken Burns generator
│   ├── render.py             # FFmpeg video compositor (9:16 Shorts / 16:9 long)
│   ├── main.py               # CLI entrypoint for local execution and CI slots
│   ├── youtube.py            # (Phase 2) Official YouTube v3 upload & stats
│   ├── telegram.py           # (Phase 2) Telegram bot notifications & video delivery
│   ├── analytics.py          # (Phase 4) Metrics collector
│   ├── comments.py           # (Phase 5) Sentiment classification & auto-replies
│   └── learn.py              # (Phase 4) Self-learning feedback loop
├── tests/                    # Pytest unit tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 🚀 Phase 1: Local CLI Testing Guide

### 1. Configure Local Environment
Copy `.env.example` to `.env` and fill in your `GROQ_API_KEY`:
```bash
cp .env.example .env
```
*(Optional for Phase 1: `PIXABAY_API_KEY`. If omitted, the engine automatically uses sleek high-contrast cinematic visual backgrounds with hook animations).*

### 2. Run Test Suite
Verify that state management, JSON parsing, and captions logic are passing:
```bash
python -m pytest tests/
```

### 3. Generate a Finished Short Video
Run the CLI to generate a complete, ready-to-watch 1080x1920 MP4:
```bash
python -m src.main make-short --topic "The Stoic Secret to Conquering Overthinking"
```

The resulting video and metadata will be placed in `output/`:
- `output/short_<title>.mp4`: 1080x1920 vertical video with neural narration, burned word-level subtitles, hook overlay, and visual footage.
- `output/short_<title>.json`: Complete metadata payload with description, title options, and tags.

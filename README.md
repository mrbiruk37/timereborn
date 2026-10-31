# Timereborn ⏳✨

**Timereborn** is a complete, autonomous, $0-budget AI content creator designed to run 24/7 on GitHub Actions with your PC turned off. It researches viral concepts from reference channels, writes 100% original vertical Shorts and 16:9 horizontal documentary videos, synthesizes natural neural voices, generates word-level captions, fetches free licensed stock footage, uploads to YouTube, delivers TikTok-ready videos to Telegram, interacts with viewers via auto-replies, and learns from audience analytics to self-improve over time.

---

## 🔒 Hard Rules & Ethics

1. **Originality Guarantee:** Reference channels are studied strictly for titles, hooks, stats, and transcripts to identify winning themes. **Zero** creator audio, video, or script text is ever reused. All scripts are written fresh by the LLM.
2. **Official APIs Only:** Uses official YouTube Data API v3, YouTube Analytics API, Telegram Bot API, Pixabay API, and Groq API. No browser automation or fragile web scraping.
3. **TikTok Delivery:** Sends the rendered vertical MP4 with caption and hashtags to your Telegram for easy 1-click mobile posting (no unofficial TikTok APIs).
4. **Zero Secrets in Git:** Secrets are read strictly from environment variables (local `.env` in development, GitHub Repository Secrets in CI).
5. **AI Content Disclosure:** Transparently discloses AI generation in YouTube metadata and description.
6. **Free-Tier Protection:** Respects YouTube's 10,000 daily quota units, caches stock footage, and retries with exponential backoff.

---

## 🛠 Tech Stack

- **Runtime:** Python 3.11+
- **LLM Engine:** Groq API (`openai/gpt-oss-120b` or `qwen/qwen3.8-27b`) with Pydantic JSON validation
- **Voiceover:** `edge-tts` (Microsoft neural voices, 100% free, no key required)
- **Subtitles:** `faster-whisper` (word-level timestamps to `.ass` subtitles with proportional fallback)
- **Footage:** Pixabay API (HD landscape/vertical video clips & Ken Burns pan/zoom images)
- **Video Rendering:** FFmpeg (1080x1920 9:16 Shorts & 1920x1080 16:9 long documentaries)
- **Automation:** GitHub Actions (scheduled UTC slots + daily keepalive commit)

---

## 🔑 Required Secrets & Environment Variables

| Variable | Description | Where to Obtain |
|---|---|---|
| `GROQ_API_KEY` | Groq Cloud API Key | [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | LLM Model (Default: `openai/gpt-oss-120b`) | Groq Console |
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
│   ├── post.yml              # Scheduled video slots (13:00, 17:00, 22:00 UTC)
│   ├── analytics.yml         # Daily stats collection, comments, & learning loop (06:00 UTC)
│   └── telegram_poll.yml     # Telegram approval polling & bot commands (every 15 min)
├── config/
│   ├── settings.yml          # Niche, slots, voice, limits, mode (approve/auto)
│   └── sources.yml           # Reference YouTube channels to study for ideas
├── data/
│   ├── ideas.json            # Backlog of queued and brainstormed video ideas
│   ├── posts.json            # History of rendered and published videos
│   ├── stats.json            # Analytics snapshots (views, likes, retention)
│   ├── comments.json         # Viewer comments, classification, and drafted replies
│   └── learning.json         # Self-improving insights (winning hooks, topics, lengths)
├── src/
│   ├── state.py              # Safe atomic state management
│   ├── scriptgen.py          # Groq LLM script generation with JSON validation (Short & Long)
│   ├── voice.py              # edge-tts voiceover generation
│   ├── captions.py           # faster-whisper word-level subtitle generation (.ass)
│   ├── footage.py            # Pixabay provider, cache, and Ken Burns generator
│   ├── render.py             # FFmpeg video compositor (9:16 Shorts / 16:9 long)
│   ├── youtube.py            # Official YouTube v3 resumable upload & privacy control
│   ├── telegram.py           # Telegram bot notifications & TikTok video delivery
│   ├── telegram_poll.py      # Interactive Telegram buttons & bot commands
│   ├── research.py           # Reference channels research via Data API
│   ├── ideas.py              # Ideas queue, deduplication, & 70/30 selection
│   ├── analytics.py          # Metrics collector (24h/72h milestones)
│   ├── comments.py           # Sentiment classification & auto-replies (max 15/day)
│   ├── learn.py              # Self-learning feedback loop & daily Telegram summary
│   └── main.py               # Unified CLI dispatcher
├── scripts/
│   └── get_youtube_token.py  # Local one-time OAuth token generator
├── tests/                    # 42 Pytest unit tests across all modules
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 🤖 Telegram Bot Commands & Approval Flow

The Telegram bot handles both interactive approval buttons and administrative commands via `telegram_poll.yml`:

| Command / Action | Description |
|---|---|
| `✅ Approve (Publish)` | Changes YouTube video privacy from **Private** to **Public**. |
| `❌ Reject (Delete)` | Deletes the private upload from YouTube and cancels publication. |
| `✅ Send Reply` | Approves and posts a drafted comment reply on YouTube. |
| `❌ Dismiss` | Dismisses a drafted comment reply. |
| `/pause` | Temporarily suspends scheduled posting slots. |
| `/resume` | Resumes automated posting slots. |
| `/stats` | Sends a summary of the channel's performance over the last 7 days. |
| `/idea <text or link>` | Submits a new concept or inspiration link to the ideas backlog. |
| `/mode approve` | Sets upload mode to Private + Telegram interactive approval. |
| `/mode auto` | Sets upload mode to direct Public release. |

---

## 🎬 CLI Reference

### 1. Generate Vertical Short (Phase 1 & 2)
```powershell
# Local render only
python -m src.main make-short --topic "The Stoic Secret to Conquering Overthinking"

# Render + YouTube Upload + Telegram Delivery
python -m src.main make-short --topic "Marcus Aurelius Morning Habit" --upload
```

### 2. Generate 16:9 Long Documentary (Phase 6)
```powershell
# Local 16:9 widescreen render (chapters + horizontal footage)
python -m src.main make-long --topic "The Rise of Marcus Aurelius"

# Render + YouTube Upload
python -m src.main make-long --topic "The Rise of Marcus Aurelius" --upload
```

### 3. Execute Scheduled Slot (Phase 3 & 4)
```powershell
# Slot 1 (13:00 UTC) = Short
python -m src.main post-slot --slot slot_1

# Slot 2 (17:00 UTC) = Long Documentary
python -m src.main post-slot --slot slot_2
```

### 4. Run Daily Analytics & Self-Learning (Phase 4)
```powershell
python -m src.main analytics
```

### 5. Process Viewer Comments & Auto-Replies (Phase 5)
```powershell
python -m src.main comments
```

### 6. Poll Telegram Callbacks & Commands (Phase 5)
```powershell
python -m src.main poll-telegram
```

---

## 🧪 Running the Complete Test Suite

Run all 42 unit tests with pytest:
```powershell
python -m pytest tests/
```

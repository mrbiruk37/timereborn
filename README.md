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
│   ├── youtube.py            # Official YouTube v3 resumable upload & privacy control
│   ├── telegram.py           # Telegram bot notifications & TikTok video delivery
│   ├── main.py               # CLI entrypoint for local execution and CI slots
│   ├── research.py           # (Phase 4) Reference channels research via Data API
│   ├── ideas.py              # (Phase 4) Ideas queue & deduplication
│   ├── analytics.py          # (Phase 4) Metrics collector (24h/72h)
│   ├── comments.py           # (Phase 5) Sentiment classification & auto-replies
│   └── learn.py              # (Phase 4) Self-learning feedback loop
├── scripts/
│   └── get_youtube_token.py  # Local one-time OAuth token generator
├── tests/                    # Pytest unit tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 🔑 Phase 2 Setup: YouTube & Telegram

### 1. Generate YouTube OAuth Refresh Token
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Create OAuth 2.0 Credentials:
   - Application type: **Desktop app**.
   - Copy the Client ID and Client Secret.
4. Set `YT_CLIENT_ID` and `YT_CLIENT_SECRET` in your `.env` file (or download `client_secrets.json`).
5. Run the local authentication script:
   ```powershell
   python scripts/get_youtube_token.py
   ```
   A browser window will open. Authorize your channel. Copy the returned `YT_REFRESH_TOKEN` into your `.env` file and GitHub Secrets.

### 2. Configure Telegram Bot
1. Open Telegram and message `@BotFather`.
2. Send `/newbot`, follow prompts, and copy the Bot Token (`TELEGRAM_BOT_TOKEN`).
3. Send a message to `@userinfobot` to retrieve your numeric user ID (`TELEGRAM_CHAT_ID`).
4. Start a chat with your new bot and click **Start**.
5. Save both to `.env` and GitHub Secrets.

---

## 🧪 Testing Phase 2

### 1. Run Complete Test Suite
```powershell
python -m pytest tests/
```
All 21 unit tests covering state, LLM parsing, captions, Telegram, and YouTube will execute with mock fixtures.

### 2. Test Local Render + Upload (Approve Mode)
Set your credentials in `.env` and run:
```powershell
python -m src.main make-short --topic "The Stoic Art of Letting Go" --upload
```

**What happens:**
1. Generates original script + neural voice + word-level captions + footage.
2. Renders 1080x1920 MP4 into `output/`.
3. Uploads the video to YouTube as **PRIVATE** (in approve mode).
4. Sends the **TikTok-ready MP4** to your Telegram with the complete caption and hashtags for 1-click mobile posting.
5. Sends an **Approval Request** with inline buttons:
   - `✅ Approve (Publish)`
   - `❌ Reject (Delete)`
6. Logs the post into `data/posts.json` with status `pending_approval`.

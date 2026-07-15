# Deployment Guide

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key for Gemini models. Powers resume analysis/tailoring, cover letters, job metadata, inbox classification. The app will refuse to do anything AI-related without this. |

### Optional — Command Center (job discovery & scoring)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude, used by `_score_jobs_with_claude()` to score/rank auto-discovered jobs. Without it, `/api/jobs/auto-search` will fail at the scoring step. |
| `RAPIDAPI_KEY` | RapidAPI key for the JSearch job-search API — Command Center's primary job source (200 requests/month on the free tier, tracked in the Usage dashboard). Falls back to a DuckDuckGo scrape if unset, but that fallback is lower quality/volume. |

### Optional — Email Drafting

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o-mini email draft/follow-up generation (`services/ollama_service.py` — despite the filename, this is OpenAI, not Ollama). |

### Optional — Gmail Integration

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth2 client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth2 client secret |
| `GMAIL_REDIRECT_URI` | OAuth2 callback URL (default: `http://localhost:8000/api/gmail/callback`) |

### Optional — Telegram Bot

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather. Enables JD scanning via Telegram, the Action-Queue digest loop, and the daily auto-search digest. |

### Optional — Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Directory for database, logs, usage tracking, and all the background-loop bookkeeping JSON files |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hostnames |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS origins |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for OAuth redirects |
| `ENVIRONMENT` | (unset) | Set to `development` for auto-reload |

### Present but unused

`.env.example` also lists `OLLAMA_URL` (no code path actually calls Ollama — see the naming note above) and `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_WHATSAPP_NUMBER` are read by `services/whatsapp_service.py`, but that service is never imported by `main.py` — it's dead code. Don't spend time configuring either unless you're the one wiring them up.

## PDF Generation Requirement

Every resume scan also produces a PDF copy alongside the tailored `.docx`, via `docx2pdf` driving MS Word through COM automation. This **only works on Windows with MS Word installed**. `requirements.txt` pins `docx2pdf`/`pywin32` with `; sys_platform == "win32"`, so:

- On Windows dev machines with Word: PDF generation works out of the box.
- Inside the Linux/Alpine Docker image (or any non-Windows host): those packages are skipped entirely at install time, and `_convert_docx_to_pdf()` silently no-ops (best-effort, never blocks a scan) — you'll just never get a `pdf_path` back.

If you need PDF generation inside Docker, this would need to be swapped for a cross-platform converter (e.g. LibreOffice headless) — that's a real architecture change, not a config toggle.

## Local Development Setup

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Edit .env with your API keys

# Run the server
python main.py
# Or with auto-reload:
python main.py --reload
```

The backend starts on `http://localhost:8000`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The frontend starts on `http://localhost:5173` (Vite will pick the next free port, e.g. 5174, if 5173 is already in use).

### Docker Compose

```bash
# From project root
docker-compose down && docker-compose up --build
```

`docker-compose.yml` mounts `backend/data`, `backend/original`, `backend/trailerd`, **and** `backend/online-platform` (Command Center's output root) as volumes, and the backend container has a `wget`-based healthcheck the frontend container waits on before starting.

## Directory Structure at Runtime

```
backend/
├── data/                    # Created automatically
│   ├── resumes.db           # SQLite database (single `resumes` table, all 4 products)
│   ├── history.csv          # History export
│   ├── api_usage.json       # Cost tracking (Gemini + Claude + OpenAI + JSearch quota)
│   ├── profile.txt          # User profile
│   ├── gmail_tokens.json    # OAuth tokens (auto-created)
│   ├── documents/           # DL/GC uploads
│   ├── last_scan.json               # Command Center: last auto-search result
│   ├── daily_search_schedule.json   # Command Center: automation schedule
│   ├── telegram_notified_ids.json   # Telegram: Action Queue dedup
│   ├── inbox_classify_cache.json    # Gmail inbox: AI classification cache
│   ├── inbox_reply_seen.json        # Gmail inbox: reply-matching dedup
│   ├── inbox_reply_matches.json     # Gmail inbox: matched replies
│   └── logs/
│       └── app.log          # Application logs
├── original/                # Created automatically
│   └── *.docx               # Uploaded base resumes
├── trailerd/                # Created automatically — Dashboard/Job Finder output
│   └── <Company_Name>/      # Per-company output
│       ├── Teja_Mahesh_Neerukonda_Resume.docx
│       ├── Teja_Mahesh_Neerukonda_Resume.pdf   # Windows + Word only
│       ├── jd_info.txt
│       ├── difference.txt
│       ├── cover_letter_*.docx
│       └── mail_draft_*.txt
└── online-platform/         # Created automatically — Command Center output
    └── <Company_Name>_<job_id>/   # Deterministic per-job folder
        └── (same artifact types as trailerd/)
```

## Gmail OAuth2 Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select existing
3. Enable the **Gmail API**
4. Go to **Credentials** > **Create Credentials** > **OAuth 2.0 Client IDs**
5. Application type: **Web application**
6. Add authorized redirect URI: `http://localhost:8000/api/gmail/callback`
7. Copy the Client ID and Client Secret to your `.env` file
8. In the app, click "Connect Gmail" — you'll be redirected to Google consent

**Scopes used:** compose (drafts), read (inbox search/threads/summaries), and label/modify (archive, mark-read, apply labels — used by the Inbox page's organize actions).

## Telegram Bot Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token to `TELEGRAM_BOT_TOKEN` in `.env`
4. Restart the backend — the bot starts long-polling automatically, and the 30-minute Action Queue digest loop starts alongside it
5. Search for your bot in Telegram and send `/start`

The bot processes any text message as a job description and replies with the scan result; `/matches`, `/followups`, and `/queue` surface Command Center summaries.

## Command Center Setup (job discovery)

1. Get a RapidAPI key and subscribe to the JSearch API, then set `RAPIDAPI_KEY` — this is Command Center's primary job source (free tier: 200 requests/month, tracked under `jsearch_quota` in `/api/usage`).
2. Get an Anthropic API key and set `ANTHROPIC_API_KEY` — required for job scoring/ranking (`/api/jobs/auto-search` and `/api/jobs/{id}/rescore` both fail without it).
3. Optionally configure the daily auto-search schedule via `POST /api/automation/schedule` (or the Command Center UI) — default is 10:00 AM America/New_York, query "DevOps Engineer" across linkedin/dice/indeed/ziprecruiter.
4. If Gmail is connected, the inbox-reply-matching loop starts automatically — no separate setup needed.

## API Cost Tracking

The system tracks all AI API calls (Gemini, Claude, and OpenAI) in `data/api_usage.json`, plus a separate JSearch free-tier quota counter:

| Model | Input Price | Output Price |
|-------|-----------|-------------|
| Gemini quality model | varies — see `services/model_config.py` and current Google pricing | |
| Gemini fast model | varies — see `services/model_config.py` and current Google pricing | |
| claude-sonnet-5 | see current Anthropic pricing | |
| gpt-4o-mini | $0.15/M tokens | $0.60/M tokens |

View costs in the app via the **$ Usage** tab, or query `GET /api/usage`.

## Production Considerations

### Security

- Change `ALLOWED_HOSTS` to your actual domain
- Change `ALLOWED_ORIGINS` to your frontend URL
- Set `GMAIL_REDIRECT_URI` to your production callback URL
- Use HTTPS in production (HSTS headers are already set)
- The SQLite database and Gmail tokens contain sensitive data — restrict file permissions
- The frontend hardcodes `http://localhost:8000` as its API base URL in every component (no env-based config) — this needs a real fix before deploying the frontend anywhere but localhost, not just an environment variable change

### Rate Limits

All endpoints are rate-limited via SlowAPI. Limits are per-IP:
- Scan operations: 3-10/minute
- AI generation (cover letter, email, follow-up): 5/minute
- Read operations: 30-60/minute

### Logging & Metrics

Logs are written to both `data/logs/app.log` and stdout. Format:
```
2024-06-15 10:30:00 - __main__ - INFO - Resume uploaded: devops_resume.docx
```

Prometheus metrics are exposed at `/metrics` via `prometheus-fastapi-instrumentator`.

### Background Loops in Production

Four `asyncio` background tasks run for the life of the process (see [System Architecture](System_Architecture.md#background-jobs)): Telegram polling, Telegram Action-Queue digest, the daily Command Center auto-search scheduler, and the Gmail inbox-reply matcher. With `uvicorn --workers 1` (as set in the Dockerfile), there's exactly one instance of each loop. **Do not scale this service to multiple workers/replicas without addressing that** — each additional worker would spin up its own copies of all four loops, causing duplicate Telegram messages, duplicate auto-searches, and duplicate inbox-reply notifications.

### Backup

Back up these files to preserve all data:
- `data/resumes.db` — All history and scan records (Dashboard, Job Finder, Command Center, manual — all four products)
- `data/api_usage.json` — Cost tracking
- `data/gmail_tokens.json` — Gmail OAuth tokens
- `data/profile.txt` — User profile
- `data/daily_search_schedule.json` — Command Center automation schedule (won't survive a fresh volume without this)
- `original/` — Base resume files
- `trailerd/` and `online-platform/` — All generated outputs (resumes, PDFs, cover letters, mail drafts)

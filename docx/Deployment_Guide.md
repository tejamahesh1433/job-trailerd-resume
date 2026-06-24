# Deployment Guide

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key for Gemini models. The app will refuse to start without this. |

### Optional — Email Drafting

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o-mini email draft generation |

### Optional — Gmail Integration

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth2 client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth2 client secret |
| `GMAIL_REDIRECT_URI` | OAuth2 callback URL (default: `http://localhost:8000/api/gmail/callback`) |

### Optional — Telegram Bot

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |

### Optional — Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Directory for database, logs, usage tracking |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hostnames |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS origins |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for OAuth redirects |
| `ENVIRONMENT` | (unset) | Set to `development` for auto-reload |

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
pip install fastapi uvicorn python-dotenv python-docx pdfplumber
pip install google-genai openai httpx slowapi
pip install google-auth google-auth-oauthlib google-api-python-client

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

The frontend starts on `http://localhost:5173`.

### Docker Compose

```bash
# From project root
docker-compose down && docker-compose up --build
```

## Directory Structure at Runtime

```
backend/
├── data/                    # Created automatically
│   ├── resumes.db           # SQLite database
│   ├── history.csv          # History export
│   ├── api_usage.json       # Cost tracking
│   ├── profile.txt          # User profile
│   ├── gmail_tokens.json    # OAuth tokens (auto-created)
│   ├── documents/           # DL/GC uploads
│   └── logs/
│       └── app.log          # Application logs
├── original/                # Created automatically
│   └── *.docx               # Uploaded base resumes
└── trailerd/                # Created automatically
    └── <Company_Name>/      # Per-company output
        ├── resume.docx
        ├── jd_info.txt
        ├── difference.txt
        ├── cover_letter_*.docx
        └── mail_draft_*.txt
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

**Required scopes:**
- `https://www.googleapis.com/auth/gmail.compose` — Create drafts
- `https://www.googleapis.com/auth/gmail.readonly` — Read inbox for follow-up

## Telegram Bot Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token to `TELEGRAM_BOT_TOKEN` in `.env`
4. Restart the backend — the bot starts long-polling automatically
5. Search for your bot in Telegram and send `/start`

The bot processes any text message as a job description and replies with the scan result.

## API Cost Tracking

The system tracks all AI API calls in `data/api_usage.json`:

| Model | Input Price | Output Price |
|-------|-----------|-------------|
| gemini-2.5-pro | $1.25/M tokens | $10.00/M tokens |
| gemini-2.5-flash | $0.15/M tokens | $0.60/M tokens |
| gpt-4o-mini | $0.15/M tokens | $0.60/M tokens |
| gpt-4o | $2.50/M tokens | $10.00/M tokens |

View costs in the app via the **$ Usage** tab, or query `GET /api/usage`.

## Production Considerations

### Security

- Change `ALLOWED_HOSTS` to your actual domain
- Change `ALLOWED_ORIGINS` to your frontend URL
- Set `GMAIL_REDIRECT_URI` to your production callback URL
- Use HTTPS in production (HSTS headers are already set)
- The SQLite database and Gmail tokens contain sensitive data — restrict file permissions

### Rate Limits

All endpoints are rate-limited via SlowAPI. Limits are per-IP:
- Scan operations: 3-10/minute
- AI generation (cover letter, email): 5/minute
- Read operations: 30-60/minute

### Logging

Logs are written to both `data/logs/app.log` and stdout. Format:
```
2024-06-15 10:30:00 - __main__ - INFO - Resume uploaded: devops_resume.docx
```

### Backup

Back up these files to preserve all data:
- `data/resumes.db` — All history and scan records
- `data/api_usage.json` — Cost tracking
- `data/gmail_tokens.json` — Gmail OAuth tokens
- `data/profile.txt` — User profile
- `original/` — Base resume files
- `trailerd/` — All generated outputs

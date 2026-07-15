# TRAILERD - Job Tailored Resume System

Comprehensive documentation for the **TRAILERD** project — an AI-powered job-application platform covering resume tailoring, job discovery/scoring, application tracking, and recruiter communication.

## Documentation Index

| Document | Description |
|----------|-------------|
| [System Architecture](System_Architecture.md) | High-level system overview, component interaction, background jobs, and security |
| [Backend Architecture](Backend_Architecture.md) | FastAPI backend, service modules, database schema, file layout |
| [Frontend Architecture](Frontend_Architecture.md) | React SPA page structure, state management, and UI flow |
| [API Documentation](API_Documentation.md) | Complete REST API reference with request/response schemas |
| [Data Flow & Sequences](Data_Flow_Sequences.md) | Sequence diagrams for all major workflows |
| [Deployment Guide](Deployment_Guide.md) | Environment setup, configuration, and deployment instructions |

## Project Overview

TRAILERD automates the job-application workflow end to end, across four connected products that share one backend and one database table:

1. **Resume Tailor (Dashboard)** — Paste a job description, select a base resume, and the system uses Gemini to analyze ATS compatibility, rewrite bullet points to close keyword gaps, and produce a tailored resume — as a friendly-named `.docx` **and** a matching PDF.
2. **Command Center** — The app's home screen. Runs a scheduled or on-demand auto-search across job boards (JSearch/RapidAPI, with a DuckDuckGo scrape fallback), scores every posting with **Claude**, and tracks each one through a 7-stage pipeline (Discovered → Matched → Saved → Applied → Interview → Offer → Rejected). Includes an Action Queue, automation scheduling, and an AI-monitored Gmail inbox that auto-matches recruiter replies to tracked applications.
3. **Job Finder (Job Matcher)** — The original, simpler pre-screening flow: paste one JD or a URL, get an instant pass/reject + match score against your profile before committing to tailoring.
4. **Search / History / Info** — Full-text search across every processed JD, a production log with status tracking, a Telegram bot for on-the-go scanning, and an AI cost dashboard.

Cover letters, recruiter emails, and follow-up replies can be generated for any tracked job and saved directly as Gmail drafts.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, vanilla CSS, no router (hash-based view switching), no state library |
| Backend | Python, FastAPI, Uvicorn — a single ~5,000-line `main.py` (no router modules) |
| Database | SQLite, one table (`resumes`) shared by all four products, distinguished by a `source` column |
| AI — Resume analysis & tailoring | Google Gemini (quality/fast/fallback model chain) |
| AI — Job discovery scoring | **Anthropic Claude** (`_score_jobs_with_claude`, Command Center only) |
| AI — Email/mail drafting | OpenAI GPT-4o-mini (via `services/ollama_service.py` — despite the filename, this is not Ollama) |
| Document conversion | python-docx (read/write), `docx2pdf` + MS Word COM automation (Windows-only, best-effort) for the resume's PDF copy |
| Job search source | JSearch (RapidAPI), DuckDuckGo scrape fallback |
| Email Integration | Gmail API (OAuth2) — drafts, inbox search/read, labeling, archiving |
| Messaging | Telegram Bot API (long-polling) — scanning, notifications, daily digest |
| Document Processing | python-docx, pdfplumber, Gemini Vision (OCR for profile documents) |

**Known dead code:** `services/whatsapp_service.py` (a complete Twilio WhatsApp client) and `services/search_cache.py` (an empty-search-result cache) are fully implemented but never called from anywhere in `main.py`. Keep this in mind before assuming either feature is live.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Valid `GEMINI_API_KEY` (required — the resume-tailoring pipeline needs it)
- Optional: `ANTHROPIC_API_KEY` (Command Center job scoring), `OPENAI_API_KEY` (mail drafts), `RAPIDAPI_KEY` (JSearch job search), `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (Gmail), `TELEGRAM_BOT_TOKEN`
- Windows + MS Word installed, if you want the tailored resume's PDF copy generated (`docx2pdf`/`pywin32` are gated to `sys_platform == "win32"` in `requirements.txt`, so this silently no-ops elsewhere, e.g. the Linux Docker image)

### Running Locally

```bash
# Backend
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # Fill in API keys
python main.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs

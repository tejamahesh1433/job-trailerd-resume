# TRAILERD - Job Tailored Resume System

Comprehensive documentation for the **TRAILERD** project — an AI-powered resume tailoring and job matching platform.

## Documentation Index

| Document | Description |
|----------|-------------|
| [System Architecture](System_Architecture.md) | High-level system overview, data flow, and component interaction diagrams |
| [Backend Architecture](Backend_Architecture.md) | FastAPI backend services, database schema, and class diagrams |
| [Frontend Architecture](Frontend_Architecture.md) | React SPA component hierarchy, state management, and UI flow |
| [API Documentation](API_Documentation.md) | Complete REST API reference with request/response schemas |
| [Data Flow & Sequences](Data_Flow_Sequences.md) | Sequence diagrams for all major workflows |
| [Deployment Guide](Deployment_Guide.md) | Environment setup, configuration, and deployment instructions |

## Project Overview

TRAILERD is a full-stack application that automates the job application workflow:

1. **Resume Tailoring** — Paste a job description, select a base resume, and the system uses Google Gemini AI to analyze ATS compatibility, then rewrites bullet points to maximize the match score.
2. **Job Finder** — Pre-screen job descriptions against your profile (visa status, employment type, experience level, role type) before investing time in tailoring.
3. **Email Drafting** — Generate professional application emails and follow-up replies using OpenAI, with direct Gmail integration for one-click draft saving.
4. **Telegram Bot** — Process job descriptions on-the-go by sending them to a Telegram bot.
5. **Search & History** — Full-text search across all processed JDs, with status tracking through the application pipeline.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, vanilla CSS |
| Backend | Python, FastAPI, Uvicorn |
| Database | SQLite (via `database.py`) |
| AI - Resume Analysis | Google Gemini (2.5-pro / 2.5-flash / 2.0-flash fallback chain) |
| AI - Email Drafting | OpenAI GPT-4o-mini |
| AI - Profile OCR | Google Gemini 2.5-flash (vision) |
| Email Integration | Gmail API (OAuth2) |
| Messaging | Telegram Bot API (long-polling) |
| Document Processing | python-docx, pdfplumber |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Valid `GEMINI_API_KEY` (required)
- Optional: `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`

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

# System Architecture

## High-Level Architecture Diagram

```mermaid
graph TB
    User((User))

    subgraph Frontend ["Frontend (React 19 + Vite 8)"]
        App["App.jsx<br/>Main State Container"]
        JM["JobMatcher.jsx<br/>Job Pre-Screening"]
        SP["SearchPage.jsx<br/>Full-Text Search"]
    end

    subgraph Backend ["Backend (FastAPI + Uvicorn)"]
        Router["main.py<br/>API Router + Business Logic"]

        subgraph Services ["services/"]
            AIS["ai_service.py<br/>Gemini Resume Analysis"]
            OLS["ollama_service.py<br/>OpenAI Email Drafts"]
            DXS["docx_service.py<br/>DOCX Read/Write"]
            GMS["gmail_service.py<br/>Gmail OAuth2 + API"]
            TGS["telegram_service.py<br/>Telegram Bot"]
            PFS["profile_service.py<br/>Document OCR"]
            UTS["usage_tracker.py<br/>Cost Tracking"]
        end

        DB[("SQLite<br/>resumes.db")]
        FS[("File System<br/>trailerd/ + original/")]
    end

    subgraph External ["External Services"]
        Gemini["Google Gemini API<br/>2.5-pro / 2.5-flash"]
        OpenAI["OpenAI API<br/>GPT-4o-mini"]
        Gmail["Gmail API<br/>OAuth2"]
        TGBot["Telegram Bot API"]
    end

    User -->|Browser| App
    User -->|Telegram| TGBot
    App -->|REST API| Router
    JM -->|REST API| Router
    SP -->|REST API| Router

    Router --> AIS
    Router --> OLS
    Router --> DXS
    Router --> GMS
    Router --> TGS
    Router --> PFS
    Router --> UTS
    Router --> DB
    Router --> FS

    AIS -->|API Calls| Gemini
    OLS -->|API Calls| OpenAI
    GMS -->|OAuth2 + API| Gmail
    TGS -->|Long-Polling| TGBot
    PFS -->|Vision API| Gemini
```

## Component Responsibilities

### Frontend (React SPA)

| Component | Role |
|-----------|------|
| `App.jsx` | Central state container with 60+ state variables. Renders all pages: Dashboard (Resume Tailor), Job Finder, Search, Info. Manages resume upload, JD scanning, cover letter/email generation, batch mode, history, and Gmail integration. |
| `JobMatcher.jsx` | Pre-screening interface. Accepts JD text or URL, runs eligibility checks (visa, employment type, experience, role level), displays match percentage and skill breakdown. |
| `SearchPage.jsx` | Full-text search across all processed JDs. Shows company, position, emails, location, local-only status. Supports per-record address editing. |

### Backend Services

| Service | Technology | Purpose |
|---------|-----------|---------|
| `ai_service.py` | Google Gemini | ATS score calculation, resume bullet-point rewriting, company name extraction, cover letter generation, job metadata analysis. Uses a 3-model fallback chain (2.5-pro -> 2.5-flash -> 2.0-flash). |
| `ollama_service.py` | OpenAI GPT-4o-mini | Email draft generation (initial outreach + follow-up replies). W2/full-time auto-detection with automatic decline drafts. Recruiter name/job title extraction from JD signatures. |
| `docx_service.py` | python-docx | Extracts text from DOCX (paragraphs + tables). Creates tailored DOCX by performing fuzzy string replacement across runs while preserving formatting. |
| `gmail_service.py` | Google Gmail API | OAuth2 authentication flow. Creates Gmail drafts with multi-attachment support (resume, cover letter, DL, GC). Inbox search and message reading for follow-up workflows. |
| `telegram_service.py` | Telegram Bot API | Async long-polling for incoming messages. Processes JDs sent via chat, runs the full scan pipeline, replies with score and status. |
| `profile_service.py` | Gemini Vision + pdfplumber | Extracts job-relevant facts from uploaded personal documents (PDF, DOCX, images). Uses OCR for scanned documents. Merges extracted facts into the user profile. |
| `usage_tracker.py` | Local JSON file | Tracks all API calls with per-model token counts and cost calculation. Provides daily/weekly/monthly/all-time breakdowns. |

### Data Storage

| Store | Location | Contents |
|-------|----------|----------|
| SQLite Database | `data/resumes.db` | All scan records: company name, JD text, ATS score, file paths, status, scan results (JSON), employment type, match percentage, source URL |
| File System - Originals | `original/` | Uploaded base resume DOCX files |
| File System - Tailored | `trailerd/<company>/` | Per-company output: tailored `resume.docx`, `jd_info.txt`, `difference.txt`, `cover_letter_*.docx`, `mail_draft_*.txt` |
| CSV History | `data/history.csv` | Append-only CSV log with hyperlinks to all generated files |
| API Usage | `data/api_usage.json` | Token counts and costs per API call |
| Gmail Tokens | `data/gmail_tokens.json` | OAuth2 refresh tokens for Gmail integration |
| User Profile | `data/profile.txt` | Extracted personal facts (work authorization, location, availability) |
| Personal Documents | `data/documents/` | Uploaded DL/GC files for email attachments |

## Security Architecture

```mermaid
graph LR
    subgraph Middleware
        TH["TrustedHostMiddleware<br/>Restrict allowed hosts"]
        CORS["CORSMiddleware<br/>Restrict origins"]
        SH["Security Headers<br/>X-Frame-Options, HSTS,<br/>X-Content-Type-Options"]
        RL["SlowAPI Rate Limiter<br/>Per-endpoint limits"]
    end

    subgraph Validation
        PT["Path Traversal Prevention<br/>os.path.abspath checks"]
        FV["File Validation<br/>Size limits, type checks"]
        IV["Input Validation<br/>Pydantic models"]
        CSV["CSV Injection Prevention<br/>sanitize_csv_field()"]
    end

    Request -->|HTTP| TH --> CORS --> SH --> RL --> Handler
    Handler --> PT
    Handler --> FV
    Handler --> IV
    Handler --> CSV
```

### Rate Limits

| Endpoint Group | Limit |
|---------------|-------|
| Resume scan (`/api/scan`) | 10/minute |
| Batch scan (`/api/batch-scan`) | 3/minute |
| Cover letter / Email generation | 5/minute |
| History / Search reads | 30-60/minute |
| Gmail operations | 10-20/minute |
| Job matcher analysis | 30/minute |

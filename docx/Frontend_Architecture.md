# Frontend Architecture

The frontend is a React 19 Single Page Application built with Vite 8. It uses vanilla CSS with CSS custom properties for theming — no external UI library.

## Component Hierarchy

```mermaid
graph TD
    main["main.jsx - StrictMode + DOM mount"]
    main --> App

    subgraph App_Component ["App.jsx — Central State Container"]
        App["App - 60+ state variables, hash routing"]
        SR["ScoreRing - Animated SVG progress ring"]
        FI["FilmIcon - SVG brand icon"]
        EI["EmptyResultsIcon - SVG placeholder"]
    end

    subgraph Pages ["Page Components"]
        JM["JobMatcher.jsx - Job pre-screening"]
        SP["SearchPage.jsx - Full-text JD search"]
        Dashboard["Dashboard View - inline in App.jsx"]
        Info["Info View - inline in App.jsx"]
    end

    App -->|currentPage = dashboard| Dashboard
    App -->|currentPage = job-matcher| JM
    App -->|currentPage = search| SP
    App -->|currentPage = info| Info
```

## Navigation Architecture

The app uses URL hash-based routing managed by `useState` + `window.location.hash`:

```mermaid
stateDiagram-v2
    [*] --> Dashboard: #(empty) or #dashboard
    Dashboard --> JobFinder: #job-matcher
    Dashboard --> Search: #search
    Dashboard --> Info: #info
    JobFinder --> Dashboard: Apply button (sends JD to tailor)
    Search --> Dashboard: Open in Dashboard (loads record)
```

### Sidebar Navigation

All pages share a persistent left sidebar with four navigation buttons:
- **Resume Tailor** — Main dashboard
- **Job Finder** — Pre-screening
- **Search** — Full-text search
- **Info** — Employer details, Telegram bot status, saved addresses

## Dashboard Layout (App.jsx)

The dashboard is the primary interface, organized as numbered panels:

```mermaid
graph TB
    subgraph Tabs ["Mode Tabs"]
        SS["Single Scan"]
        BM["Batch Mode"]
        US["$ Usage"]
    end

    subgraph Workspace ["Two-Column Workspace"]
        subgraph Left ["Panel 01: Pre-Production"]
            AN["AI Notes textarea"]
            JD["Job Description textarea"]
            RM["Resume Manager - Drag-drop, select, delete"]
            PP["Personal Profile - Collapsible editor + doc upload"]
            ACT["ACTION button"]
        end

        subgraph Right ["Panel 02: Post-Production"]
            CB["Company Badge"]
            SC["Score Rings - Original to Tailored"]
            SB["Status Banner"]
            DL["Download Links"]
            CI["Contact Info Strip"]
            MK["Missing Keywords Chips"]
            SS2["Section Breakdown Bars"]
            DF["AI Changes Diff View"]
        end
    end

    subgraph CLMail ["Two-Column Below"]
        P03["Panel 03: Cover Letter - Generate, copy, download"]
        P04["Panel 04: Email Draft - Generate, copy, mailto, Gmail"]
    end

    P05["Panel 05: Follow-Up - Gmail inbox picker, reply generation"]
    P06["Panel 06: Production Log - History table with sort/filter/search"]
```

## State Management

All state is managed via `useState` hooks in `App.jsx`. Key state groups:

```mermaid
graph LR
    subgraph Core ["Core Workflow"]
        jdText["jdText"]
        aiNotes["aiNotes"]
        loading["loading"]
        result["result"]
        error["error"]
    end

    subgraph Resume ["Resume Management"]
        storedResumes["storedResumes[]"]
        selectedResumeName["selectedResumeName"]
        uploadingResume["uploadingResume"]
    end

    subgraph History ["History & Navigation"]
        history["history[]"]
        historySearch["historySearch"]
        historyStatusFilter["historyStatusFilter"]
        historyPage["historyPage"]
        historySortBy["historySortBy"]
        currentPage["currentPage"]
    end

    subgraph Outputs ["Generated Content"]
        coverLetter["coverLetter"]
        mailDraft["mailDraft"]
        followUpDraft["followUpDraft"]
    end

    subgraph Integration ["Integrations"]
        gmailConnected["gmailConnected"]
        gmailEmail["gmailEmail"]
        telegramStatus["telegramStatus"]
        usageStats["usageStats"]
    end

    subgraph Active ["Active Record"]
        activeRecordId["activeRecordId"]
        activeCompanyName["activeCompanyName"]
    end
```

### State Persistence

| State | Storage | Mechanism |
|-------|---------|-----------|
| `selectedResumeName` | `localStorage` | Read on mount, write on change |
| `currentPage` | URL hash | `window.location.hash` |
| `history` | Backend DB | Fetched via `GET /api/history` |
| All other state | Memory | Lost on page refresh |

## Component Details

### App.jsx (~1960 lines)

The monolithic root component handles:

- **Resume Management**: Upload (drag-drop or file picker), select, delete base resumes
- **Single Scan**: JD input -> pre-screening rules -> Gemini AI analysis -> tailored resume output
- **Batch Mode**: Process up to 10 JDs sequentially against selected resume
- **Cover Letter**: Generate via Gemini, copy to clipboard, download DOCX
- **Email Draft**: Generate via OpenAI, copy all, open in mail app, save to Gmail drafts
- **Follow-Up**: Select from Gmail inbox or paste email, generate contextual reply
- **Production Log**: Paginated history table (20/page) with sort (date/score/company/status), filter by status, search by company name, expandable JD preview
- **Usage Dashboard**: API cost tracking with daily/weekly/monthly/all-time breakdowns by model and operation
- **Personal Profile**: Collapsible editor for work authorization, location, availability. Supports document upload for fact extraction.
- **Info Page**: Employer details, Telegram bot configuration status, saved addresses with search

### JobMatcher.jsx (~860 lines)

Standalone job pre-screening component with inline styles:

- URL input with "Fetch JD" button to scrape job posting text
- JD text area with Ctrl+Enter shortcut
- Three view states: input form, analysis results, hard rejection
- Analysis results show: match %, company info, employment type, warnings, skills breakdown bars, detected keywords by category, source URL
- "Apply — Tailor Resume" button sends JD back to dashboard

### SearchPage.jsx (~236 lines)

Full-text search interface:

- Search input with Enter key trigger (min 2 chars)
- Results show: company name, score badge, status badge, position, location, local-only flag, date, emails (click to copy), recruiter name
- Per-record address editing with save/cancel
- Expandable JD preview
- "Open in Dashboard" button to load record in main view

### ScoreRing (inline component)

Animated SVG circular progress indicator:
- Uses `requestAnimationFrame` for smooth 900ms cubic-bezier animation
- Stroke-dasharray/dashoffset technique on SVG circle
- Color-coded: green (>=85%), gold (>=60%), red (<60%)

## Styling

### CSS Custom Properties (index.css)

The app uses a dark cinema-inspired theme:

| Variable | Value | Usage |
|----------|-------|-------|
| `--ink` | Dark background | Page/panel backgrounds |
| `--cream` | Light text | Primary text color |
| `--gold` | Warm accent | Buttons, highlights, panel borders |
| `--success` | Green | High scores, connected status |
| `--danger` | Red | Low scores, errors, rejections |
| `--muted` | Gray | Labels, secondary text |
| `--panel` | Dark panel | Card backgrounds |
| `--border` | Subtle line | Dividers, input borders |
| `--font-display` | Serif | Headers (h1, panel titles) |
| `--font-mono` | Monospace | Labels, scores, badges |
| `--font-body` | Sans-serif | Body text, textareas |

### UI Patterns

- **Panel system**: Numbered panels (`01 Pre-Production`, `02 Post-Production`, etc.) with gold top border
- **Film/cinema metaphor**: "TRAILERD" branding, film strip icon, production terminology
- **Entrance animations**: `panel-enter` CSS animation with staggered `animationDelay`
- **Responsive grid**: `workspace` class uses CSS Grid for two-column layout

## Data Flow: Frontend to Backend

```mermaid
sequenceDiagram
    participant U as User
    participant A as App.jsx
    participant B as Backend API

    Note over U,B: Page Load
    A->>B: GET /api/history?limit=200
    A->>B: GET /api/resumes
    A->>B: GET /api/gmail/status
    A->>B: GET /api/profile
    A->>B: GET /api/usage
    A->>B: GET /api/documents

    Note over U,B: Resume Scan
    U->>A: Paste JD + Click ACTION
    A->>B: POST /api/scan (FormData)
    B-->>A: { score, after_score, company_name, replacements, ... }
    A->>A: setResult(), setActiveRecordId()
    A->>B: GET /api/history (refresh)

    Note over U,B: Cover Letter
    U->>A: Click Generate Cover Letter
    A->>B: POST /api/history/{id}/cover-letter
    B-->>A: { cover_letter, cl_path }

    Note over U,B: Email Draft
    U->>A: Click Generate Email Draft
    A->>B: POST /api/history/{id}/mail-draft
    B-->>A: { to_emails, subject, body }

    Note over U,B: Save to Gmail
    U->>A: Click Save to Gmail Drafts
    A->>B: POST /api/gmail/save-draft
    B-->>A: { draft_id }
```

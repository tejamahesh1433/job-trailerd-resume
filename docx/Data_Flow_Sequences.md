# Data Flow & Sequence Diagrams

## 1. Resume Scan — Full Pipeline (Dashboard)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend (App.jsx)
    participant BE as Backend (main.py)
    participant DB as SQLite
    participant FS as File System
    participant AI as Gemini API
    participant DX as DocxService
    participant WD as MS Word (docx2pdf)

    U->>FE: Paste JD + select resume + click ACTION
    FE->>BE: POST /api/scan (FormData)

    Note over BE: Pre-screening Rules
    BE->>BE: _extract_experience_years() <= 10?
    BE->>BE: _check_visa_eligibility() — GC ok?
    BE->>BE: _check_foreign_language() — no foreign lang?
    BE->>BE: _check_lead_role() — not lead/mgmt?

    alt Pre-screening fails
        BE-->>FE: 400 + reason
        FE->>FE: Show error banner
    end

    BE->>FS: Read resume from original/
    BE->>DX: extract_text_from_docx(file_bytes)
    DX-->>BE: resume_text

    Note over BE: Duplicate Check (skipped if rerun_id set)
    BE->>DB: get_all_resumes(limit=1000)
    BE->>BE: SequenceMatcher ratio >= 0.95?

    Note over BE,AI: AI Analysis
    BE->>AI: analyze_resume(resume_text, jd_text, ai_notes)
    Note over AI: Model fallback chain (model_config.py)
    AI-->>BE: {score, after_score, replacements, company_name, ...}

    alt score >= 85
        BE->>FS: Copy original to trailerd/<company>/Teja_Mahesh_Neerukonda_Resume.docx
        Note over BE: No tailoring needed
    else score < 85 AND replacements exist
        BE->>DX: create_tailored_docx(original_bytes, replacements)
        DX-->>BE: tailored BytesIO
        BE->>FS: Save to trailerd/<company>/Teja_Mahesh_Neerukonda_Resume.docx
    end

    BE->>FS: Write jd_info.txt (contact info + JD)
    BE->>FS: Write difference.txt (before/after diff)
    BE->>WD: _convert_docx_to_pdf() — best-effort, Windows + Word only
    WD-->>BE: Teja_Mahesh_Neerukonda_Resume.pdf (or None if unavailable)
    BE->>DB: save_resume_record(company, jd, score, path, scan_data)
    BE->>FS: Append to history.csv

    BE-->>FE: Full result JSON (file_path + pdf_path)
    FE->>FE: Display ScoreRings, replacements, keywords, PDF download link
    FE->>BE: GET /api/history (refresh log)
```

## 2. Batch Scan Pipeline

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    participant AI as Gemini API

    FE->>BE: POST /api/batch-scan { jd_texts: [...], selected_resume }

    loop For each JD (max 10)
        Note over BE: Pre-screening filters
        alt Filters pass
            BE->>AI: analyze_resume()
            AI-->>BE: Analysis result
            BE->>BE: Save record + create files + convert to PDF
        else Filters fail
            BE->>BE: Mark as skipped with reason
        end
        Note over BE: 2-second delay between JDs
    end

    BE-->>FE: { results: [...], total, processed, skipped }
    FE->>FE: Update batchJobs state for each result
```

## 3. Job Finder Analysis (standalone pre-screen — not Command Center)

```mermaid
sequenceDiagram
    participant U as User
    participant JM as JobMatcher.jsx
    participant BE as Backend
    participant AI as Gemini API

    U->>JM: Paste JD or enter URL

    opt URL provided
        JM->>BE: POST /api/job-matcher/fetch-url
        BE->>BE: Fetch URL, parse HTML
        alt JSON-LD found
            BE-->>JM: Structured JD text
        else Fallback
            BE->>AI: Clean raw text with Gemini
            AI-->>BE: Cleaned JD
            BE-->>JM: Cleaned JD text
        end
    end

    JM->>BE: POST /api/job-matcher/analyze

    Note over BE: Hard Reject Rules
    BE->>BE: 1. _check_lead_role()
    BE->>BE: 2. _check_visa_eligibility()
    BE->>BE: 3. _check_foreign_language()
    BE->>BE: 4. _check_employment_type()

    alt Hard reject
        BE->>BE: save_job_matcher_record(can_apply=false)
        BE-->>JM: { can_apply: false, hard_reject: true, error: "..." }
        JM->>JM: Show rejection card
    else Passes all rules
        BE->>BE: extract_job_keywords()
        BE->>AI: analyze_job_metadata()
        BE->>BE: calculate_match_score()
        BE->>BE: save_job_matcher_record(can_apply=true)
        BE-->>JM: { can_apply: true, match_percentage, job_category, ... }
        JM->>JM: Show analysis with score circle + skills bars
    end

    opt User clicks "Apply — Tailor Resume"
        JM->>JM: onApply(jd_text)
        Note over JM: Sets jdText in App.jsx, switches to dashboard
    end
```

## 4. Command Center Auto-Search + Claude Scoring

```mermaid
sequenceDiagram
    participant U as User
    participant CC as CommandCenter.jsx
    participant BE as Backend
    participant JS as JSearch (RapidAPI)
    participant DDG as DuckDuckGo scrape
    participant CL as Claude API
    participant DB as SQLite

    U->>CC: Click "Search Jobs" (or scheduled trigger)
    CC->>BE: POST /api/jobs/auto-search { query, platforms, work_types, contract_types }

    BE->>JS: Search jobs (primary source)
    alt JSearch unavailable / not configured
        BE->>DDG: Scrape fallback
        DDG-->>BE: Raw job postings text
    else JSearch responds
        JS-->>BE: Structured job listings
    end

    Note over BE: Same hard-reject pre-screening rules as Dashboard/Job Finder
    BE->>BE: Filter out visa/lead-role/language/experience mismatches

    BE->>CL: _score_jobs_with_claude(job_texts, query)
    Note over CL: claude-sonnet-5 — scores 0-100, tags, reasons,\nnext_action, contact extraction (never invents)
    CL-->>BE: Scored + ranked job list

    BE->>DB: save_found_job(...) for each (source='command-center')
    BE->>BE: scan_status.save_last_scan(timestamp, platforms, query, count)
    BE-->>CC: { results, count }
    CC->>CC: Refresh pipeline funnel + Latest Job Matches
```

## 5. Match Center — Tailor a Command Center Job

```mermaid
sequenceDiagram
    participant U as User
    participant JDW as JobDetailWorkspace.jsx
    participant BE as Backend
    participant AI as Gemini API
    participant FS as File System
    participant DB as SQLite

    U->>JDW: Click "Tailor Resume" on a job card
    JDW->>BE: POST /api/jobs/{job_id}/tailor

    Note over BE: Reuses the SAME internal core as /api/scan\n(_scan_resume_core), with override_company_dir set
    BE->>AI: analyze_resume(resume_text, job description, ai_notes)
    AI-->>BE: {score, after_score, replacements, ...}
    BE->>FS: Save to online-platform/<Company>_<job_id>/Teja_Mahesh_Neerukonda_Resume.docx
    BE->>FS: _convert_docx_to_pdf() — best-effort
    BE->>DB: link_tailored_resume(job_id, file_path)
    BE-->>JDW: { file_path, pdf_path, score, after_score, ... }
    JDW->>JDW: Show tailored score + download links
```

## 6. Email Draft + Gmail Integration

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant OAI as OpenAI API
    participant GM as Gmail API

    U->>FE: Click "Generate Email Draft"
    FE->>BE: POST /api/history/{id}/mail-draft

    BE->>BE: Read tailored resume, JD, cover letter, profile
    BE->>OAI: generate_mail_draft(resume, jd, cover_letter, company, profile)
    OAI-->>BE: { subject, body }

    BE-->>FE: { to_emails, subject, body }
    FE->>FE: Display email preview

    alt Copy All
        U->>FE: Click "Copy All"
        FE->>FE: navigator.clipboard.writeText()
    end

    alt Open in Mail App
        U->>FE: Click "Open in Mail App"
        FE->>FE: window.open(mailto: link)
    end

    alt Save to Gmail Drafts
        U->>FE: Click "Save to Gmail Drafts"
        FE->>BE: POST /api/gmail/save-draft
        BE->>GM: Create draft (MIME message + attachments)
        GM-->>BE: { draft_id }
        BE-->>FE: Success
    end
```

## 7. Follow-Up Reply (with W2 Auto-Detection)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant OAI as OpenAI API
    participant GM as Gmail API

    opt Select from Gmail inbox
        U->>FE: Click "Select from Gmail"
        FE->>BE: GET /api/gmail/inbox?q=...
        BE->>GM: Search messages
        GM-->>BE: Message list
        BE-->>FE: Messages with snippets
        U->>FE: Click a message
        FE->>BE: GET /api/gmail/message/{id}
        BE->>GM: Get full body
        GM-->>BE: Message body
        BE-->>FE: Email body text
    end

    U->>FE: Click "Generate Follow-Up"
    FE->>BE: POST /api/history/{id}/follow-up { received_email }

    BE->>OAI: detect_w2_fulltime(received_email)
    OAI-->>BE: is_w2 = true/false

    alt W2 Detected
        BE->>GM: get_conversation_with_sender() — full thread
        GM-->>BE: Conversation history
        BE->>OAI: generate_follow_up(is_w2=true)
        OAI-->>BE: C2C/C2H preference reply
        BE->>GM: Auto-save draft to Gmail
        GM-->>BE: { draft_id }
        BE-->>FE: { w2_detected: true, auto_draft_saved: true }
        FE->>FE: Show "W2 Detected" + "Draft auto-saved" banner
    else Normal follow-up
        BE->>OAI: generate_follow_up(is_w2=false)
        OAI-->>BE: Contextual reply
        BE-->>FE: { subject, body, w2_detected: false }
    end
```

## 8. Inbox AI Classification + Application Matching

```mermaid
sequenceDiagram
    participant U as User
    participant IB as InboxPage.jsx
    participant BE as Backend
    participant Cache as inbox_cache.py
    participant AI as Gemini API
    participant Matcher as inbox_matcher.py
    participant GM as Gmail API

    U->>IB: Open Inbox page
    IB->>BE: GET /api/gmail/inbox?q=...
    BE->>GM: Search messages
    GM-->>BE: Message list (id, subject, snippet, from)

    BE->>Cache: split_cached(messages) — by id + content hash
    Cache-->>BE: { cached: [...], needs_classify: [...] }

    opt Messages need classification
        BE->>AI: classify_inbox_messages(needs_classify) — one batched call
        AI-->>BE: Category per message (Needs Attention/Interview/Rejection/...)
        BE->>Cache: store(new results)
    end

    BE->>Matcher: match against get_active_applications()
    Note over Matcher: Confidence order:\n1. sender domain vs. company (skips shared ATS domains)\n2. company-name text match\n3. job-title text match (>=20 chars only)
    Matcher-->>BE: Matched application id per message (if any)

    BE-->>IB: Messages with category + matched_application
    IB->>IB: Render filter chips, matched-application banner
```

## 9. Background Loops (started at FastAPI startup)

```mermaid
sequenceDiagram
    participant Startup as @app.on_event("startup")
    participant TGPoll as _telegram_poll_loop
    participant TGNotify as telegram_notifier
    participant Sched as scheduler.daily_search_loop
    participant Inbox as inbox_matcher

    Startup->>TGPoll: asyncio.create_task() — if TELEGRAM_BOT_TOKEN set
    Startup->>TGNotify: asyncio.create_task() — if TELEGRAM_BOT_TOKEN set
    Startup->>Sched: asyncio.create_task() — always starts, checks its own enabled flag
    Startup->>Inbox: asyncio.create_task() — if Gmail connected

    loop Continuous long-poll
        TGPoll->>TGPoll: getUpdates(offset, timeout=30)
        Note over TGPoll: JD text -> full scan pipeline\n/matches /followups /queue /start /status\nInline button callbacks
    end

    loop Every 30 minutes
        TGNotify->>TGNotify: Diff Action Queue vs. telegram_notified_ids.json
        TGNotify->>TGNotify: Send Telegram message for anything new
    end

    loop Daily at scheduled time (default 10:00 AM America/New_York)
        Sched->>Sched: Re-check enabled flag
        Sched->>Sched: _run_command_center_search() — see Diagram 4
        Sched->>TGNotify: send_daily_digest()
    end

    loop Every 30 minutes
        Inbox->>Inbox: check_inbox_for_replies() — see Diagram 8
        Inbox->>Inbox: Record new matches, dedupe via inbox_reply_seen.json
        Inbox->>TGNotify: Push notification with follow-up suggestion
    end
```

## 10. Telegram Bot Processing (JD scanning path)

```mermaid
sequenceDiagram
    participant TG as Telegram User
    participant Bot as Telegram Bot API
    participant BE as Backend (poll loop)
    participant AI as Gemini API
    participant FS as File System

    Note over BE: Startup: asyncio.create_task(_telegram_poll_loop)

    loop Long-polling (30s timeout)
        BE->>Bot: getUpdates(offset, timeout=30)
        Bot-->>BE: Updates list

        alt /start command
            BE->>Bot: sendMessage("Welcome to Job Tailored Resume Bot!")
        else /status command
            BE->>BE: Count resumes in original/
            BE->>Bot: sendMessage("Bot running, N resumes available")
        else JD text received
            BE->>Bot: sendMessage("Processing your JD...")
            BE->>BE: Run in thread executor:
            Note over BE: Pre-screening checks
            BE->>FS: Load most recent resume
            BE->>AI: _process_single_jd(jd_text, file_bytes)
            AI-->>BE: { company, score, after_score, tailored }
            BE->>Bot: sendMessage("Processed JD for Company!\nScore: X% -> Y%")
        end
    end
```

## 11. Company Name Extraction Priority

```mermaid
flowchart TD
    JD["JD Text Input"] --> P1
    P1{"Explicit company patterns?"} -->|Found| R1["Return match"]
    P1 -->|Not found| P2
    P2{"Corporate suffix patterns?"} -->|Found| R2["Return match"]
    P2 -->|Not found| P3
    P3{"Email domain extraction?"} -->|Non-generic domain| R3["Return domain.title()"]
    P3 -->|Generic domain| P4
    P4{"Website URL patterns?"} -->|Found| R4["Return domain"]
    P4 -->|Not found| P5
    P5{"Any URL in text?"} -->|Non-blacklisted| R5["Return domain"]
    P5 -->|Blacklisted| P6
    P6{"Phone number context?"} -->|Found| R6["Return prev line"]
    P6 -->|Not found| R7["Return 'Unknown_Company'"]
```

## 12. DOCX Tailoring — Text Replacement Strategy

```mermaid
flowchart TD
    REP["Replacement: {original, new}"] --> PASS1

    subgraph PASS1 ["Pass 1: Exact Match"]
        E1{"original in paragraph.text?"}
        E1 -->|Yes, single run| SR["Replace in run.text"]
        E1 -->|Yes, spans runs| MR["_replace_across_runs()"]
        E1 -->|Normalized match| EP["_replace_entire_paragraph()"]
    end

    E1 -->|No match| PASS2

    subgraph PASS2 ["Pass 2: Fuzzy Match"]
        F1["_find_best_paragraph_match()"]
        F1 --> F2{"SequenceMatcher ratio >= 0.75?"}
        F2 -->|Yes| FP["_replace_entire_paragraph()"]
        F2 -->|No| SKIP["Skip replacement"]
    end

    SR --> DONE["Applied"]
    MR --> DONE
    EP --> DONE
    FP --> DONE

    style DONE fill:#2ebd73,color:#fff
    style SKIP fill:#d94f4f,color:#fff
```

## 13. Resume File Resolution Fallback (`_resolve_resume_path`)

```mermaid
flowchart TD
    START["Endpoint needs record's resume file"] --> EXACT{"record.file_path exists on disk?"}
    EXACT -->|Yes| USE["Use it directly"]
    EXACT -->|No| GENERIC{"company_name is a generic\nplaceholder (Unknown/Unknown Company)?"}
    GENERIC -->|Yes| SKIPCO["Skip company-name-derived candidate\n(would risk misattributing a stranger's file)"]
    GENERIC -->|No| TRYCO["Try trailerd/<safe-company-name>/\nand online-platform/<safe-company-name>/"]
    SKIPCO --> TRYDIR
    TRYCO -->|Found a non-cover-letter .docx| HEAL
    TRYCO -->|Not found| TRYDIR["Try os.path.dirname(file_path)\n(skip if it resolves to the bare trailerd/\nor online-platform/ root itself)"]
    TRYDIR -->|Found| HEAL
    TRYDIR -->|Not found| TRYSTEM["Try file_path with its extension\ntreated as a directory name\n(legacy flat-file scans)"]
    TRYSTEM -->|Found| HEAL["Self-heal: link_tailored_resume()\nupdates the DB to the found path"]
    TRYSTEM -->|Not found| NONE["Return None — endpoint reports\n'resume file not found' honestly"]
    HEAL --> USE
```

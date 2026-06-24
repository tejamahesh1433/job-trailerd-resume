# Data Flow & Sequence Diagrams

## 1. Resume Scan — Full Pipeline

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend (App.jsx)
    participant BE as Backend (main.py)
    participant DB as SQLite
    participant FS as File System
    participant AI as Gemini API
    participant DX as DocxService

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

    Note over BE: Duplicate Check
    BE->>DB: get_all_resumes(limit=1000)
    BE->>BE: SequenceMatcher ratio >= 0.95?

    Note over BE,AI: AI Analysis
    BE->>AI: analyze_resume(resume_text, jd_text, ai_notes)
    Note over AI: Try gemini-2.5-pro
    AI-->>BE: {score, after_score, replacements, company_name, ...}

    alt score >= 85
        BE->>FS: Copy original to trailerd/<company>/resume.docx
        Note over BE: No tailoring needed
    else score < 85 AND replacements exist
        BE->>DX: create_tailored_docx(original_bytes, replacements)
        DX-->>BE: tailored BytesIO
        BE->>FS: Save to trailerd/<company>/resume.docx
    end

    BE->>FS: Write jd_info.txt (contact info + JD)
    BE->>FS: Write difference.txt (before/after diff)
    BE->>DB: save_resume_record(company, jd, score, path, scan_data)
    BE->>FS: Append to history.csv

    BE-->>FE: Full result JSON
    FE->>FE: Display ScoreRings, replacements, keywords
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
            BE->>BE: Save record + create files
        else Filters fail
            BE->>BE: Mark as skipped with reason
        end
        Note over BE: 2-second delay between JDs
    end

    BE-->>FE: { results: [...], total, processed, skipped }
    FE->>FE: Update batchJobs state for each result
```

## 3. Job Finder Analysis

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

## 4. Email Draft + Gmail Integration

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

## 5. Follow-Up Reply (with W2 Auto-Detection)

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

## 6. Telegram Bot Processing

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

## 7. Company Name Extraction Priority

```mermaid
flowchart TD
    JD["JD Text Input"] --> P1
    P1{"Explicit company patterns<br/>Company:, Organization:, About [X]"} -->|Found| R1["Return match"]
    P1 -->|Not found| P2
    P2{"Corporate suffix patterns<br/>[Name] Inc./LLC/Corp/Ltd"} -->|Found| R2["Return match"]
    P2 -->|Not found| P3
    P3{"Email domain extraction<br/>user@company.com"} -->|Non-generic domain| R3["Return domain.title()"]
    P3 -->|Generic domain| P4
    P4{"Website URL patterns<br/>Web: www.company.com"} -->|Found| R4["Return domain"]
    P4 -->|Not found| P5
    P5{"Any URL in text<br/>https://company.com/..."} -->|Non-blacklisted| R5["Return domain"]
    P5 -->|Blacklisted| P6
    P6{"Phone number context<br/>Line before phone = company?"} -->|Found| R6["Return prev line"]
    P6 -->|Not found| R7["Return 'Unknown_Company'"]
```

## 8. DOCX Tailoring — Text Replacement Strategy

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

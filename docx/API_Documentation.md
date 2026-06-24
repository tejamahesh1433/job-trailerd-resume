# API Documentation

Base URL: `http://localhost:8000`

All endpoints return JSON unless noted. Interactive Swagger docs available at `/docs` when the server is running.

---

## Resume Management

### GET /api/resumes
List all uploaded base resumes.

**Rate Limit:** 60/minute

**Response:**
```json
[
    {
        "filename": "devops_resume.docx",
        "size": 24567,
        "modified": "2024-06-15T10:30:00"
    }
]
```

### POST /api/resumes
Upload a new base resume.

**Rate Limit:** 10/minute  
**Content-Type:** multipart/form-data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `resume` | File (.docx) | Yes | Resume file, max 5MB |

**Response:** `{ "filename": "sanitized_name.docx" }`

### DELETE /api/resumes/{filename}
Delete a stored resume.

**Rate Limit:** 10/minute  
**Response:** `{ "status": "ok" }`

### GET /api/base-resume
Check if a default base resume exists.

**Response:** `{ "exists": true, "filename": "base_resume.docx" }`

---

## Resume Scanning

### POST /api/scan
Analyze a resume against a job description and generate a tailored version.

**Rate Limit:** 10/minute  
**Content-Type:** multipart/form-data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `jd_text` | string | Yes | Job description text (50-50000 chars) |
| `resume` | File | No | Upload new resume |
| `selected_resume` | string | No | Filename of stored resume to use |
| `ai_notes` | string | No | Custom instructions for AI (e.g., "focus on Kubernetes") |

**Pre-screening rules (returns 400 if failed):**
- JD minimum 50 characters
- Experience requirement <= 10 years
- Green Card eligible (no explicit GC exclusion)
- No foreign language requirement
- Not a lead/management role
- Not a duplicate JD (>= 95% similarity with existing record)

**Response (200):**
```json
{
    "id": 42,
    "company_name": "TechCorp Inc",
    "file_path": "trailerd/TechCorp_Inc/resume.docx",
    "tailored": true,
    "duplicate": false,
    "previous_score": null,
    "score": 62,
    "after_score": 87,
    "missing_keywords": ["Terraform", "Ansible", "GitOps"],
    "section_scores": {
        "Skills": 75,
        "Experience": 68,
        "Education": 85,
        "Summary": 60
    },
    "contact_info": {
        "name": "John Smith",
        "email": "john@recruiting.com",
        "phone": "555-123-4567"
    },
    "replacements": [
        {
            "original": "Managed cloud infrastructure on AWS",
            "new": "Managed cloud infrastructure on AWS using Terraform IaC and Ansible automation",
            "keywords_added": ["Terraform", "IaC", "Ansible"]
        }
    ]
}
```

### POST /api/batch-scan
Process multiple JDs in sequence against a single resume.

**Rate Limit:** 3/minute

**Request Body (JSON):**
```json
{
    "jd_texts": ["JD text 1...", "JD text 2..."],
    "selected_resume": "my_resume.docx",
    "ai_notes": "Keep ATS score above 85"
}
```

| Field | Type | Constraints |
|-------|------|------------|
| `jd_texts` | string[] | 1-10 items, each 50-50000 chars |
| `selected_resume` | string | Must exist in `original/` |
| `ai_notes` | string | Optional |

**Response:**
```json
{
    "results": [
        { "index": 0, "skipped": false, "company_name": "...", "score": 65, "after_score": 88, ... },
        { "index": 1, "skipped": true, "reason": "Requires 15+ years experience" }
    ],
    "total": 2,
    "processed": 1,
    "skipped": 1
}
```

---

## History & Records

### GET /api/history
Retrieve paginated scan history.

**Rate Limit:** 60/minute

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Max records (1-200) |
| `offset` | int | 0 | Pagination offset |

**Response:** Array of record objects with parsed `scan_result` JSON.

### GET /api/search
Full-text search across company names, JD text, and scan results.

**Rate Limit:** 30/minute

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | Yes | Search query (min 2 chars) |
| `limit` | int | No | Max results (1-100, default 50) |

**Response:**
```json
{
    "results": [
        {
            "id": 42,
            "company_name": "TechCorp",
            "position": "DevOps Engineer",
            "emails": ["john@techcorp.com"],
            "recruiter_name": "John Smith",
            "location": "Remote, US",
            "local_required": false,
            "user_address": "",
            "status": "Applied",
            "score": 87,
            "match_percentage": null,
            "source": "dashboard",
            "created_at": "2024-06-15T10:30:00",
            "jd_preview": "We are looking for..."
        }
    ],
    "count": 1
}
```

### DELETE /api/history/{record_id}
Delete a history record.

**Rate Limit:** 20/minute

### PATCH /api/history/{record_id}/status
Update application status.

**Rate Limit:** 20/minute

**Request Body:**
```json
{ "status": "Applied" }
```

**Valid statuses:** `Scanned`, `Applied`, `Phone Screen`, `Interview`, `Offer`, `Rejected`

### PATCH /api/history/{record_id}/address
Save a user address for a specific record.

**Rate Limit:** 30/minute

**Request Body:**
```json
{ "address": "123 Main St, City, State 12345" }
```

### GET /api/history/{record_id}/content
Retrieve saved cover letter and mail draft for a record.

**Rate Limit:** 60/minute

**Response:**
```json
{
    "company_name": "TechCorp",
    "cover_letter": "Dear Hiring Manager...",
    "cl_path": "trailerd/TechCorp/cover_letter_abc123.docx",
    "mail_draft": {
        "to_emails": ["john@techcorp.com"],
        "subject": "Application for DevOps Engineer",
        "body": "Dear John..."
    },
    "draft_path": "trailerd/TechCorp/mail_draft_abc123.txt"
}
```

### GET /api/history/csv
Download full history as CSV file.

**Rate Limit:** 10/minute

### GET /api/addresses
List all records with saved addresses.

**Rate Limit:** 60/minute

---

## Cover Letter & Email

### POST /api/history/{record_id}/cover-letter
Generate a cover letter using Gemini AI.

**Rate Limit:** 5/minute  
**Response:** `{ "cover_letter": "...", "cl_path": "trailerd/.../cover_letter_*.docx" }`

### POST /api/history/{record_id}/mail-draft
Generate an email draft using OpenAI.

**Rate Limit:** 5/minute

**Response:**
```json
{
    "to_emails": ["recruiter@company.com"],
    "subject": "Application: DevOps Engineer — C2C",
    "body": "Dear [Recruiter],\n\n..."
}
```

### POST /api/history/{record_id}/mail-draft/save
Save email draft to the company folder.

**Rate Limit:** 10/minute

**Request Body:**
```json
{
    "subject": "Application: DevOps Engineer",
    "body": "Dear recruiter..."
}
```

**Response:** `{ "draft_path": "trailerd/.../mail_draft_abc123.txt" }`

### POST /api/history/{record_id}/follow-up
Generate a follow-up reply to a received email.

**Rate Limit:** 5/minute

**Request Body:**
```json
{ "received_email": "Hi, we received your resume..." }
```

**Response:**
```json
{
    "to_emails": ["recruiter@company.com"],
    "subject": "Re: DevOps Engineer Position",
    "body": "Thank you for your response...",
    "w2_detected": false,
    "auto_draft_saved": false
}
```

If `w2_detected` is true, the system auto-generates a C2C/C2H preference reply and saves it to Gmail drafts.

### POST /api/follow-up/standalone
Generate a follow-up without a company record context.

**Rate Limit:** 5/minute  
Same request/response as above.

---

## Gmail Integration

### GET /api/gmail/status
Check Gmail connection status.

**Response:** `{ "connected": true, "email": "user@gmail.com" }`

### GET /api/gmail/auth
Initiate OAuth2 flow. Redirects to Google consent screen.

### GET /api/gmail/callback
OAuth2 callback. Exchanges auth code for tokens, redirects to frontend.

### POST /api/gmail/disconnect
Remove stored Gmail tokens.

### POST /api/gmail/save-draft
Save an email as a Gmail draft with optional attachments.

**Rate Limit:** 10/minute

**Request Body:**
```json
{
    "to_emails": ["recruiter@company.com"],
    "subject": "Application",
    "body": "Dear...",
    "record_id": 42,
    "attach_resume": true,
    "attach_cover_letter": true,
    "attach_dl": false,
    "attach_gc": false
}
```

### GET /api/gmail/inbox
Search Gmail inbox messages.

**Rate Limit:** 10/minute

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | "in:inbox" | Gmail search query |

### GET /api/gmail/message/{message_id}
Get full body of a Gmail message.

**Rate Limit:** 20/minute

---

## Job Finder

### POST /api/job-matcher/fetch-url
Fetch and extract job description from a URL.

**Rate Limit:** 20/minute

| Field | Type | Required |
|-------|------|----------|
| `url` | string | Yes (http/https) |

**Response:** `{ "jd_text": "Extracted JD text...", "url": "..." }`

Extraction priority:
1. JSON-LD structured data (`@type: JobPosting`)
2. AI-cleaned raw HTML text (Gemini 2.5-flash fallback)

### POST /api/job-matcher/analyze
Analyze a job description against user profile.

**Rate Limit:** 30/minute

| Field | Type | Required |
|-------|------|----------|
| `jd_text` | string | Yes (50-50000 chars) |
| `source_url` | string | No |

**Hard reject rules (returns with `hard_reject: true`):**
1. Lead/management role detected
2. Visa ineligibility (GC not accepted)
3. Foreign language required
4. W2/full-time only (user prefers C2C/C2H)

**Success response:**
```json
{
    "id": 15,
    "can_apply": true,
    "hard_reject": false,
    "match_percentage": 85,
    "warnings": ["Experience gap: requires 12+ years"],
    "company_name": "CloudStart Solutions",
    "job_category": {
        "name": "DevOps Engineer",
        "sub_categories": [
            { "name": "Kubernetes", "confidence": 0.95 },
            { "name": "CI/CD", "confidence": 0.88 }
        ],
        "match_confidence": 0.91
    },
    "employment_type": "c2c",
    "experience_years": "7+ years",
    "extracted_keywords": {
        "devops": ["kubernetes", "docker", "terraform"],
        "sre": ["monitoring", "prometheus"],
        "platform": [],
        "security": ["iam"]
    },
    "location": "Remote, US",
    "salary_range": "$85-95/hr",
    "visa_requirements": "GC accepted",
    "clearance_level": "Not specified"
}
```

---

## Profile & Documents

### GET /api/profile
Get personal profile text.

### POST /api/profile
Save personal profile.

**Rate Limit:** 10/minute  
**Request Body:** `{ "content": "Work Auth: GC\nLocation: Open to relocation\n..." }`

### POST /api/profile/upload
Upload a document (PDF, DOCX, image) to extract job-relevant facts.

**Rate Limit:** 5/minute  
**Content-Type:** multipart/form-data  
**Max size:** 10MB

The raw file is never stored — only extracted facts are saved to the profile.

### POST /api/documents/upload
Upload personal documents (DL, GC) for email attachments.

**Rate Limit:** 10/minute

| Field | Type | Values |
|-------|------|--------|
| `doc_type` | string | `dl` or `gc` |
| `file` | File | PDF, DOCX, PNG, JPG |

### GET /api/documents
List uploaded documents.

### DELETE /api/documents/{doc_type}
Delete a personal document.

---

## Telegram Bot

### GET /api/telegram/status
Check Telegram bot configuration and polling status.

**Response:**
```json
{
    "configured": true,
    "polling": true,
    "bot_username": "my_resume_bot"
}
```

The Telegram bot uses long-polling (not webhooks). It processes JDs sent as text messages and replies with scan results.

**Bot commands:**
- `/start` — Welcome message
- `/status` — Bot status and resume count
- Any other text — Treated as a JD and processed through the full scan pipeline

---

## Utility

### GET /
Health check.

**Response:** `{ "status": "ok", "message": "API is running" }`

### GET /api/usage
API usage statistics and cost tracking.

**Response:**
```json
{
    "today": { "calls": 5, "cost": 0.0234 },
    "week": { "calls": 42, "cost": 0.1856 },
    "month": { "calls": 180, "cost": 0.7234 },
    "all_time": {
        "calls": 500,
        "cost": 2.1456,
        "by_model": {
            "gemini-2.5-flash": { "calls": 300, "cost": 0.45 },
            "gpt-4o-mini": { "calls": 200, "cost": 0.32 }
        },
        "by_operation": {
            "resume_analysis": 150,
            "cover_letter": 80,
            "mail_draft": 120
        }
    },
    "daily_breakdown": { "2024-06-15": { "calls": 5, "cost": 0.023 } },
    "projected_monthly": 1.45
}
```

### GET /api/download/{file_path}
Download a generated file from the `trailerd/` directory.

Path traversal protection is enforced via `os.path.abspath` validation.

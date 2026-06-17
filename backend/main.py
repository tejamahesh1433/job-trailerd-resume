from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import os
import re
import difflib
import csv
import shutil
import docx
import json
import logging
import hashlib
import sys
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi.responses import RedirectResponse
from services.ai_service import analyze_resume, generate_cover_letter
from services.ollama_service import generate_mail_draft
from services.docx_service import extract_text_from_docx, create_tailored_docx
from services import gmail_service
from services.profile_service import process_uploaded_doc
from services.usage_tracker import get_usage_stats
from database import init_db, save_resume_record, get_all_resumes, delete_resume_record, update_resume_status, get_resume_by_id, find_existing_company, sanitize_csv_field

DATA_DIR = os.getenv("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, 'logs', 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Validate required environment variables
load_dotenv()
required_env_vars = ["GEMINI_API_KEY"]
for var in required_env_vars:
    if not os.getenv(var):
        logger.error(f"Missing required environment variable: {var}")
        raise SystemExit(f"Missing required environment variable: {var}")

limiter = Limiter(key_func=get_remote_address)

_TECH_TOOLS = {
    "digitalocean", "digital ocean", "aws", "amazon", "amazon web services",
    "google cloud", "gcp", "azure", "microsoft azure", "kubernetes", "docker",
    "terraform", "ansible", "jenkins", "github", "gitlab", "bitbucket",
    "circleci", "travis", "datadog", "splunk", "grafana", "prometheus",
    "elasticsearch", "redis", "mongodb", "postgresql", "mysql", "nginx",
    "apache", "linux", "ubuntu", "centos", "helm", "argocd", "vault",
    "consul", "nomad", "istio", "envoy", "kafka", "rabbitmq", "jira",
    "confluence", "slack", "pagerduty", "new relic", "cloudflare",
    "heroku", "vercel", "netlify", "firebase", "supabase",
}

def _extract_company_name(jd_text: str) -> str:
    """Best-effort local extraction of company name — no API call.
    Searches the ENTIRE JD text including signatures at the bottom."""

    _GENERIC_EMAIL = {"gmail", "yahoo", "hotmail", "outlook", "protonmail",
                      "mail", "icloud", "aol", "live", "ymail", "zoho",
                      "fastmail", "tutanota", "pm", "hey"}

    # Priority 1: Look for explicit company name lines (often near signatures)
    company_patterns = [
        r'(?:Company|Employer|Organization|Firm|Client)(?:\s+Name)?[:\s]+([^\n]{2,60})',
        r'^([A-Z][A-Za-z0-9\s&.,\-]+?)\s+(?:is hiring|is looking|is seeking|seeks|are hiring)',
        r'(?:About|Join)\s+([A-Z][A-Za-z0-9\s&.,\-]{2,40}?)(?:\s*[\n:]|\s+is\b|\s+are\b)',
    ]
    for pattern in company_patterns:
        m = re.search(pattern, jd_text, re.MULTILINE)
        if m:
            name = m.group(1).strip().strip('.,')
            if 2 < len(name) < 60 and name.lower() not in _TECH_TOOLS:
                return name

    # Priority 2: Extract from "Company Inc/LLC/Ltd/Corp" patterns anywhere in text
    # Search line by line to avoid cross-line matches
    for line in jd_text.split('\n'):
        corp_match = re.search(
            r'([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Pvt|Private|Limited|Group|Consulting|Solutions|Technologies|Services)',
            line.strip()
        )
        if corp_match:
            name = corp_match.group(0).strip().strip('.,')
            if name.lower() not in _TECH_TOOLS and len(name) < 60:
                return name

    # Priority 3: Extract from email domain (search ALL emails in the JD)
    all_emails = re.findall(r'[\w.+-]+@([\w-]+)\.\w{2,}', jd_text)
    for domain in all_emails:
        if domain.lower() not in _GENERIC_EMAIL and len(domain) > 2:
            return domain.replace('-', ' ').title()

    # Priority 4: Look for "Web: www.company.com" or website patterns near signatures
    web_match = re.search(r'(?:Web|Website|URL)[:\s]+(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+)\.\w{2,}', jd_text, re.IGNORECASE)
    if web_match:
        domain = web_match.group(1).strip()
        if domain.lower() not in _GENERIC_EMAIL and len(domain) > 2:
            return domain.replace('-', ' ').title()

    return "Unknown_Company"

def get_output_filename(filename_type: str, record_id: int = 0) -> str:
    """Generate non-revealing output filenames using record ID hash."""
    if record_id > 0:
        user_hash = hashlib.sha256(str(record_id).encode()).hexdigest()[:8]
    else:
        user_hash = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:8]

    templates = {
        "resume": f"resume_{user_hash}.docx",
        "cover_letter": f"cover_letter_{user_hash}.docx",
        "mail_draft": f"mail_draft_{user_hash}.txt"
    }
    return templates.get(filename_type, f"file_{user_hash}.tmp")

class StatusUpdate(BaseModel):
    status: str

def append_to_csv(company_name, jd_text, before_score, after_score, original_path, tailored_path):
    csv_file = os.path.join(DATA_DIR, "history.csv")
    file_exists = os.path.exists(csv_file)

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Company Name", "Before Score", "After Score", "Original Resume", "Tailored Resume", "JD Info", "Cover Letter", "Mail Draft", "Job Description"])

        abs_orig = os.path.abspath(original_path) if original_path else ""
        abs_tail = os.path.abspath(tailored_path) if tailored_path else ""

        # Derive paths for other files assuming they are in the same folder as the tailored resume
        tail_dir = os.path.dirname(abs_tail) if abs_tail else ""
        abs_jd = os.path.join(tail_dir, "jd_info.txt") if tail_dir else ""
        abs_cl_search = [f for f in os.listdir(tail_dir) if f.startswith("cover_letter_")] if tail_dir and os.path.isdir(tail_dir) else []
        abs_mail_search = [f for f in os.listdir(tail_dir) if f.startswith("mail_draft_")] if tail_dir and os.path.isdir(tail_dir) else []

        abs_cl = os.path.join(tail_dir, abs_cl_search[0]) if abs_cl_search else ""
        abs_mail = os.path.join(tail_dir, abs_mail_search[0]) if abs_mail_search else ""

        # Format for Excel hyperlinks - sanitize CSV injection
        orig_link = f'=HYPERLINK("file:///{abs_orig.replace(chr(92), "/")}", "Open Original")' if abs_orig else "N/A"
        tail_link = f'=HYPERLINK("file:///{abs_tail.replace(chr(92), "/")}", "Open Tailored")' if abs_tail else "N/A"
        jd_link = f'=HYPERLINK("file:///{abs_jd.replace(chr(92), "/")}", "Open JD Info")' if abs_jd else "N/A"
        cl_link = f'=HYPERLINK("file:///{abs_cl.replace(chr(92), "/")}", "Open Cover Letter")' if abs_cl else "N/A"
        mail_link = f'=HYPERLINK("file:///{abs_mail.replace(chr(92), "/")}", "Open Mail Draft")' if abs_mail else "N/A"

        writer.writerow([
            sanitize_csv_field(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            sanitize_csv_field(company_name),
            sanitize_csv_field(f"{before_score}%"),
            sanitize_csv_field(f"{after_score}%"),
            orig_link,
            tail_link,
            jd_link,
            cl_link,
            mail_link,
            sanitize_csv_field(jd_text[:1000])  # Limit JD length in CSV
        ])

# Ensure output directory exists
os.makedirs("trailerd", exist_ok=True)
os.makedirs("original", exist_ok=True)
init_db()

app = FastAPI(title="Job Tailored Resume API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security: Trusted host middleware
allowed_hosts = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in allowed_hosts])

# Security: CORS with restricted origins
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type"],
    max_age=3600
)

# Security: Add security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API is running"}

@app.get("/api/base-resume")
def get_base_resume():
    base_path = "original/base_resume.docx"
    if os.path.exists(base_path):
        return {"exists": True, "filename": "base_resume.docx"}
    return {"exists": False}

@app.get("/api/resumes")
@limiter.limit("60/minute")
async def list_resumes(request: Request):
    try:
        resumes = []
        if os.path.exists("original"):
            for f in os.listdir("original"):
                if f.endswith(".docx"):
                    path = os.path.join("original", f)
                    stat = os.stat(path)
                    resumes.append({
                        "filename": f,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
        resumes.sort(key=lambda r: r["modified"], reverse=True)
        return resumes
    except Exception as e:
        logger.error(f"List resumes error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list resumes")

@app.post("/api/resumes")
@limiter.limit("10/minute")
async def upload_named_resume(request: Request, resume: UploadFile = File(...)):
    try:
        if not resume.filename or not resume.filename.endswith(".docx"):
            raise HTTPException(status_code=400, detail="Only .docx files are supported")

        file_bytes = await resume.read()
        if len(file_bytes) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        # Sanitize filename - only allow alphanumeric, dash, underscore, dot
        safe_name = re.sub(r"[^\w\-.]", "_", os.path.basename(resume.filename))
        safe_name = re.sub(r"\.{2,}", ".", safe_name)  # Prevent directory traversal

        file_path = os.path.join("original", safe_name)

        # Verify path is within original directory
        abs_path = os.path.abspath(file_path)
        abs_base = os.path.abspath("original")
        if not abs_path.startswith(abs_base):
            raise HTTPException(status_code=400, detail="Invalid filename")

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        logger.info(f"Resume uploaded: {safe_name}")
        return {"filename": safe_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume upload error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload resume")

@app.delete("/api/resumes/{filename}")
@limiter.limit("10/minute")
async def delete_named_resume(request: Request, filename: str):
    try:
        safe = os.path.basename(filename)
        file_path = os.path.join("original", safe)

        # Verify path is within original directory
        abs_path = os.path.abspath(file_path)
        abs_base = os.path.abspath("original")
        if not abs_path.startswith(abs_base):
            raise HTTPException(status_code=404, detail="Resume not found")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Resume not found")

        os.remove(file_path)
        logger.info(f"Resume deleted: {safe}")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume deletion error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete resume")

@app.post("/api/scan")
@limiter.limit("10/minute")
async def scan_resume(request: Request, jd_text: str = Form(...), resume: Optional[UploadFile] = File(None), selected_resume: Optional[str] = Form(None)):
    try:
        # Validate JD text length
        if not jd_text or len(jd_text) > 50000:
            raise HTTPException(status_code=400, detail="Invalid job description")

        if resume:
            file_bytes = await resume.read()
            if len(file_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
            if not resume.filename or not resume.filename.endswith('.docx'):
                raise HTTPException(status_code=400, detail="Only .docx files are supported")
            if len(file_bytes) == 0:
                raise HTTPException(status_code=400, detail="File is empty")

            safe_name = re.sub(r'[^\w\-.]', '_', os.path.basename(resume.filename))
            safe_name = re.sub(r"\.{2,}", ".", safe_name)  # Prevent directory traversal
            original_filename = os.path.join("original", safe_name)

            # Verify path is within original directory
            abs_path = os.path.abspath(original_filename)
            abs_base = os.path.abspath("original")
            if not abs_path.startswith(abs_base):
                raise HTTPException(status_code=400, detail="Invalid filename")

            with open(original_filename, "wb") as f:
                f.write(file_bytes)
        elif selected_resume:
            safe = os.path.basename(selected_resume)
            resume_path = os.path.join("original", safe)

            # Verify path is within original directory
            abs_path = os.path.abspath(resume_path)
            abs_base = os.path.abspath("original")
            if not abs_path.startswith(abs_base):
                raise HTTPException(status_code=400, detail="Resume not found")

            if not os.path.exists(resume_path):
                raise HTTPException(status_code=400, detail="Resume not found")

            # Check file size before loading
            file_size = os.path.getsize(resume_path)
            if file_size > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Resume file too large")

            with open(resume_path, "rb") as f:
                file_bytes = f.read()
            original_filename = resume_path
        else:
            base_path = "original/base_resume.docx"
            if not os.path.exists(base_path):
                raise HTTPException(status_code=400, detail="No resume found. Please upload a resume first.")
            with open(base_path, "rb") as f:
                file_bytes = f.read()
            original_filename = base_path

        resume_text = extract_text_from_docx(file_bytes)

        all_history = get_all_resumes(limit=1000)
        best_match = None
        best_cached_ratio = 0.0

        for item in all_history:
            if not item.get('file_path') or not os.path.exists(item['file_path']):
                continue
            ratio = difflib.SequenceMatcher(None, jd_text, item.get('jd_text', '')).ratio()
            if ratio > best_cached_ratio:
                best_cached_ratio = ratio
                best_match = item

        if best_match and best_cached_ratio >= 0.80 and best_match.get('score', 0) >= 85:
            # TRUE ZERO-COST CACHE: Skip analyze_resume API call entirely!
            company_name = _extract_company_name(jd_text)
            safe_company_name = "".join([c for c in company_name if c.isalpha() or c.isdigit() or c==' ']).strip()
            if not safe_company_name:
                safe_company_name = "Company"
            company_dir = f"trailerd/{safe_company_name.replace(' ', '_')}"
            os.makedirs(company_dir, exist_ok=True)

            file_path = f"{company_dir}/resume.docx"
            jd_path = f"{company_dir}/jd_info.txt"

            shutil.copy(best_match['file_path'], file_path)

            with open(jd_path, "w", encoding="utf-8") as f:
                f.write("Job Description:\n")
                f.write(jd_text)

            record_id = save_resume_record(company_name, jd_text, best_match['score'], file_path)
            append_to_csv(company_name, jd_text, best_match['score'], best_match['score'], original_filename, file_path)

            return {
                "id": record_id,
                "score": best_match['score'],
                "after_score": best_match['score'],
                "company_name": company_name,
                "file_path": file_path,
                "missing_keywords": [],
                "section_scores": {},
                "contact_info": {},
                "replacements": [],
                "tailored": False
            }

        try:
            result = analyze_resume(resume_text, jd_text)
        except RuntimeError as e:
            logger.warning(f"AI provider unavailable: {e}")
            raise HTTPException(status_code=503, detail="The AI provider is currently unavailable. Please try again in a few moments.")

        score = result.get('score', 0)
        company_name = result.get('company_name', _extract_company_name(jd_text))
        safe_company_name = "".join([c for c in company_name if c.isalpha() or c.isdigit() or c==' ']).strip()
        company_dir = f"trailerd/{safe_company_name.replace(' ', '_')}"
        os.makedirs(company_dir, exist_ok=True)

        file_path = f"{company_dir}/resume.docx"
        jd_path = f"{company_dir}/jd_info.txt"

        replacements = result.get('replacements', [])
        if replacements:
            tailored_stream = create_tailored_docx(file_bytes, replacements)
            with open(file_path, "wb") as f:
                f.write(tailored_stream.read())
            after_score = result.get('after_score', score)
            logger.info(f"Applied {len(replacements)} replacements for {company_name}")
        else:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            after_score = score
            logger.info(f"No replacements needed for {company_name} (score: {score})")

        contact_info = result.get('contact_info', {})
        with open(jd_path, "w", encoding="utf-8") as f:
            f.write("Contact Info:\n")
            f.write(f"Name: {contact_info.get('name', 'N/A')}\n")
            f.write(f"Email: {contact_info.get('email', 'N/A')}\n")
            f.write(f"Phone: {contact_info.get('phone', 'N/A')}\n\n")
            f.write("Job Description:\n")
            f.write(jd_text)

        existing = find_existing_company(company_name)

        scan_data = {
            "score": score,
            "after_score": after_score,
            "missing_keywords": result.get('missing_keywords', []),
            "section_scores": result.get('section_scores', {}),
            "contact_info": contact_info,
            "replacements": replacements,
        }

        record_id = save_resume_record(company_name, jd_text, after_score, file_path, json.dumps(scan_data))
        append_to_csv(company_name, jd_text, score, after_score, original_filename, file_path)

        return {
            "id": record_id,
            "company_name": company_name,
            "file_path": file_path,
            "tailored": len(replacements) > 0,
            "duplicate": existing is not None,
            "previous_score": existing['score'] if existing else None,
            **scan_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scan resume error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process resume. Please try again later.")

@app.get("/api/history")
@limiter.limit("60/minute")
async def get_history(request: Request, limit: int = 50, offset: int = 0):
    try:
        # Validate input parameters
        limit = min(max(limit, 1), 200)  # Clamp between 1 and 200
        offset = max(offset, 0)
        return get_all_resumes(limit, offset)
    except Exception as e:
        logger.error(f"Get history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")

@app.delete("/api/history/{record_id}")
@limiter.limit("20/minute")
async def delete_history_item(request: Request, record_id: int):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")
        delete_resume_record(record_id)
        logger.info(f"History record deleted: {record_id}")
        return {"status": "ok", "message": "Record deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete record")

@app.patch("/api/history/{record_id}/status")
@limiter.limit("20/minute")
async def patch_history_status(request: Request, record_id: int, status_update: StatusUpdate):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")
        # Validate status value
        valid_statuses = ["Scanned", "Applied", "Phone Screen", "Interview", "Offer", "Rejected"]
        if status_update.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        update_resume_status(record_id, status_update.status)
        logger.info(f"History record status updated: {record_id} -> {status_update.status}")
        return {"status": "ok", "message": "Status updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update status")

@app.post("/api/history/{record_id}/cover-letter")
@limiter.limit("5/minute")
async def api_generate_cover_letter(request: Request, record_id: int):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")

        record = get_resume_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        file_path = record.get('file_path')
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail="Resume file not found")

        # Verify file path is valid
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=400, detail="Resume file not accessible")

        with open(abs_path, "rb") as f:
            resume_text = extract_text_from_docx(f.read())

        cover_letter = generate_cover_letter(resume_text, record['jd_text'], record['company_name'])

        company_dir = os.path.dirname(abs_path)
        cl_filename = get_output_filename("cover_letter", record_id)
        cl_path = os.path.join(company_dir, cl_filename).replace("\\", "/")

        cl_doc = docx.Document()
        cl_doc.add_paragraph(cover_letter)
        cl_doc.save(cl_path)

        logger.info(f"Cover letter generated for record: {record_id}")
        return {"cover_letter": cover_letter, "cl_path": cl_path}
    except RuntimeError as e:
        logger.warning(f"AI provider error: {e}")
        raise HTTPException(status_code=503, detail="The AI provider is unavailable. Please try again in a few moments.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cover letter generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate cover letter")

class MailDraftSave(BaseModel):
    subject: str
    body: str

@app.post("/api/history/{record_id}/mail-draft")
@limiter.limit("5/minute")
async def api_generate_mail_draft(request: Request, record_id: int):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")

        record = get_resume_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        file_path = record.get('file_path')
        if not file_path:
            raise HTTPException(status_code=400, detail="No file path for this record")

        company_dir = os.path.dirname(file_path)

        # Read ALL files in the company folder for full context
        resume_text = ""
        jd_text = ""
        cover_letter_text = ""
        jd_info_text = ""

        # Read the tailored resume using the exact path from the database
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                resume_text = extract_text_from_docx(f.read())

        # Read other files from the company folder
        if os.path.isdir(company_dir):
            for filename in os.listdir(company_dir):
                filepath = os.path.join(company_dir, filename)
                if filename == "jd_info.txt":
                    with open(filepath, "r", encoding="utf-8") as f:
                        jd_info_text = f.read()
                elif filename.endswith(".docx") and filepath != file_path:
                    # Read cover letter (any docx that isn't the resume)
                    if "cover" in filename.lower() or filename.startswith("cover_letter_"):
                        with open(filepath, "rb") as f:
                            cover_letter_text = extract_text_from_docx(f.read())

        if not resume_text:
            raise HTTPException(status_code=400, detail="Could not read resume text")

        # Use full JD from database (most complete), fall back to jd_info.txt
        jd_text = record.get('jd_text', '') or jd_info_text
        if not jd_text:
            raise HTTPException(status_code=400, detail="No job description found for this record")

        # Read personal profile if it exists (work auth, location, etc.)
        profile_text = ""
        profile_path = os.path.join(DATA_DIR, "profile.txt")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_text = f.read().strip()

        # Extract any email addresses found in the JD
        to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', jd_text)))

        mail = generate_mail_draft(resume_text, jd_text, cover_letter_text, record['company_name'], profile_text)
        return {
            "to_emails": to_emails,
            "subject": mail.get('subject', ''),
            "body": mail.get('body', ''),
        }
    except RuntimeError as e:
        logger.warning(f"AI provider error: {e}")
        raise HTTPException(status_code=503, detail="The AI provider is unavailable. Please try again in a few moments.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mail draft generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate mail draft")

@app.post("/api/history/{record_id}/mail-draft/save")
@limiter.limit("10/minute")
async def save_mail_draft(request: Request, record_id: int, draft: MailDraftSave):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")

        record = get_resume_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        file_path = record.get('file_path')
        if not file_path:
            raise HTTPException(status_code=400, detail="No file path for this record")

        company_dir = os.path.dirname(file_path)
        draft_filename = get_output_filename("mail_draft", record_id)
        draft_path = os.path.join(company_dir, draft_filename).replace("\\", "/")

        content = f"Subject: {draft.subject}\n\n{draft.body}"
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Mail draft saved for record: {record_id}")
        return {"draft_path": draft_path}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save mail draft error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save mail draft")

@app.get("/api/history/{record_id}/content")
@limiter.limit("60/minute")
async def get_record_content(request: Request, record_id: int):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")

        record = get_resume_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        file_path = record.get('file_path', '')
        if not file_path:
            raise HTTPException(status_code=400, detail="No file path for this record")

        company_dir = os.path.dirname(file_path)
        payload = {"company_name": record['company_name'], "cover_letter": None, "cl_path": None, "mail_draft": None, "draft_path": None}

        # Find cover letter files
        cl_files = [f for f in os.listdir(company_dir) if f.startswith("cover_letter_") and f.endswith(".docx")] if os.path.isdir(company_dir) else []
        if cl_files:
            try:
                cl_full_path = os.path.join(company_dir, cl_files[0])
                with open(cl_full_path, "rb") as f:
                    payload["cover_letter"] = extract_text_from_docx(f.read())
                payload["cl_path"] = cl_full_path.replace("\\", "/")
            except Exception:
                pass

        # Find mail draft files
        draft_files = [f for f in os.listdir(company_dir) if f.startswith("mail_draft_") and f.endswith(".txt")] if os.path.isdir(company_dir) else []
        if draft_files:
            try:
                draft_full_path = os.path.join(company_dir, draft_files[0])
                with open(draft_full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.startswith("Subject:"):
                    sep = content.find('\n\n')
                    subject = content[len("Subject:"):sep].strip() if sep != -1 else content[len("Subject:"):].strip()
                    body = content[sep + 2:] if sep != -1 else ""
                else:
                    subject, body = "", content
                to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', record.get('jd_text', ''))))
                payload["mail_draft"] = {"to_emails": to_emails, "subject": subject, "body": body}
                payload["draft_path"] = draft_full_path.replace("\\", "/")
            except Exception:
                pass

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get record content error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve record content")

@app.get("/api/history/csv")
@limiter.limit("10/minute")
async def download_history_csv(request: Request):
    try:
        csv_file = os.path.join(DATA_DIR, "history.csv")
        if not os.path.exists(csv_file):
            raise HTTPException(status_code=404, detail="No history CSV found yet.")
        logger.info("History CSV downloaded")
        return FileResponse(csv_file, filename="resume_history.csv", media_type="text/csv")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download CSV error: {e}")
        raise HTTPException(status_code=500, detail="Failed to download CSV")

@app.get("/api/download/{file_path:path}")
def download_resume(file_path: str):
    try:
        # Security: Prevent path traversal
        safe_path = os.path.basename(file_path)
        full_path = os.path.abspath(os.path.join("trailerd", safe_path))
        base_path = os.path.abspath("trailerd")

        # Verify path is within trailerd directory
        if not full_path.startswith(base_path) or not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Prevent directory listing
        if os.path.isdir(full_path):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(f"Resume downloaded: {safe_path}")
        return FileResponse(full_path, filename=safe_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume download error: {e}")
        raise HTTPException(status_code=500, detail="Failed to download file")

# ─── API Usage Stats ───

@app.get("/api/usage")
async def api_usage():
    """Get API usage statistics and costs."""
    try:
        return get_usage_stats()
    except Exception as e:
        logger.error(f"Usage stats error: {e}")
        return {"today": {"calls": 0, "cost": 0}, "week": {"calls": 0, "cost": 0},
                "month": {"calls": 0, "cost": 0}, "all_time": {"calls": 0, "cost": 0}}

# ─── Personal Profile ───

class ProfileUpdate(BaseModel):
    content: str

@app.get("/api/profile")
async def get_profile():
    """Get the personal profile text."""
    profile_path = os.path.join(DATA_DIR, "profile.txt")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            return {"content": f.read(), "exists": True}
    return {"content": "", "exists": False}

@app.post("/api/profile")
@limiter.limit("10/minute")
async def save_profile(request: Request, profile: ProfileUpdate):
    """Save personal profile — key facts only, never raw documents."""
    try:
        profile_path = os.path.join(DATA_DIR, "profile.txt")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile.content)
        logger.info("Personal profile updated")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Save profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save profile")

@app.post("/api/profile/upload")
@limiter.limit("5/minute")
async def upload_profile_doc(request: Request, file: UploadFile = File(...)):
    """Upload a personal document (PDF, DOCX, image) to extract job-relevant facts.
    Raw file is never stored — only extracted facts are saved to profile."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = file.filename.lower().rsplit('.', 1)[-1] if '.' in file.filename else ''
        allowed = {'pdf', 'docx', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'}
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file type. Use: {', '.join(allowed)}")

        file_bytes = await file.read()
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 10MB.")
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        result = process_uploaded_doc(file_bytes, file.filename)
        logger.info(f"Profile doc processed: {file.filename}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process document")

# ─── Gmail Integration ───

@app.get("/api/gmail/status")
async def gmail_status():
    """Check if Gmail is connected."""
    try:
        return gmail_service.is_connected()
    except Exception as e:
        logger.error(f"Gmail status check error: {e}")
        return {"connected": False}

@app.get("/api/gmail/auth")
async def gmail_auth():
    """Start Gmail OAuth flow — redirects user to Google consent screen."""
    try:
        auth_url = gmail_service.get_auth_url()
        return RedirectResponse(url=auth_url)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Gmail auth error: {e}")
        raise HTTPException(status_code=500, detail="Failed to start Gmail authentication")

@app.get("/api/gmail/callback")
async def gmail_callback(code: str):
    """Handle OAuth callback from Google."""
    try:
        result = gmail_service.handle_callback(code)
        logger.info(f"Gmail connected: {result.get('email', 'unknown')}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend_url}?gmail=connected")
    except Exception as e:
        logger.error(f"Gmail callback error: {e}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend_url}?gmail=error")

@app.post("/api/gmail/disconnect")
async def gmail_disconnect():
    """Disconnect Gmail account."""
    try:
        result = gmail_service.disconnect()
        logger.info("Gmail disconnected")
        return result
    except Exception as e:
        logger.error(f"Gmail disconnect error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect Gmail")

class GmailDraftRequest(BaseModel):
    to_emails: list = []
    subject: str
    body: str
    record_id: Optional[int] = None

@app.post("/api/gmail/save-draft")
@limiter.limit("10/minute")
async def gmail_save_draft(request: Request, draft: GmailDraftRequest):
    """Save email as a draft in Gmail with resume attached."""
    try:
        # Attach the tailored resume if record_id is provided
        attachment_path = None
        if draft.record_id:
            record = get_resume_by_id(draft.record_id)
            if record and record.get('file_path') and os.path.exists(record['file_path']):
                attachment_path = record['file_path']

        result = gmail_service.save_draft(
            to_emails=draft.to_emails,
            subject=draft.subject,
            body=draft.body,
            attachment_path=attachment_path,
        )
        logger.info(f"Gmail draft saved: {result.get('draft_id', 'unknown')}")
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Gmail save draft error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save draft to Gmail")

if __name__ == "__main__":
    # Don't use reload in production
    reload = "--reload" in sys.argv or os.getenv("ENVIRONMENT") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload)

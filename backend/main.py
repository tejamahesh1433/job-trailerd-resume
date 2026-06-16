from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import os
import re
import difflib
import csv
import shutil
import docx
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from services.ai_service import analyze_resume, generate_cover_letter
from services.ollama_service import generate_mail_draft
from services.docx_service import extract_text_from_docx, create_tailored_docx
from database import init_db, save_resume_record, get_all_resumes, delete_resume_record, update_resume_status, get_resume_by_id

limiter = Limiter(key_func=get_remote_address)

def _extract_company_name(jd_text: str) -> str:
    """Best-effort local extraction of company name — no API call."""
    patterns = [
        r'^([A-Z][A-Za-z0-9\s&.,\-]+?)\s+(?:is hiring|is looking|is seeking|seeks|are hiring)',
        r'(?:About|Join)\s+([A-Z][A-Za-z0-9\s&.,\-]{2,40}?)(?:\s*[\n:]|\s+is\b|\s+are\b)',
        r'(?:Company|Employer|Organization)(?:\s+Name)?[:\s]+([^\n]{2,60})',
        r'(?:at|with)\s+([A-Z][A-Za-z0-9\s&.\-]{2,30}?)(?:\s*[,\n]|\s+(?:is|are|a)\b)',
    ]
    for pattern in patterns:
        m = re.search(pattern, jd_text, re.MULTILINE)
        if m:
            name = m.group(1).strip().strip('.,')
            if 2 < len(name) < 60:
                return name
    return "Unknown_Company"

class StatusUpdate(BaseModel):
    status: str

def append_to_csv(company_name, jd_text, before_score, after_score, original_path, tailored_path):
    csv_file = "history.csv"
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
        abs_cl = os.path.join(tail_dir, "tejamahesh_cover-letter.docx") if tail_dir else ""
        abs_mail = os.path.join(tail_dir, "tejamahesh_mail-draft.txt") if tail_dir else ""
        
        # Format for Excel hyperlinks
        orig_link = f'=HYPERLINK("file:///{abs_orig.replace(chr(92), "/")}", "Open Original")' if abs_orig else "N/A"
        tail_link = f'=HYPERLINK("file:///{abs_tail.replace(chr(92), "/")}", "Open Tailored")' if abs_tail else "N/A"
        jd_link = f'=HYPERLINK("file:///{abs_jd.replace(chr(92), "/")}", "Open JD Info")' if abs_jd else "N/A"
        cl_link = f'=HYPERLINK("file:///{abs_cl.replace(chr(92), "/")}", "Open Cover Letter")' if abs_cl else "N/A"
        mail_link = f'=HYPERLINK("file:///{abs_mail.replace(chr(92), "/")}", "Open Mail Draft")' if abs_mail else "N/A"
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            company_name,
            f"{before_score}%",
            f"{after_score}%",
            orig_link,
            tail_link,
            jd_link,
            cl_link,
            mail_link,
            jd_text
        ])

load_dotenv()

# Ensure output directory exists
os.makedirs("trailerd", exist_ok=True)
os.makedirs("original", exist_ok=True)
init_db()

app = FastAPI(title="Job Tailored Resume API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
def list_resumes():
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

@app.post("/api/resumes")
async def upload_named_resume(resume: UploadFile = File(...)):
    if not resume.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")
    file_bytes = await resume.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
    safe_name = re.sub(r"[^\w\-.]", "_", resume.filename)
    file_path = os.path.join("original", safe_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return {"filename": safe_name}

@app.delete("/api/resumes/{filename}")
def delete_named_resume(filename: str):
    safe = os.path.basename(filename)
    file_path = os.path.join("original", safe)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume not found")
    os.remove(file_path)
    return {"status": "ok"}

@app.post("/api/scan")
@limiter.limit("10/minute")
async def scan_resume(request: Request, jd_text: str = Form(...), resume: Optional[UploadFile] = File(None), selected_resume: Optional[str] = Form(None)):
    try:
        if resume:
            file_bytes = await resume.read()
            if len(file_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
            if not resume.filename.endswith('.docx'):
                raise HTTPException(status_code=400, detail="Only .docx files are supported")
            safe_name = re.sub(r'[^\w\-.]', '_', resume.filename)
            original_filename = os.path.join("original", safe_name)
            with open(original_filename, "wb") as f:
                f.write(file_bytes)
        elif selected_resume:
            safe = os.path.basename(selected_resume)
            resume_path = os.path.join("original", safe)
            if not os.path.exists(resume_path):
                raise HTTPException(status_code=400, detail=f"Resume '{safe}' not found.")
            with open(resume_path, "rb") as f:
                file_bytes = f.read()
            original_filename = resume_path
        else:
            base_path = "original/base_resume.docx"
            if not os.path.exists(base_path):
                raise HTTPException(status_code=400, detail="No resume found. Add a resume first.")
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
            
            file_path = f"{company_dir}/tejamahesh_resume.docx"
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
            raise HTTPException(status_code=503, detail="The AI provider is currently overloaded or unavailable. Please try again in a few moments.")
        
        score = result.get('score', 0)
        company_name = result.get('company_name', _extract_company_name(jd_text))
        safe_company_name = "".join([c for c in company_name if c.isalpha() or c.isdigit() or c==' ']).strip()
        company_dir = f"trailerd/{safe_company_name.replace(' ', '_')}"
        os.makedirs(company_dir, exist_ok=True)
        
        file_path = f"{company_dir}/tejamahesh_resume.docx"
        jd_path = f"{company_dir}/jd_info.txt"

        if score >= 85:
            if best_match and best_match['score'] >= 85:
                shutil.copy(best_match['file_path'], file_path)
            else:
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
            after_score = score
            replacements = []
        else:
            replacements = result.get('replacements', [])
            tailored_stream = create_tailored_docx(file_bytes, replacements)
            with open(file_path, "wb") as f:
                f.write(tailored_stream.read())
            after_score = result.get('after_score', score)

        contact_info = result.get('contact_info', {})
        with open(jd_path, "w", encoding="utf-8") as f:
            f.write("Contact Info:\n")
            f.write(f"Name: {contact_info.get('name', 'N/A')}\n")
            f.write(f"Email: {contact_info.get('email', 'N/A')}\n")
            f.write(f"Phone: {contact_info.get('phone', 'N/A')}\n\n")
            f.write("Job Description:\n")
            f.write(jd_text)

        record_id = save_resume_record(company_name, jd_text, after_score, file_path)
        append_to_csv(company_name, jd_text, score, after_score, original_filename, file_path)

        return {
            "id": record_id,
            "score": score,
            "after_score": after_score,
            "company_name": company_name,
            "file_path": file_path,
            "missing_keywords": result.get('missing_keywords', []),
            "section_scores": result.get('section_scores', {}),
            "contact_info": contact_info,
            "replacements": replacements,
            "tailored": len(replacements) > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_history(limit: int = 50, offset: int = 0):
    return get_all_resumes(limit, offset)

@app.delete("/api/history/{record_id}")
def delete_history_item(record_id: int):
    delete_resume_record(record_id)
    return {"status": "ok", "message": "Record deleted"}

@app.patch("/api/history/{record_id}/status")
def patch_history_status(record_id: int, status_update: StatusUpdate):
    update_resume_status(record_id, status_update.status)
    return {"status": "ok", "message": "Status updated"}

@app.post("/api/history/{record_id}/cover-letter")
@limiter.limit("5/minute")
def api_generate_cover_letter(request: Request, record_id: int):
    record = get_resume_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
        
    try:
        file_path = record.get('file_path')
        if not file_path or not os.path.exists(file_path):
             raise HTTPException(status_code=400, detail="Document file not found to extract text from.")
             
        with open(file_path, "rb") as f:
            resume_text = extract_text_from_docx(f.read())
            
        cover_letter = generate_cover_letter(resume_text, record['jd_text'], record['company_name'])

        company_dir = os.path.dirname(file_path)
        cl_path = os.path.join(company_dir, "tejamahesh_cover-letter.docx").replace("\\", "/")
        cl_doc = docx.Document()
        cl_doc.add_paragraph(cover_letter)
        cl_doc.save(cl_path)

        return {"cover_letter": cover_letter, "cl_path": cl_path}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="The AI provider is currently overloaded or unavailable. Please try again in a few moments.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MailDraftSave(BaseModel):
    subject: str
    body: str

@app.post("/api/history/{record_id}/mail-draft")
def api_generate_mail_draft(request: Request, record_id: int):
    record = get_resume_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    try:
        file_path = record.get('file_path')
        if not file_path:
            raise HTTPException(status_code=400, detail="No file path for this record")

        company_dir = os.path.dirname(file_path)

        # Read resume text
        resume_text = ""
        resume_path = os.path.join(company_dir, "tejamahesh_resume.docx")
        if os.path.exists(resume_path):
            with open(resume_path, "rb") as f:
                resume_text = extract_text_from_docx(f.read())

        # Read jd_info.txt (has contact info + full JD)
        jd_info_text = ""
        jd_info_path = os.path.join(company_dir, "jd_info.txt")
        if os.path.exists(jd_info_path):
            with open(jd_info_path, "r", encoding="utf-8") as f:
                jd_info_text = f.read()
        else:
            jd_info_text = record.get('jd_text', '')

        # Read cover letter if it already exists (optional context)
        cover_letter_text = ""
        cl_path = os.path.join(company_dir, "tejamahesh_cover-letter.docx")
        if os.path.exists(cl_path):
            with open(cl_path, "rb") as f:
                cover_letter_text = extract_text_from_docx(f.read())

        # Extract any email addresses found in the JD
        to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', record.get('jd_text', ''))))

        mail = generate_mail_draft(resume_text, jd_info_text, cover_letter_text, record['company_name'])
        return {
            "to_emails": to_emails,
            "subject": mail.get('subject', ''),
            "body": mail.get('body', ''),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/history/{record_id}/mail-draft/save")
def save_mail_draft(record_id: int, draft: MailDraftSave):
    record = get_resume_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    file_path = record.get('file_path')
    if not file_path:
        raise HTTPException(status_code=400, detail="No file path for this record")
    company_dir = os.path.dirname(file_path)
    draft_path = os.path.join(company_dir, "tejamahesh_mail-draft.txt").replace("\\", "/")
    content = f"Subject: {draft.subject}\n\n{draft.body}"
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"draft_path": draft_path}

@app.get("/api/history/{record_id}/content")
def get_record_content(record_id: int):
    record = get_resume_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    file_path = record.get('file_path', '')
    if not file_path:
        raise HTTPException(status_code=400, detail="No file path for this record")

    company_dir = os.path.dirname(file_path)
    payload = {"company_name": record['company_name'], "cover_letter": None, "cl_path": None, "mail_draft": None, "draft_path": None}

    cl_path = os.path.join(company_dir, "tejamahesh_cover-letter.docx")
    if os.path.exists(cl_path):
        try:
            with open(cl_path, "rb") as f:
                payload["cover_letter"] = extract_text_from_docx(f.read())
            payload["cl_path"] = cl_path.replace("\\", "/")
        except Exception:
            pass

    draft_path = os.path.join(company_dir, "tejamahesh_mail-draft.txt")
    if os.path.exists(draft_path):
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("Subject:"):
                sep = content.find('\n\n')
                subject = content[len("Subject:"):sep].strip() if sep != -1 else content[len("Subject:"):].strip()
                body = content[sep + 2:] if sep != -1 else ""
            else:
                subject, body = "", content
            to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', record.get('jd_text', ''))))
            payload["mail_draft"] = {"to_emails": to_emails, "subject": subject, "body": body}
            payload["draft_path"] = draft_path.replace("\\", "/")
        except Exception:
            pass

    return payload

@app.get("/api/history/csv")
def download_history_csv():
    csv_file = "history.csv"
    if not os.path.exists(csv_file):
        raise HTTPException(status_code=404, detail="No history CSV found yet.")
    return FileResponse(csv_file, filename="resume_history.csv")

@app.get("/api/download/{file_path:path}")
def download_resume(file_path: str):
    full_path = os.path.join("trailerd", file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path, filename=os.path.basename(file_path))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

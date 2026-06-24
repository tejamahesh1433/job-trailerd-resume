from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
import asyncio
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
import time
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi.responses import RedirectResponse
from services.ai_service import analyze_resume, generate_cover_letter, analyze_job_metadata
from services.ollama_service import generate_mail_draft, generate_follow_up, detect_w2_fulltime
from services.docx_service import extract_text_from_docx, create_tailored_docx
from services import gmail_service
from services.profile_service import process_uploaded_doc
from services.usage_tracker import get_usage_stats
from database import init_db, save_resume_record, save_job_matcher_record, get_all_resumes, delete_resume_record, update_resume_status, get_resume_by_id, find_existing_company, sanitize_csv_field, search_records, update_user_address

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

_JOB_TITLE_WORDS = {
    "senior", "junior", "lead", "staff", "principal", "manager", "director",
    "engineer", "developer", "architect", "analyst", "administrator", "admin",
    "devops", "sre", "cloud", "software", "platform", "infrastructure",
    "backend", "frontend", "full stack", "fullstack", "remote", "hybrid",
    "onsite", "contract", "full time", "part time", "position", "role",
    "job description", "job title", "responsibilities", "requirements",
    "qualifications", "experience", "we are looking", "about the role",
}

_GENERIC_EMAIL = {"gmail", "yahoo", "hotmail", "outlook", "protonmail",
                  "mail", "icloud", "aol", "live", "ymail", "zoho",
                  "fastmail", "tutanota", "pm", "hey"}

def _is_valid_company_name(name: str) -> bool:
    """Filter out names that are job titles, tech tools, or generic words."""
    lower = name.lower().strip()
    if len(lower) < 3 or len(lower) > 60:
        return False
    if lower in _TECH_TOOLS:
        return False
    words = set(lower.split())
    if words & _JOB_TITLE_WORDS and len(words - _JOB_TITLE_WORDS) == 0:
        return False
    return True

def _scrape_jd_from_url(url: str) -> str:
    """Fetch a URL and extract the job description using structured data + AI cleanup."""
    import requests
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._texts = []
            self._skip = False
            self._skip_tags = {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'head'}
            self._json_ld = []
            self._in_json_ld = False
            self._current_tag = None

        def handle_starttag(self, tag, attrs):
            self._current_tag = tag
            if tag in self._skip_tags:
                self._skip = True
            attrs_dict = dict(attrs)
            if tag == 'script' and attrs_dict.get('type') == 'application/ld+json':
                self._in_json_ld = True
                self._skip = False

        def handle_endtag(self, tag):
            if tag in self._skip_tags:
                self._skip = False
            if tag == 'script':
                self._in_json_ld = False

        def handle_data(self, data):
            if self._in_json_ld:
                self._json_ld.append(data)
            elif not self._skip:
                text = data.strip()
                if text:
                    self._texts.append(text)

        def get_text(self):
            return '\n'.join(self._texts)

        def get_json_ld(self):
            return ''.join(self._json_ld)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    parser = _TextExtractor()
    parser.feed(resp.text)

    # Try JSON-LD structured data first (LinkedIn, Indeed, etc. embed this)
    jd_from_structured = ""
    json_ld_raw = parser.get_json_ld()
    if json_ld_raw:
        try:
            ld_data = json.loads(json_ld_raw)
            if isinstance(ld_data, list):
                ld_data = next((d for d in ld_data if d.get('@type') == 'JobPosting'), ld_data[0] if ld_data else {})
            if isinstance(ld_data, dict):
                parts = []
                if ld_data.get('title'):
                    parts.append(f"Job Title: {ld_data['title']}")
                org = ld_data.get('hiringOrganization', {})
                if isinstance(org, dict) and org.get('name'):
                    parts.append(f"Company: {org['name']}")
                elif isinstance(org, str):
                    parts.append(f"Company: {org}")
                loc = ld_data.get('jobLocation', {})
                if isinstance(loc, dict):
                    addr = loc.get('address', {})
                    if isinstance(addr, dict):
                        loc_parts = [addr.get('addressLocality', ''), addr.get('addressRegion', ''), addr.get('addressCountry', '')]
                        loc_str = ', '.join(p for p in loc_parts if p)
                        if loc_str:
                            parts.append(f"Location: {loc_str}")
                if ld_data.get('employmentType'):
                    parts.append(f"Employment Type: {ld_data['employmentType']}")
                desc = ld_data.get('description', '')
                if desc:
                    # Strip HTML tags from description
                    import re as _re
                    desc_clean = _re.sub(r'<[^>]+>', ' ', desc)
                    desc_clean = _re.sub(r'\s+', ' ', desc_clean).strip()
                    parts.append(f"\n{desc_clean}")
                if parts:
                    jd_from_structured = '\n'.join(parts)
        except (json.JSONDecodeError, StopIteration, TypeError):
            pass

    if jd_from_structured and len(jd_from_structured) >= 100:
        return jd_from_structured

    # Fallback: use raw text but ask AI to extract just the JD
    raw_text = parser.get_text()
    if len(raw_text) < 50:
        raise ValueError("Could not extract enough text from the URL")

    # Use AI to clean up the scraped text
    try:
        from services.ai_service import client as ai_client
        import google.genai as genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"""Extract ONLY the job description from this scraped web page text.
Remove all navigation, ads, cookie notices, sidebar content, and other non-JD text.
Return the clean job description including: job title, company name, location, requirements, responsibilities, qualifications, and any other JD-related content.
If you cannot find a job description, return "NO_JD_FOUND".

Scraped text (first 8000 chars):
{raw_text[:8000]}""",
                config=types.GenerateContentConfig(temperature=0.1),
            )
            cleaned = response.text.strip()
            if cleaned and cleaned != "NO_JD_FOUND" and len(cleaned) >= 50:
                from services.usage_tracker import log_api_call
                usage = response.usage_metadata
                if usage:
                    log_api_call("gemini-2.5-flash", "url_jd_extract",
                                 input_tokens=usage.prompt_token_count or 0,
                                 output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
                return cleaned
    except Exception as e:
        logger.warning(f"AI JD extraction fallback failed: {e}")

    return raw_text

def _extract_company_name(jd_text: str) -> str:
    """Best-effort local extraction of company name — no API call.
    Searches the ENTIRE JD text including signatures at the bottom."""

    # Priority 1: Look for explicit company name lines (often near signatures)
    company_patterns = [
        r'(?:Company|Employer|Organization|Firm|Client|Hiring\s+Company)(?:\s+Name)?[:\s]+([^\n]{2,60})',
        r'^([A-Z][A-Za-z0-9\s&.,\-]+?)\s+(?:is hiring|is looking|is seeking|seeks|are hiring|has an opening)',
        r'(?:About|Join|Work\s+at|Working\s+at)\s+([A-Z][A-Za-z0-9\s&.,\-]{2,40}?)(?:\s*[\n:]|\s+is\b|\s+are\b)',
        r'(?:at|@)\s+([A-Z][A-Za-z0-9\s&.\-]{2,40}?)(?:\s*[\n,.]|\s+in\b|\s+for\b|\s*$)',
        r'(?:Role|Position|Title|Job|Opportunity)\s*(?:at|with|@|[-–])\s*([A-Z][A-Za-z0-9\s&.\-]{2,40})',
        r'^([A-Z][A-Za-z0-9\s&.\-]{2,40}?)\s*[-–|]\s*(?:Job|Role|Position|Career|Hiring|Opening)',
        r'(?:Employer|Hiring\s+Company)[:\s]+([^\n]{2,60})',
        r'(?:on behalf of|client|end[\s-]?client)[:\s]+([^\n]{2,60})',
    ]
    for pattern in company_patterns:
        m = re.search(pattern, jd_text, re.MULTILINE | re.IGNORECASE)
        if m:
            name = m.group(1).strip().strip('.,')
            if _is_valid_company_name(name):
                return name

    # Priority 2: Extract from "Company Inc/LLC/Ltd/Corp" patterns anywhere in text
    for line in jd_text.split('\n'):
        corp_match = re.search(
            r'([A-Z][A-Za-z0-9]+(?:[\s&]+[A-Z][A-Za-z0-9]+)*)\s+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Pvt\.?|Private|Limited|Group|Consulting|Solutions|Technologies|Services|Staffing|Partners|Associates)',
            line.strip()
        )
        if corp_match:
            name = corp_match.group(0).strip().strip('.,')
            if _is_valid_company_name(name):
                return name

    # Priority 3: Extract from email domain (search ALL emails in the JD)
    all_emails = re.findall(r'[\w.+-]+@([\w-]+)\.\w{2,}', jd_text)
    for domain in all_emails:
        if domain.lower() not in _GENERIC_EMAIL and len(domain) > 2:
            return domain.replace('-', ' ').title()

    # Priority 4: Look for "Web: www.company.com" or website patterns near signatures
    web_match = re.search(r'(?:Web|Website|URL|Visit\s+us)[:\s]+(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+)\.\w{2,}', jd_text, re.IGNORECASE)
    if web_match:
        domain = web_match.group(1).strip()
        if domain.lower() not in _GENERIC_EMAIL and len(domain) > 2:
            return domain.replace('-', ' ').title()

    # Priority 5: Any URL in the text (e.g. https://company.com/careers)
    _URL_BLACKLIST = {'linkedin', 'indeed', 'glassdoor', 'ziprecruiter', 'lever',
                      'greenhouse', 'workday', 'icims', 'smartrecruiters', 'jobvite',
                      'google', 'apply', 'dice', 'monster', 'careerbuilder', 'hired',
                      'angel', 'wellfound', 'simplyhired', 'recruiter', 'zoom', 'teams'}
    url_match = re.search(r'https?://(?:www\.)?([a-zA-Z0-9-]+)\.(?:com|io|org|co|net|ai)\b', jd_text, re.IGNORECASE)
    if url_match:
        domain = url_match.group(1).strip()
        if domain.lower() not in _GENERIC_EMAIL and domain.lower() not in _URL_BLACKLIST and len(domain) > 2:
            return domain.replace('-', ' ').title()

    # Priority 6: Phone number with company signature — look for a name on the line before a phone
    lines = jd_text.strip().split('\n')
    for i, line in enumerate(lines):
        if re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', line):
            if i > 0:
                prev = lines[i - 1].strip()
                if prev and len(prev) < 50 and not re.match(r'^[\d(+]', prev):
                    candidate = re.sub(r'[,|–\-].*$', '', prev).strip()
                    if _is_valid_company_name(candidate) and not re.search(r'@', candidate):
                        return candidate

    return "Unknown_Company"


def _make_company_dir(company_name: str, email: str = "") -> str:
    """Build a unique trailerd/<company> directory path. Uses email if unknown, appends _1, _2 if duplicate."""
    safe = "".join([c for c in company_name if c.isalpha() or c.isdigit() or c == ' ' or c == '@' or c == '.']).strip()
    if not safe or safe.lower() in ("unknown company", "unknowncompany", "unknown", "unknown_company"):
        if email and isinstance(email, str) and '@' in email:
            safe = email.split('@')[0]
            safe = "".join([c for c in safe if c.isalnum()]).strip()
        
        if not safe or safe.lower() in ("unknown company", "unknowncompany", "unknown", "unknown_company"):
            safe = "Unknown"

    safe = safe.replace(' ', '_')
    base_dir = f"trailerd/{safe}"
    
    # Handle duplicates by appending _1, _2, etc.
    company_dir = base_dir
    counter = 1
    while os.path.exists(company_dir):
        company_dir = f"{base_dir}_{counter}"
        counter += 1
        
    os.makedirs(company_dir, exist_ok=True)
    return company_dir

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

class BatchScanRequest(BaseModel):
    jd_texts: List[str]
    selected_resume: str
    ai_notes: Optional[str] = None

def _extract_experience_years(jd_text: str) -> int:
    """Extract the maximum years of experience required from a JD.
    Handles: '11+ Years', '10-15 years experience', '84 months', etc."""
    text_lower = jd_text.lower()
    max_years = 0

    # Range patterns: "10-15 years experience"
    range_pattern = r'(\d{1,2})\s*[\-–to]+\s*\d{1,2}\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,3}\s*(?:experience|exp\b)'
    for m in re.finditer(range_pattern, text_lower):
        years = int(m.group(1))
        if 1 <= years <= 30:
            max_years = max(max_years, years)

    text_no_ranges = re.sub(r'\d{1,2}\s*[\-–to]+\s*\d{1,2}\s*(?:years?|yrs?)', '', text_lower)

    patterns = [
        # "11+ years of experience", "5 years experience"
        r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,3}\s*(?:experience|exp\b|professional)',
        # "minimum 10 years", "at least 8 years", "requires 12 years"
        r'(?:minimum|min\.?|at\s+least|over|requires?|must\s+have)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)',
        # "experience: 10+ years"
        r'(?:experience|exp)\s*(?:required)?[:\s]+(\d{1,2})\s*\+?\s*(?:years?|yrs?)',
        # "10+ years in DevOps/cloud/IT"
        r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:in\s+(?:the\s+)?(?:industry|field|role|domain|it\b|devops|cloud|software))',
        # "10+ years working/hands-on/relevant"
        r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:working|hands[\-\s]on|relevant|total|overall|progressive)',
        # "11+ Years Candidates Only" — number + years + any word (catch-all for title lines)
        r'(\d{1,2})\s*\+\s*(?:years?|yrs?)\s+(?:candidates?|only|required|mandatory)',
        # Standalone "11+ years" or "11+ yrs" (with the + sign = explicit requirement)
        r'\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b',
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text_no_ranges):
            years = int(m.group(1))
            if 1 <= years <= 30:
                max_years = max(max_years, years)

    # Convert months to years: "84 months of experience" = 7 years
    month_patterns = [
        r'(\d{2,3})\s*(?:months?|mos?\.?)(?:\s+of)?(?:\s+\w+){0,3}\s*(?:experience|exp\b)',
        r'(\d{2,3})\s*\+?\s*(?:months?|mos?\.?)\s+(?:in\s+|of\s+)',
    ]
    for pattern in month_patterns:
        for m in re.finditer(pattern, text_lower):
            months = int(m.group(1))
            if 6 <= months <= 360:
                years = months // 12
                max_years = max(max_years, years)

    return max_years

def _check_lead_role(jd_text: str) -> str | None:
    """Return a skip reason if the JD is for a lead/management position, else None."""
    text_lower = jd_text.lower()

    # Check the job title area (first 500 chars where the title usually is)
    title_area = text_lower[:500]

    # Lead patterns
    lead_patterns = [
        r'\blead\s+(?:sre|devops|site\s+reliability)\b',
        r'\blead\s+(?:software|platform|cloud|infrastructure|systems?|backend|frontend|full[\s-]?stack)\s+engineer\b',
        r'\blead\s+(?:developer|architect|admin|administrator|engineer)\b',
        r'\b(?:sre|devops|software|platform|cloud|infrastructure|engineering)\s+lead\b',
        r'\btechnical\s+lead\b',
        r'\btech\s+lead\b',
        r'\bteam\s+lead\b',
        r'\bsr\.?\s+lead\b',
    ]

    # Management/senior leadership patterns (check title area only)
    mgmt_patterns = [
        r'\bengineering\s+manager\b',
        r'\bdevops\s+manager\b',
        r'\binfrastructure\s+manager\b',
        r'\bplatform\s+manager\b',
        r'\bcloud\s+manager\b',
        r'\bsre\s+manager\b',
        r'\bit\s+manager\b',
        r'\bmanager[,\s]+(?:devops|sre|infrastructure|platform|cloud|engineering)\b',
        r'\bdirector\s+of\s+(?:engineering|devops|infrastructure|platform|sre|it|operations|technology)\b',
        r'\bvp\s+(?:of\s+)?(?:engineering|infrastructure|devops|platform|operations|technology)\b',
        r'\bvice\s+president\b',
        r'\bhead\s+of\s+(?:engineering|devops|infrastructure|platform|sre|it|operations)\b',
        r'\bchief\s+(?:technology|information|infrastructure)\s+officer\b',
        r'\b(?:cto|cio)\b',
        r'\bprincipal\s+(?:engineer|architect|devops|sre)\b',
        r'\bstaff\s+(?:engineer|architect|devops|sre)\b',
    ]

    for pattern in lead_patterns:
        if re.search(pattern, text_lower):
            return "JD is for a lead-level position — skipping"

    for pattern in mgmt_patterns:
        if re.search(pattern, title_area):
            return "JD is for a management/senior leadership role — skipping"

    return None

def _check_visa_eligibility(jd_text: str) -> str | None:
    """Return a detailed skip reason if the JD is not GC-friendly, else None."""
    text_lower = jd_text.lower()

    explicit_exclusions = [
        r'\bno\s+green\s*card\b',
        r'\bno\s+gc\b',
        r'\bfake\s+gc\b',
        r'\bfake\s+green\s*card\b',
        r'\bgc\s+not\s+accepted\b',
        r'\bgreen\s*card\s+not\s+accepted\b',
    ]
    for pattern in explicit_exclusions:
        if re.search(pattern, text_lower):
            return "Rejected: JD explicitly excludes Green Card holders"

    gc_patterns = [
        r'\bgreen\s*card\b', r'\bgc\b', r'\bpermanent\s+resident\b',
        r'\bpermanent\s+residency\b', r'\busc\b', r'\bus\s+citizen\b',
        r'\bcitizen\b',
    ]

    visa_labels = {
        r'\bh[- ]?1b\b': 'H-1B',
        r'\bh[- ]?1\b': 'H-1',
        r'\bopt\b': 'OPT',
        r'\bcpt\b': 'CPT',
        r'\btn\s+visa\b': 'TN Visa',
        r'\bl[- ]?1\b': 'L-1',
        r'\bl[- ]?2\b': 'L-2',
        r'\be[- ]?2\b': 'E-2',
        r'\be[- ]?3\b': 'E-3',
        r'\bo[- ]?1\b': 'O-1',
        r'\bf[- ]?1\b': 'F-1',
        r'\bj[- ]?1\b': 'J-1',
        r'\bead\b': 'EAD',
        r'\bwork\s+permit\b': 'Work Permit',
        r'\bsponsorship\b': 'Visa Sponsorship',
        r'\bvisa\s+sponsor\b': 'Visa Sponsor',
        r'\bw2\s+only\b': 'W2 Only',
        r'\bus\s+citizens?\s+only\b': 'US Citizens Only',
    }

    has_gc = any(re.search(p, text_lower) for p in gc_patterns)
    found_visas = [label for pattern, label in visa_labels.items() if re.search(pattern, text_lower)]

    if found_visas and not has_gc:
        visa_list = ', '.join(sorted(set(found_visas)))
        return f"Rejected: JD requires [{visa_list}] — Green Card not listed as accepted"

    return None

def _check_foreign_language(jd_text: str) -> str | None:
    """Return a skip reason if the JD strictly requires a foreign language, else None."""
    text_lower = jd_text.lower()
    languages = r'(chinese|mandarin|spanish|mexican|french|german|japanese|korean|russian|arabic|portuguese|italian|hindi)'
    
    patterns = [
        languages + r'\s*\(?required\)?',
        languages + r'\s*is\s*required',
        r'\b(?:required|mandatory|must)\b.{0,30}' + languages,
        r'\b(?:fluent|native|bilingual)\b.{0,30}' + languages + r'.{0,30}\b(?:required|mandatory|must)\b',
        languages + r'.{0,30}\b(?:fluent|native|bilingual)\b.{0,30}\b(?:required|mandatory|must)\b'
    ]
    
    for p in patterns:
        if re.search(p, text_lower):
            return "JD explicitly requires a foreign language"
            
    return None

def _check_employment_type(jd_text: str) -> tuple[str, str | None]:
    """
    Check employment type: C2C, C2H, Full-time, W2
    Return: (employment_type, warning_if_rejected)
    User accepts ONLY C2C or C2H contracts, rejects full-time/W2
    """
    text_lower = jd_text.lower()

    # Check for explicit C2C patterns (strong signals only)
    c2c_patterns = [
        r'\bc2c\b', r'\bcorp[\s-]to[\s-]corp\b', r'\bcorp-to-corp\b',
        r'\b1099\b', r'\bindependent\s+contractor\b',
    ]

    # Check for C2H patterns
    c2h_patterns = [
        r'\bc2h\b', r'\bcontract[\s-]to[\s-]hire\b', r'\bcontract[\s-]hire\b',
        r'\bcontract\s+to\s+perm\b',
    ]

    # Check for W2/Full-time patterns
    w2_patterns = [
        r'\bw2\b', r'\bw-2\b',
        r'\bfull[\s-]?time\s+(?:position|role|opportunity|employment|employee)\b',
        r'\bfulltime\b',
        r'\bpermanent\s+(?:position|role|employee|employment)\b',
        r'\bdirect\s+hire\b',
        r'\bsalaried\s+(?:position|role|employee)\b',
    ]

    # Check for contract (weaker signal — only if no W2 signals)
    contract_patterns = [
        r'\bcontract\s+(?:position|role|opportunity|assignment|engagement)\b',
        r'\bcontractor\s+(?:position|role)\b',
        r'\b(?:6|12|18)\s*[\+]?\s*month\s+contract\b',
        r'\bcontract\s+duration\b',
    ]

    has_c2c = any(re.search(p, text_lower) for p in c2c_patterns)
    has_c2h = any(re.search(p, text_lower) for p in c2h_patterns)
    has_w2 = any(re.search(p, text_lower) for p in w2_patterns)
    has_contract = any(re.search(p, text_lower) for p in contract_patterns)

    # W2 check first — if it says "full-time" or "W2", reject even if "contract" appears elsewhere
    if has_w2 and not has_c2c and not has_c2h:
        return ('w2', "This is a W2/Full-time position. You prefer C2C/C2H contracts.")

    if has_c2c:
        return ('c2c', None)
    if has_c2h:
        return ('c2h', None)
    if has_contract:
        return ('contract', None)

    # Default: unclear employment type — pass as soft warning, not hard reject
    return ('unknown', None)

def extract_job_keywords(jd_text: str) -> dict:
    """
    Phase 1: Extract tech keywords from job description
    Returns dict with keyword categories and found keywords
    """
    text_lower = jd_text.lower()

    keyword_groups = {
        'devops': [
            'kubernetes', 'k8s', 'docker', 'container', 'orchestration',
            'terraform', 'ansible', 'infrastructure', 'iac', 'infrastructure as code',
            'aws', 'gcp', 'azure', 'cloud', 'ec2', 's3', 'lambda',
            'ci/cd', 'jenkins', 'gitlab', 'github', 'circleci', 'travis',
            'monitoring', 'prometheus', 'datadog', 'grafana', 'elastic',
            'linux', 'bash', 'shell', 'scripting', 'python',
            'helm', 'helm charts', 'argocd', 'flux', 'gitops',
            'nginx', 'apache', 'haproxy', 'load balancer',
        ],
        'sre': [
            'site reliability', 'sre', 'reliability', 'uptime', 'availability',
            'slo', 'sla', 'oncall', 'on-call', 'pagerduty',
            'incident', 'incident response', 'incident management',
            'postmortem', 'blameless', 'runbook',
            'observability', 'logging', 'tracing', 'metrics',
        ],
        'platform': [
            'platform engineer', 'platform team', 'internal platform',
            'developer platform', 'developer experience', 'devex',
            'self-service', 'automation', 'tooling',
        ],
        'security': [
            'security', 'infosec', 'secops', 'infrastructure security',
            'compliance', 'audit', 'vulnerability', 'scanning',
            'iam', 'identity', 'access management', 'iam',
            'encryption', 'tls', 'ssl', 'certificates',
        ],
    }

    found = {}
    for category, keywords in keyword_groups.items():
        found[category] = []
        for keyword in keywords:
            if keyword in text_lower:
                found[category].append(keyword)

    return found

def calculate_match_score(years_required: int, keywords: dict, employment_type: str) -> int:
    """
    Calculate overall job match percentage (0-100)
    Based on: experience years, keyword overlap, employment type match
    """
    score = 100

    # Experience deduction: each year over 10 costs 2 points
    if years_required > 10:
        score -= min(20, (years_required - 10) * 2)

    # Employment type deduction
    if employment_type == 'w2':
        score -= 30  # Major deduction for W2 (not acceptable)
    elif employment_type == 'unknown':
        score -= 10  # Minor deduction for unclear type

    # Keyword match bonus (small positive impact)
    total_keywords = sum(len(kws) for kws in keywords.values())
    if total_keywords >= 3:
        score += 5
    elif total_keywords == 0:
        score -= 10

    return max(0, min(100, score))  # Clamp to 0-100

def _csv_header():
    return ["Timestamp", "Company Name", "Before Score", "After Score", "Status", "Skip Reason", "Original Resume", "Tailored Resume", "JD Info", "Cover Letter", "Mail Draft", "Job Description", "Source", "Source URL", "Job Fit %", "Rejection Reason"]

def append_to_csv(company_name, jd_text, before_score, after_score, original_path, tailored_path):
    csv_file = os.path.join(DATA_DIR, "history.csv")
    file_exists = os.path.exists(csv_file)

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(_csv_header())

        abs_orig = os.path.abspath(original_path) if original_path else ""
        abs_tail = os.path.abspath(tailored_path) if tailored_path else ""

        tail_dir = os.path.dirname(abs_tail) if abs_tail else ""
        abs_jd = os.path.join(tail_dir, "jd_info.txt") if tail_dir else ""
        abs_cl_search = [f for f in os.listdir(tail_dir) if f.startswith("cover_letter_")] if tail_dir and os.path.isdir(tail_dir) else []
        abs_mail_search = [f for f in os.listdir(tail_dir) if f.startswith("mail_draft_")] if tail_dir and os.path.isdir(tail_dir) else []

        abs_cl = os.path.join(tail_dir, abs_cl_search[0]) if abs_cl_search else ""
        abs_mail = os.path.join(tail_dir, abs_mail_search[0]) if abs_mail_search else ""

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
            "Processed",
            "",
            orig_link,
            tail_link,
            jd_link,
            cl_link,
            mail_link,
            sanitize_csv_field(jd_text[:1000]),
            "dashboard",
            "",
            "",
            ""
        ])

def append_skipped_to_csv(jd_text, skip_reason):
    csv_file = os.path.join(DATA_DIR, "history.csv")
    file_exists = os.path.exists(csv_file)

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(_csv_header())

        company_name = _extract_company_name(jd_text) if len(jd_text) >= 50 else "Unknown"
        writer.writerow([
            sanitize_csv_field(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            sanitize_csv_field(company_name),
            "N/A",
            "N/A",
            "Skipped",
            sanitize_csv_field(skip_reason),
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            sanitize_csv_field(jd_text[:1000]),
            "dashboard",
            "",
            "",
            ""
        ])

def append_job_matcher_to_csv(company_name, jd_text, match_pct, status, rejection_reason="", source_url=""):
    csv_file = os.path.join(DATA_DIR, "history.csv")
    file_exists = os.path.exists(csv_file)

    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(_csv_header())

        writer.writerow([
            sanitize_csv_field(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            sanitize_csv_field(company_name),
            "N/A",
            "N/A",
            sanitize_csv_field(status),
            "",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            sanitize_csv_field(jd_text[:1000]),
            "job-finder",
            sanitize_csv_field(source_url or ""),
            sanitize_csv_field(f"{match_pct}%") if match_pct is not None else "N/A",
            sanitize_csv_field(rejection_reason),
        ])

# Ensure output directory exists
os.makedirs("trailerd", exist_ok=True)
os.makedirs("original", exist_ok=True)
init_db()

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Job Tailored Resume API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)

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
async def scan_resume(request: Request, jd_text: str = Form(...), resume: Optional[UploadFile] = File(None), selected_resume: Optional[str] = Form(None), ai_notes: Optional[str] = Form(None)):
    try:
        # Validate JD text length
        if not jd_text or len(jd_text) > 50000:
            raise HTTPException(status_code=400, detail="Invalid job description")

        if len(jd_text) < 50:
            append_skipped_to_csv(jd_text, "JD too short (min 50 chars)")
            raise HTTPException(status_code=400, detail="Job description too short (minimum 50 characters)")

        years = _extract_experience_years(jd_text)
        if years > 10:
            reason = f"Requires {years}+ years experience (max allowed: 10)"
            append_skipped_to_csv(jd_text, reason)
            raise HTTPException(status_code=400, detail=reason)

        gc_reason = _check_visa_eligibility(jd_text)
        if gc_reason:
            append_skipped_to_csv(jd_text, gc_reason)
            raise HTTPException(status_code=400, detail=gc_reason)

        lang_reason = _check_foreign_language(jd_text)
        if lang_reason:
            append_skipped_to_csv(jd_text, lang_reason)
            raise HTTPException(status_code=400, detail=lang_reason)

        lead_reason = _check_lead_role(jd_text)
        if lead_reason:
            append_skipped_to_csv(jd_text, lead_reason)
            raise HTTPException(status_code=400, detail=lead_reason)

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

        # ── Duplicate JD check ──
        all_history = get_all_resumes(limit=1000)
        for item in all_history:
            if not item.get('jd_text'):
                continue
            ratio = difflib.SequenceMatcher(None, jd_text, item['jd_text']).ratio()
            if ratio >= 0.95:
                company = item.get('company_name', 'Unknown')
                score = item.get('score', 0)
                logger.info(f"Duplicate JD rejected — {ratio:.0%} match with {company} (score={score})")
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate JD — already scanned for {company} (score: {score}%). Check your Production Log."
                )

        # ── AI analysis ──
        try:
            result = analyze_resume(resume_text, jd_text, ai_notes=ai_notes or "")
        except RuntimeError as e:
            logger.warning(f"AI provider unavailable: {e}")
            raise HTTPException(status_code=503, detail="The AI provider is currently unavailable. Please try again in a few moments.")

        score = result.get('score', 0)
        company_name = result.get('company_name', _extract_company_name(jd_text))
        contact_info = result.get('contact_info', {})
        jd_emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', jd_text)
        vendor_email = next((e for e in jd_emails if e.split('@')[1].split('.')[0].lower() not in _GENERIC_EMAIL), '')
        company_dir = _make_company_dir(company_name, vendor_email)

        file_path = f"{company_dir}/resume.docx"
        jd_path = f"{company_dir}/jd_info.txt"
        diff_path = f"{company_dir}/difference.txt"

        replacements = result.get('replacements', [])
        after_score = result.get('after_score', score)

        # ── Decide: skip tailoring, reuse existing, or create new ──
        if score >= 85:
            # Base resume already strong — copy original, keep AI's after_score
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            # after_score stays as AI calculated (may equal score)
            replacements = []
            logger.info(f"Score {score}% >= 85% for {company_name} — no tailoring needed")
            with open(diff_path, "w", encoding="utf-8") as f:
                f.write(f"Score: {score}% — already above 85%%, no tailoring needed.\n")

        elif replacements:
            tailored_stream = create_tailored_docx(file_bytes, replacements)
            with open(file_path, "wb") as f:
                f.write(tailored_stream.read())
            logger.info(f"Applied {len(replacements)} replacements for {company_name}")

            missing_kw = result.get('missing_keywords', [])
            with open(diff_path, "w", encoding="utf-8") as f:
                f.write(f"Resume Tailoring Differences for {company_name}\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Score: {score}% → {after_score}% (Δ +{after_score - score})\n")
                f.write(f"Total Replacements: {len(replacements)}\n")
                if missing_kw:
                    f.write(f"Missing Keywords: {', '.join(missing_kw)}\n")
                f.write("=" * 60 + "\n\n")
                for i, rep in enumerate(replacements, 1):
                    kw_added = rep.get('keywords_added', [])
                    f.write(f"--- REPLACEMENT #{i} ---\n")
                    if kw_added:
                        f.write(f"Keywords Added: {', '.join(kw_added)}\n\n")
                    f.write(f"REMOVED:\n{rep.get('original', 'N/A')}\n\n")
                    f.write(f"ADDED:\n{rep.get('new', 'N/A')}\n")
                    f.write("=" * 60 + "\n\n")
        else:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            after_score = score
            with open(diff_path, "w", encoding="utf-8") as f:
                f.write("No changes were needed. The resume already matched the job description well.\n")

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

def _process_single_jd(jd_text: str, file_bytes: bytes, original_filename: str, ai_notes: str = "") -> dict:
    resume_text = extract_text_from_docx(file_bytes)

    # Duplicate JD check
    all_history = get_all_resumes(limit=1000)
    for item in all_history:
        if not item.get('jd_text'):
            continue
        ratio = difflib.SequenceMatcher(None, jd_text, item['jd_text']).ratio()
        if ratio >= 0.95:
            company = item.get('company_name', 'Unknown')
            return {
                "skipped": True,
                "reason": f"Duplicate JD — already scanned for {company} (score: {item.get('score', 0)}%)",
            }

    result = None
    for attempt in range(3):
        try:
            result = analyze_resume(resume_text, jd_text, ai_notes=ai_notes)
            break
        except RuntimeError as e:
            if attempt < 2 and ("503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e) or "All models" in str(e)):
                wait = (attempt + 1) * 10
                logger.warning(f"AI unavailable (attempt {attempt + 1}/3), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    if result is None:
        raise RuntimeError("AI unavailable after 3 attempts")

    score = result.get('score', 0)
    ai_company = result.get('company_name', '')
    local_company = _extract_company_name(jd_text)

    contact_info = result.get('contact_info', {})
    jd_emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', jd_text)
    vendor_email = next((e for e in jd_emails if e.split('@')[1].split('.')[0].lower() not in _GENERIC_EMAIL), '')

    if ai_company and ai_company not in ('Unknown_Company', 'Unknown', ''):
        company_name = ai_company
    elif local_company != 'Unknown_Company':
        company_name = local_company
    elif vendor_email:
        company_name = vendor_email
    else:
        company_name = ai_company or local_company
    company_dir = _make_company_dir(company_name, vendor_email)
    file_path = f"{company_dir}/resume.docx"
    jd_path = f"{company_dir}/jd_info.txt"
    diff_path = f"{company_dir}/difference.txt"

    replacements = result.get('replacements', [])
    after_score = result.get('after_score', score)

    if score >= 85:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        replacements = []
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write(f"Score: {score}% — already above 85%, no tailoring needed.\n")

    elif replacements:
        tailored_stream = create_tailored_docx(file_bytes, replacements)
        with open(file_path, "wb") as f:
            f.write(tailored_stream.read())
        missing_kw = result.get('missing_keywords', [])
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write(f"Resume Tailoring Differences for {company_name}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Score: {score}% → {after_score}% (Δ +{after_score - score})\n")
            f.write(f"Total Replacements: {len(replacements)}\n")
            if missing_kw:
                f.write(f"Missing Keywords: {', '.join(missing_kw)}\n")
            f.write("=" * 60 + "\n\n")
            for i, rep in enumerate(replacements, 1):
                kw_added = rep.get('keywords_added', [])
                f.write(f"--- REPLACEMENT #{i} ---\n")
                if kw_added:
                    f.write(f"Keywords Added: {', '.join(kw_added)}\n\n")
                f.write(f"REMOVED:\n{rep.get('original', 'N/A')}\n\n")
                f.write(f"ADDED:\n{rep.get('new', 'N/A')}\n")
                f.write("=" * 60 + "\n\n")
    else:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        after_score = score
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write("No changes were needed. The resume already matched the job description well.\n")

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
        "score": score, "after_score": after_score,
        "missing_keywords": result.get('missing_keywords', []),
        "section_scores": result.get('section_scores', {}),
        "contact_info": contact_info, "replacements": replacements,
    }
    record_id = save_resume_record(company_name, jd_text, after_score, file_path, json.dumps(scan_data))
    append_to_csv(company_name, jd_text, score, after_score, original_filename, file_path)
    return {
        "id": record_id, "company_name": company_name, "file_path": file_path,
        "tailored": len(replacements) > 0,
        "duplicate": existing is not None,
        "previous_score": existing['score'] if existing else None, **scan_data,
    }

@app.post("/api/batch-scan")
@limiter.limit("3/minute")
async def batch_scan(request: Request, body: BatchScanRequest):
    try:
        if len(body.jd_texts) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 JDs per batch")
        if len(body.jd_texts) == 0:
            raise HTTPException(status_code=400, detail="No JDs provided")

        safe = os.path.basename(body.selected_resume)
        resume_path = os.path.join("original", safe)
        abs_path = os.path.abspath(resume_path)
        abs_base = os.path.abspath("original")
        if not abs_path.startswith(abs_base):
            raise HTTPException(status_code=400, detail="Resume not found")
        if not os.path.exists(resume_path):
            raise HTTPException(status_code=400, detail="Resume not found")
        if os.path.getsize(resume_path) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Resume file too large")

        with open(resume_path, "rb") as f:
            file_bytes = f.read()

        results = []

        for idx, jd_text in enumerate(body.jd_texts):
            if not jd_text or len(jd_text) < 50:
                reason = "JD too short (min 50 chars)"
                results.append({"index": idx, "skipped": True, "reason": reason})
                append_skipped_to_csv(jd_text or "", reason)
                continue
            if len(jd_text) > 50000:
                reason = "JD too long (max 50000 chars)"
                results.append({"index": idx, "skipped": True, "reason": reason})
                append_skipped_to_csv(jd_text[:50000], reason)
                continue

            years = _extract_experience_years(jd_text)
            if years > 10:
                reason = f"Requires {years}+ years experience (max allowed: 10)"
                results.append({"index": idx, "skipped": True, "reason": reason})
                append_skipped_to_csv(jd_text, reason)
                continue

            gc_reason = _check_visa_eligibility(jd_text)
            if gc_reason:
                results.append({"index": idx, "skipped": True, "reason": gc_reason})
                append_skipped_to_csv(jd_text, gc_reason)
                continue

            lang_reason = _check_foreign_language(jd_text)
            if lang_reason:
                results.append({"index": idx, "skipped": True, "reason": lang_reason})
                append_skipped_to_csv(jd_text, lang_reason)
                continue

            lead_reason = _check_lead_role(jd_text)
            if lead_reason:
                results.append({"index": idx, "skipped": True, "reason": lead_reason})
                append_skipped_to_csv(jd_text, lead_reason)
                continue

            try:
                result = _process_single_jd(jd_text, file_bytes, resume_path, ai_notes=body.ai_notes or "")
                result["index"] = idx
                result["skipped"] = False
                results.append(result)
                logger.info(f"Batch JD #{idx + 1} done: {result.get('company_name', 'Unknown')}")
            except Exception as e:
                logger.error(f"Batch scan error for JD #{idx}: {e}", exc_info=True)
                reason = f"Processing failed: {str(e)}"
                results.append({"index": idx, "skipped": True, "reason": reason})
                append_skipped_to_csv(jd_text, reason)

            if idx < len(body.jd_texts) - 1:
                time.sleep(2)
        logger.info(f"Batch scan completed: {len(body.jd_texts)} JDs, {sum(1 for r in results if not r.get('skipped'))} processed, {sum(1 for r in results if r.get('skipped'))} skipped")
        return {"results": results, "total": len(body.jd_texts), "processed": sum(1 for r in results if not r.get('skipped')), "skipped": sum(1 for r in results if r.get('skipped'))}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch scan error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Batch processing failed. Please try again later.")

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
@app.get("/api/addresses")
@limiter.limit("60/minute")
async def get_addresses(request: Request):
    from database import get_all_addresses
    from services.ollama_service import _extract_recruiter_name
    import re
    try:
        records = get_all_addresses()
        results = []
        for rec in records:
            jd = rec.get("jd_text") or ""
            
            emails_found = set()
            for m in re.finditer(r'[\w.+-]+@[\w-]+\.[\w.-]+', jd):
                emails_found.add(m.group().lower())
                
            emails_list = list(emails_found)
            email = emails_list[0] if emails_list else ""
            
            # Extract phone number with extension if available
            phones = re.findall(r'(?:\+?\d{1,2}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?:\s*(?:ext\.?|x|ext\s*:)\s*:?\s*\d+)?', jd, re.IGNORECASE)
            phone = phones[0].strip() if phones else ""
            
            # Fallback to extracting name
            from services.ollama_service import _extract_recruiter_name
            name = _extract_recruiter_name(jd)
            
            results.append({
                "id": rec["id"],
                "company_name": rec["company_name"],
                "user_address": rec["user_address"],
                "phone": phone,
                "name": name,
                "email": email,
                "all_emails": emails_list
            })
        return results
    except Exception as e:
        logger.error(f"Get addresses error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve addresses")

@app.get("/api/search")
@limiter.limit("30/minute")
async def search_history(request: Request, q: str = "", limit: int = 50):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    try:
        limit = min(max(limit, 1), 100)
        records = search_records(q.strip(), limit)
        results = []
        for rec in records:
            jd = rec.get("jd_text") or ""
            sr = rec.get("scan_result") or {}
            contact = sr.get("contact_info") or {}

            emails_found = set()
            for m in re.finditer(r'[\w.+-]+@[\w-]+\.[\w.-]+', jd):
                emails_found.add(m.group().lower())

            jd_lower = jd.lower()
            location = "Not specified"
            loc_m = re.search(r'(?:location|city|office|based in|work location)[:\s]*([^\n]{3,60})', jd, re.IGNORECASE)
            if loc_m:
                location = loc_m.group(1).strip().rstrip('.,:;')

            local_required = False
            local_keywords = ["local candidates", "locals only", "local only", "must be local",
                              "onsite only", "on-site only", "no relocation", "local to",
                              "must reside", "must live in", "within commuting"]
            for kw in local_keywords:
                if kw in jd_lower:
                    local_required = True
                    break

            position = "Not specified"
            role_patterns = [
                r'^(?:job\s+title|position\s+title|role\s+title)\s*[:\-–]\s*(.{3,80})$',
                r'^(?:title|position|role)\s*:\s*(.{3,80})$',
                r'^(?:job|opening|vacancy)\s*:\s*(.{3,80})$',
                r'(?:hiring\s+(?:for|a)|looking\s+for\s+(?:a|an))\s+([A-Z][A-Za-z /&\-,]+)',
            ]
            for pat in role_patterns:
                role_m = re.search(pat, jd, re.IGNORECASE | re.MULTILINE)
                if role_m:
                    candidate = role_m.group(1).strip().rstrip('.,:;')
                    if len(candidate) >= 3 and len(candidate) <= 80:
                        position = candidate
                        break
            if position == "Not specified":
                first_line = jd.strip().split('\n')[0].strip() if jd.strip() else ""
                if 5 <= len(first_line) <= 80 and not any(w in first_line.lower() for w in ['hi ', 'hello', 'dear ', 'please', 'hope ', 'i am']):
                    position = first_line.rstrip('.,:;')

            recruiter_name = None
            name_m = re.search(r'(?:recruiter|hiring manager|contact|regards|thanks|best|sincerely)[,:\s]*\n?\s*([A-Z][a-z]+ [A-Z][a-z]+)', jd)
            if name_m:
                recruiter_name = name_m.group(1).strip()

            results.append({
                "id": rec["id"],
                "company_name": rec.get("company_name", "Unknown"),
                "position": position,
                "emails": list(emails_found),
                "recruiter_name": recruiter_name,
                "location": location,
                "local_required": local_required,
                "user_address": rec.get("user_address") or "",
                "status": rec.get("status", "Scanned"),
                "score": rec.get("score", 0),
                "match_percentage": rec.get("match_percentage"),
                "source": rec.get("source", "dashboard"),
                "created_at": rec.get("created_at"),
                "jd_preview": jd[:200] if jd else "",
            })
        return {"results": results, "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


class AddressUpdate(BaseModel):
    address: str

@app.patch("/api/history/{record_id}/address")
@limiter.limit("30/minute")
async def patch_user_address(request: Request, record_id: int, body: AddressUpdate):
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")
        if len(body.address) > 500:
            raise HTTPException(status_code=400, detail="Address too long")
        update_user_address(record_id, body.address.strip())
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update address error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update address")

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
    attach_resume: bool = False
    attach_cover_letter: bool = False
    attach_dl: bool = False
    attach_gc: bool = False

@app.post("/api/gmail/save-draft")
@limiter.limit("10/minute")
async def gmail_save_draft(request: Request, draft: GmailDraftRequest):
    """Save email as a draft in Gmail with selected attachments."""
    try:
        has_selections = draft.attach_resume or draft.attach_cover_letter or draft.attach_dl or draft.attach_gc
        attachment_list = []

        if has_selections:
            if draft.record_id and (draft.attach_resume or draft.attach_cover_letter):
                record = get_resume_by_id(draft.record_id)
                if record and record.get('file_path') and os.path.exists(record['file_path']):
                    company_dir = os.path.dirname(record['file_path'])
                    if draft.attach_resume:
                        attachment_list.append({
                            "path": record['file_path'],
                            "display_name": "Teja_Mahesh_Neerukonda_Resume.docx"
                        })
                    if draft.attach_cover_letter:
                        cl_files = [f for f in os.listdir(company_dir)
                                     if f.endswith(".docx") and ("cover" in f.lower() or f.startswith("cover_letter_"))
                                     and f != os.path.basename(record['file_path'])]
                        if cl_files:
                            attachment_list.append({
                                "path": os.path.join(company_dir, cl_files[0]),
                                "display_name": "Teja_Mahesh_Neerukonda_Cover_Letter.docx"
                            })

            doc_map = {"dl": draft.attach_dl, "gc": draft.attach_gc}
            display_names = {"dl": "Drivers_License", "gc": "Green_Card"}
            for doc_type, should_attach in doc_map.items():
                if should_attach:
                    for f in os.listdir(DOCUMENTS_DIR):
                        if f.startswith(f"{doc_type}."):
                            ext = os.path.splitext(f)[1]
                            attachment_list.append({
                                "path": os.path.join(DOCUMENTS_DIR, f),
                                "display_name": f"{display_names[doc_type]}{ext}"
                            })
                            break

        if has_selections:
            result = gmail_service.save_draft(
                to_emails=draft.to_emails,
                subject=draft.subject,
                body=draft.body,
                attachments=attachment_list,
            )
        else:
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

# ─── Gmail Inbox (for follow-up) ───

@app.get("/api/gmail/inbox")
@limiter.limit("60/minute")
async def gmail_inbox(request: Request, q: str = ""):
    """Search Gmail inbox for messages matching a query."""
    try:
        messages = gmail_service.search_inbox(q or "in:inbox", max_results=15)
        return {"messages": messages}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Gmail inbox error: {e}")
        raise HTTPException(status_code=500, detail="Failed to search inbox")

@app.get("/api/gmail/message/{message_id}")
@limiter.limit("20/minute")
async def gmail_message(request: Request, message_id: str):
    """Get full body of a Gmail message."""
    try:
        msg = gmail_service.get_message_body(message_id)
        return msg
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Gmail message read error: {e}")
        raise HTTPException(status_code=500, detail="Failed to read message")

# ─── Personal Documents (DL, GC, etc.) ───

DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

ALLOWED_DOC_TYPES = {"dl", "gc"}

@app.post("/api/documents/upload")
@limiter.limit("10/minute")
async def upload_document(request: Request, doc_type: str = Form(...), file: UploadFile = File(...)):
    """Upload a personal document (DL or GC)."""
    doc_type = doc_type.lower()
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {', '.join(ALLOWED_DOC_TYPES)}")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, DOC, PNG, or JPG.")

    save_name = f"{doc_type}{ext}"
    for existing in os.listdir(DOCUMENTS_DIR):
        if existing.startswith(f"{doc_type}."):
            os.remove(os.path.join(DOCUMENTS_DIR, existing))

    save_path = os.path.join(DOCUMENTS_DIR, save_name)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    return {"status": "uploaded", "doc_type": doc_type, "filename": save_name}


@app.get("/api/documents")
async def list_documents(request: Request):
    """List uploaded personal documents."""
    docs = {}
    for f in os.listdir(DOCUMENTS_DIR):
        name = os.path.splitext(f)[0].lower()
        if name in ALLOWED_DOC_TYPES:
            docs[name] = {"filename": f, "path": os.path.join(DOCUMENTS_DIR, f)}
    return {"documents": docs}


@app.delete("/api/documents/{doc_type}")
async def delete_document(request: Request, doc_type: str):
    """Delete a personal document."""
    doc_type = doc_type.lower()
    for f in os.listdir(DOCUMENTS_DIR):
        if f.startswith(f"{doc_type}."):
            os.remove(os.path.join(DOCUMENTS_DIR, f))
            return {"status": "deleted", "doc_type": doc_type}
    raise HTTPException(status_code=404, detail="Document not found")

# ─── Follow-Up Mail ───

class FollowUpRequest(BaseModel):
    received_email: str

@app.post("/api/history/{record_id}/follow-up")
@limiter.limit("5/minute")
async def api_generate_follow_up(request: Request, record_id: int, body: FollowUpRequest):
    """Generate a follow-up reply based on a received email."""
    try:
        if record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid record ID")

        record = get_resume_by_id(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        file_path = record.get('file_path')
        resume_text = ""
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                resume_text = extract_text_from_docx(f.read())

        jd_text = record.get('jd_text', '')
        if not jd_text:
            raise HTTPException(status_code=400, detail="No job description found for this record")

        # Read existing mail draft if available
        original_mail_body = ""
        company_dir = os.path.dirname(file_path) if file_path else ""
        if company_dir and os.path.isdir(company_dir):
            draft_files = [f for f in os.listdir(company_dir) if f.startswith("mail_draft_") and f.endswith(".txt")]
            if draft_files:
                with open(os.path.join(company_dir, draft_files[0]), "r", encoding="utf-8") as f:
                    original_mail_body = f.read()

        profile_text = ""
        profile_path = os.path.join(DATA_DIR, "profile.txt")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_text = f.read().strip()

        to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body.received_email)))

        is_w2 = detect_w2_fulltime(body.received_email)

        conversation_history = ""
        if is_w2 and to_emails:
            try:
                sender_email = to_emails[0]
                convos = gmail_service.get_conversation_with_sender(sender_email, max_results=20)
                if convos:
                    parts = []
                    for msg in convos:
                        parts.append(
                            f"--- Email ({msg['date']}) ---\n"
                            f"From: {msg['from']}\n"
                            f"To: {msg['to']}\n"
                            f"Subject: {msg['subject']}\n\n"
                            f"{msg['body']}"
                        )
                    conversation_history = "\n\n".join(parts)
            except Exception as e:
                logger.warning(f"Could not fetch conversation history: {e}")

        result = generate_follow_up(
            resume_text=resume_text,
            jd_text=jd_text,
            company_name=record['company_name'],
            received_email=body.received_email,
            original_mail_body=original_mail_body,
            profile_text=profile_text,
            conversation_history=conversation_history,
            is_w2_fulltime=is_w2,
        )

        response_data = {
            "to_emails": to_emails,
            "subject": result.get('subject', ''),
            "body": result.get('body', ''),
            "w2_detected": is_w2,
        }

        if is_w2:
            try:
                draft_result = gmail_service.save_draft(
                    to_emails=to_emails,
                    subject=result.get('subject', ''),
                    body=result.get('body', ''),
                )
                response_data["auto_draft_saved"] = True
                response_data["draft_id"] = draft_result.get("draft_id", "")
            except Exception as e:
                logger.warning(f"Auto-save draft failed for W2 reply: {e}")
                response_data["auto_draft_saved"] = False

        return response_data
    except RuntimeError as e:
        logger.warning(f"AI provider error: {e}")
        raise HTTPException(status_code=503, detail="The AI provider is unavailable. Please try again.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Follow-up generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate follow-up")


@app.post("/api/follow-up/standalone")
@limiter.limit("5/minute")
async def api_standalone_follow_up(request: Request, body: FollowUpRequest):
    """Generate a follow-up reply without a company record — for direct/personal emails."""
    try:
        profile_text = ""
        profile_path = os.path.join(DATA_DIR, "profile.txt")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_text = f.read().strip()

        to_emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body.received_email)))

        is_w2 = detect_w2_fulltime(body.received_email)

        conversation_history = ""
        if to_emails:
            try:
                sender_email = to_emails[0]
                convos = gmail_service.get_conversation_with_sender(sender_email, max_results=20)
                if convos:
                    parts = []
                    for msg in convos:
                        parts.append(
                            f"--- Email ({msg['date']}) ---\n"
                            f"From: {msg['from']}\n"
                            f"To: {msg['to']}\n"
                            f"Subject: {msg['subject']}\n\n"
                            f"{msg['body']}"
                        )
                    conversation_history = "\n\n".join(parts)
            except Exception as e:
                logger.warning(f"Could not fetch conversation history: {e}")

        result = generate_follow_up(
            received_email=body.received_email,
            profile_text=profile_text,
            conversation_history=conversation_history,
            is_w2_fulltime=is_w2,
        )

        response_data = {
            "to_emails": to_emails,
            "subject": result.get('subject', ''),
            "body": result.get('body', ''),
            "w2_detected": is_w2,
        }

        if is_w2:
            try:
                draft_result = gmail_service.save_draft(
                    to_emails=to_emails,
                    subject=result.get('subject', ''),
                    body=result.get('body', ''),
                )
                response_data["auto_draft_saved"] = True
                response_data["draft_id"] = draft_result.get("draft_id", "")
            except Exception as e:
                logger.warning(f"Auto-save draft failed for standalone W2 reply: {e}")
                response_data["auto_draft_saved"] = False

        return response_data
    except RuntimeError as e:
        logger.warning(f"AI provider error: {e}")
        raise HTTPException(status_code=503, detail="The AI provider is unavailable. Please try again.")
    except Exception as e:
        logger.error(f"Standalone follow-up error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate follow-up")

# ─── Job Matcher ───

@app.post("/api/job-matcher/fetch-url")
@limiter.limit("20/minute")
async def fetch_jd_from_url(request: Request, url: str = Form(...)):
    """Fetch job description text from a URL."""
    try:
        if not url or not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid URL")
        text = _scrape_jd_from_url(url)
        return {"jd_text": text, "url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"URL fetch error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

@app.post("/api/job-matcher/analyze")
@limiter.limit("30/minute")
async def analyze_job(request: Request, jd_text: str = Form(...), source_url: Optional[str] = Form(None)):
    """
    Analyze job description against user profile.
    Saves all results (pass/reject) to history DB and CSV.
    """
    try:
        if not jd_text or len(jd_text) < 50:
            raise HTTPException(status_code=400, detail="Job description too short (minimum 50 characters)")
        if len(jd_text) > 50000:
            raise HTTPException(status_code=400, detail="Job description too long (maximum 50000 characters)")

        # Duplicate JD check
        all_history = get_all_resumes(limit=1000)
        for item in all_history:
            if not item.get('jd_text'):
                continue
            ratio = difflib.SequenceMatcher(None, jd_text, item['jd_text']).ratio()
            if ratio >= 0.95:
                prev = item.get('company_name', 'Unknown')
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate JD — already scanned for {prev}. Check your Production Log."
                )

        company_name = _extract_company_name(jd_text)

        # Rule 1: Check lead role (HARD REJECT)
        lead_reason = _check_lead_role(jd_text)
        if lead_reason:
            reason = f"Rejected: {lead_reason}"
            record_id = save_job_matcher_record(company_name, jd_text, 0, False, reason, source_url)
            append_job_matcher_to_csv(company_name, jd_text, 0, "Rejected", reason, source_url or "")
            return {"id": record_id, "error": reason, "can_apply": False, "hard_reject": True, "company_name": company_name}

        # Rule 2: Check visa eligibility (HARD REJECT if excludes GC)
        gc_reason = _check_visa_eligibility(jd_text)
        if gc_reason:
            record_id = save_job_matcher_record(company_name, jd_text, 0, False, gc_reason, source_url)
            append_job_matcher_to_csv(company_name, jd_text, 0, "Rejected", gc_reason, source_url or "")
            return {"id": record_id, "error": gc_reason, "can_apply": False, "hard_reject": True, "company_name": company_name}

        # Rule 3: Check foreign language requirement (HARD REJECT)
        lang_reason = _check_foreign_language(jd_text)
        if lang_reason:
            reason = f"Rejected: {lang_reason}"
            record_id = save_job_matcher_record(company_name, jd_text, 0, False, reason, source_url)
            append_job_matcher_to_csv(company_name, jd_text, 0, "Rejected", reason, source_url or "")
            return {"id": record_id, "error": reason, "can_apply": False, "hard_reject": True, "company_name": company_name}

        # Rule 4: Check employment type (HARD REJECT for W2 only)
        employment_type, emp_warning = _check_employment_type(jd_text)
        if emp_warning:
            reason = f"Rejected: {emp_warning}"
            record_id = save_job_matcher_record(company_name, jd_text, 0, False, reason, source_url)
            append_job_matcher_to_csv(company_name, jd_text, 0, "Rejected", reason, source_url or "")
            return {"id": record_id, "error": reason, "can_apply": False, "hard_reject": True, "company_name": company_name}

        # Extract experience
        years_required = _extract_experience_years(jd_text)

        # Soft warnings
        warnings = []
        if years_required > 10:
            experience_match = max(0, 100 - (years_required - 10) * 5)
            warnings.append(f"Job requires {years_required}+ years, you have ~8-10 years ({experience_match}% experience match)")
        if employment_type == 'unknown':
            warnings.append("Employment type unclear — verify this is C2C or C2H before applying")

        # Extract keywords and metadata
        extracted_keywords = extract_job_keywords(jd_text)
        metadata = analyze_job_metadata(jd_text, extracted_keywords)

        # Calculate overall match
        match_score = calculate_match_score(years_required, extracted_keywords, employment_type)

        # Save to DB and CSV
        scan_data = json.dumps({
            "match_percentage": match_score,
            "warnings": warnings,
            "job_category": metadata.get("primary_role", ""),
            "sub_categories": metadata.get("sub_categories", []),
            "extracted_keywords": extracted_keywords,
        })
        record_id = save_job_matcher_record(company_name, jd_text, match_score, True, None, source_url, scan_data)
        append_job_matcher_to_csv(company_name, jd_text, match_score, "Matched", "", source_url or "")

        return {
            "id": record_id,
            "can_apply": True,
            "hard_reject": False,
            "match_percentage": match_score,
            "warnings": warnings,
            "company_name": company_name,
            "job_category": {
                "name": metadata.get("primary_role", "DevOps Engineer"),
                "sub_categories": metadata.get("sub_categories", []),
                "match_confidence": metadata.get("match_confidence", 0),
            },
            "employment_type": metadata.get("employment_type", employment_type),
            "years_required": years_required,
            "experience_years": f"{years_required}+ years" if years_required > 0 else "Not specified",
            "extracted_keywords": extracted_keywords,
            "location": metadata.get("location", "Not specified"),
            "salary_range": metadata.get("salary_range", "Not specified"),
            "visa_requirements": metadata.get("visa_requirements", "Not specified"),
            "clearance_level": metadata.get("clearance_level", "Not specified"),
            "source_url": source_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job matcher analyze error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyze job description")


@app.post("/api/job-matcher/apply")
@limiter.limit("10/minute")
async def apply_to_job(request: Request, jd_text: str = Form(...), resume: Optional[UploadFile] = File(None), selected_resume: Optional[str] = Form(None)):
    """
    Apply to a job by tailoring resume.
    Reuses existing scan logic with job matcher context.
    """
    try:
        result = await scan_resume(request, jd_text, resume, selected_resume, ai_notes="From Job Matcher")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job matcher apply error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to apply to job")

# ─── Telegram Integration ───

def _telegram_process_jd(jd_text: str, chat_id: int):
    """Background task: process a JD received via Telegram and reply with the result."""
    from services.telegram_service import send_message_sync

    try:
        resumes = []
        if os.path.exists("original"):
            for f in os.listdir("original"):
                if f.endswith(".docx"):
                    path = os.path.join("original", f)
                    resumes.append((path, os.path.getmtime(path)))
        if not resumes:
            send_message_sync(chat_id, "No resume found. Please upload a resume via the web dashboard first.")
            return

        resumes.sort(key=lambda x: x[1], reverse=True)
        resume_path = resumes[0][0]
        resume_filename = os.path.basename(resume_path)

        with open(resume_path, "rb") as f:
            file_bytes = f.read()

        if len(jd_text) < 50:
            send_message_sync(chat_id, "JD too short (minimum 50 characters). Please send the full job description.")
            return

        years = _extract_experience_years(jd_text)
        if years > 10:
            send_message_sync(chat_id, f"Skipped — requires {years}+ years experience (max: 10)")
            return

        gc_reason = _check_visa_eligibility(jd_text)
        if gc_reason:
            send_message_sync(chat_id, f"Skipped — {gc_reason}")
            return

        lang_reason = _check_foreign_language(jd_text)
        if lang_reason:
            send_message_sync(chat_id, f"Skipped — {lang_reason}")
            return

        lead_reason = _check_lead_role(jd_text)
        if lead_reason:
            send_message_sync(chat_id, f"Skipped — {lead_reason}")
            return

        result = _process_single_jd(jd_text, file_bytes, resume_path)

        if result.get("skipped"):
            send_message_sync(chat_id, f"Skipped — {result.get('reason', 'Unknown reason')}")
            return

        company = result.get("company_name", "Unknown")
        score = result.get("score", 0)
        after_score = result.get("after_score", score)
        tailored = result.get("tailored", False)
        missing = result.get("missing_keywords", [])

        lines = [f"Processed JD for {company}!"]
        if tailored and after_score != score:
            lines.append(f"Score: {score}% -> {after_score}% (+{after_score - score})")
        else:
            lines.append(f"Match Score: {after_score}%")

        if tailored:
            lines.append("Resume has been tailored")
        else:
            lines.append("Resume already strong — no changes needed")

        if missing:
            lines.append(f"Missing keywords: {', '.join(missing[:8])}")

        lines.append(f"\nUsing resume: {resume_filename}")
        lines.append("Files saved — check your dashboard for downloads.")

        send_message_sync(chat_id, "\n".join(lines))
        logger.info(f"Telegram JD processed: {company} (score={after_score}%) chat={chat_id}")

    except Exception as e:
        logger.error(f"Telegram processing error: {e}", exc_info=True)
        try:
            send_message_sync(chat_id, f"Processing failed: {str(e)[:300]}")
        except Exception:
            logger.error("Failed to send Telegram error reply")


_telegram_polling = False

async def _telegram_poll_loop():
    """Long-polling loop that listens for Telegram messages."""
    global _telegram_polling
    from services import telegram_service

    if not telegram_service.is_configured():
        logger.info("Telegram bot not configured — polling disabled")
        return

    await asyncio.sleep(2)

    try:
        bot_info = await telegram_service.get_me()
        logger.info(f"Telegram bot connected: @{bot_info.get('username', '?')}")
    except Exception as e:
        logger.error(f"Telegram bot connection failed: {e}")
        return

    try:
        import httpx as _hx
        async with _hx.AsyncClient(timeout=10) as client:
            await client.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/deleteWebhook")
    except Exception:
        pass

    _telegram_polling = True
    offset = 0

    while _telegram_polling:
        try:
            updates = await telegram_service.get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")

                if not text or not chat_id:
                    continue

                if text.startswith("/start"):
                    await telegram_service.send_message(chat_id, "Welcome to Job Tailored Resume Bot!\n\nSend me a Job Description and I'll:\n- Analyze it against your resume\n- Tailor your resume automatically\n- Save everything to your dashboard\n\nJust paste a JD and hit send.")
                    continue

                if text.startswith("/status"):
                    resumes = [f for f in os.listdir("original") if f.endswith(".docx")] if os.path.exists("original") else []
                    await telegram_service.send_message(chat_id, f"Bot is running.\nResumes available: {len(resumes)}")
                    continue

                if text.startswith("/"):
                    await telegram_service.send_message(chat_id, "Commands:\n/start - Welcome message\n/status - Check bot status\n\nOr just send a Job Description to process it.")
                    continue

                logger.info(f"Telegram message from chat {chat_id}: {len(text)} chars")
                await telegram_service.send_message(chat_id, "Processing your JD... You'll get a reply shortly.")

                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, _telegram_process_jd, text, chat_id)

        except asyncio.CancelledError:
            _telegram_polling = False
            break
        except Exception as e:
            if str(e):
                logger.error(f"Telegram polling error: {e}")
            await asyncio.sleep(5)


@app.on_event("startup")
async def start_telegram_polling():
    from services import telegram_service
    if telegram_service.is_configured():
        asyncio.create_task(_telegram_poll_loop())


@app.get("/api/telegram/status")
async def telegram_status():
    """Check if Telegram bot is configured and running."""
    from services import telegram_service
    result = {"configured": telegram_service.is_configured(), "polling": _telegram_polling}
    if telegram_service.is_configured():
        try:
            bot_info = await telegram_service.get_me()
            result["bot_username"] = bot_info.get("username", "")
        except Exception:
            result["bot_username"] = ""
    return result


if __name__ == "__main__":
    # Don't use reload in production
    reload = "--reload" in sys.argv or os.getenv("ENVIRONMENT") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload)

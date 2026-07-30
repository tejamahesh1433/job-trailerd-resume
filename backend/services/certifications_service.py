"""Keeps the Certifications page (data/certifications.json) in sync with what the
candidate's actual resume files list under their CERTIFICATIONS section. For each
certification found, runs a free DuckDuckGo search + page scrape (same approach
main.py already uses for job-contact discovery) and feeds the result to a cheap AI
model to fill in issuer/category/description/validity/exam code — so the page shows
real, useful context instead of just a bare list of names."""
import os
import re
import json
from services.docx_service import extract_text_from_docx
from services.usage_tracker import log_api_call
from services.model_config import GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL

# Cheapest tier from each provider — tried in this order so the feature isn't a
# single point of failure hanging entirely off one vendor's key/quota/uptime.
OPENAI_MODEL = "gpt-4o-mini"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

DATA_DIR = os.getenv("DATA_DIR", "data")
CERTIFICATIONS_PATH = os.path.join(DATA_DIR, "certifications.json")

# Base resume files — the source of truth for what actually shows up on this page.
RESUME_DIR = os.getenv("RESUME_DIR", "original")

CATEGORIES = [
    "Cloud Platforms", "Containers & Orchestration", "Infrastructure as Code",
    "CI/CD & DevOps Tools", "Security & DevSecOps", "Other",
]

# Resume section headings, used to know where the CERTIFICATIONS block ends.
_SECTION_HEADINGS = {
    "professional summary", "technical proficiency", "technical skills", "core competencies",
    "certifications", "professional experience", "education", "skills", "projects",
    "work experience", "summary", "key skills", "areas of expertise",
}


def _load() -> list:
    if not os.path.exists(CERTIFICATIONS_PATH):
        return []
    with open(CERTIFICATIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(items: list) -> None:
    os.makedirs(os.path.dirname(CERTIFICATIONS_PATH), exist_ok=True)
    with open(CERTIFICATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
        f.write("\n")


def _normalize(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', name.lower())


def get_certifications() -> list:
    cached = _load()
    if cached:
        return cached
    return build_certifications()


# ---------------------------------------------------------------------------
# Step 1: pull certification names straight out of the candidate's resume files
# ---------------------------------------------------------------------------

def _extract_section_lines(lines: list, heading: str) -> list:
    heading = heading.lower()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == heading:
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if line.strip().lower() in _SECTION_HEADINGS:
            break
        out.append(line.strip())
    return out


def _parse_cert_line(line: str):
    line = line.strip().lstrip("•-–*").strip()
    if not line:
        return None
    in_progress = bool(re.search(r'\(in\s*progress\)', line, re.IGNORECASE))
    name = re.sub(r'\s*\(in\s*progress\)\s*', '', line, flags=re.IGNORECASE).strip()
    if not name or len(name) > 120:
        return None
    return name, ("In Progress" if in_progress else "Active")


def _extract_cert_names_from_resumes() -> list:
    """Reads every .docx under RESUME_DIR, finds each one's CERTIFICATIONS section,
    and returns a deduped [(name, status), ...] list. Nothing here is invented —
    it all comes straight from the candidate's real resume files."""
    if not os.path.isdir(RESUME_DIR):
        return []

    found = {}
    for fname in sorted(os.listdir(RESUME_DIR)):
        if not fname.lower().endswith(".docx"):
            continue
        path = os.path.join(RESUME_DIR, fname)
        try:
            with open(path, "rb") as f:
                text = extract_text_from_docx(f.read())
        except Exception as e:
            print(f"certifications_service: failed to read {path} — {e}")
            continue

        lines = text.split("\n")
        for line in _extract_section_lines(lines, "certifications"):
            parsed = _parse_cert_line(line)
            if not parsed:
                continue
            name, status = parsed
            norm = _normalize(name)
            # A later "Active" sighting upgrades an older "In Progress" one (resume
            # was updated after finishing the cert); never downgrade the reverse.
            if norm not in found or (found[norm][1] == "In Progress" and status == "Active"):
                found[norm] = (name, status)

    return list(found.values())


# ---------------------------------------------------------------------------
# Step 2: live internet search for context on each certification
# ---------------------------------------------------------------------------

def _search_certification_info(name: str) -> tuple[str, str]:
    """Free DuckDuckGo text search + page scrape for the certification's official
    page. Returns (official_url, scraped_page_text) — either may be empty if the
    search/fetch fails, which callers must handle gracefully."""
    from duckduckgo_search import DDGS
    import requests
    from bs4 import BeautifulSoup

    url = ""
    snippet = ""
    try:
        results = DDGS().text(f"{name} certification official exam overview", max_results=3)
    except Exception as e:
        print(f"certifications_service: DDG search failed for '{name}' — {e}")
        return url, snippet

    for r in results:
        candidate_url = r.get("href", "")
        if not candidate_url:
            continue
        url = url or candidate_url
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(candidate_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                snippet = soup.get_text(separator=" ", strip=True)[:2500]
                break
        except Exception:
            continue

    return url, snippet


# ---------------------------------------------------------------------------
# Step 3: AI enrichment — turn the search result into a structured entry
# ---------------------------------------------------------------------------

def _build_prompt(name: str, status: str, snippet: str) -> str:
    return f"""You are filling in one entry of a "Certifications" reference page for a Senior
DevOps/Cloud Engineer's resume tool.

Certification name (from the candidate's actual resume): "{name}"
Current status on the resume: {status}

Text scraped from a web page about this certification (may be empty or noisy — ignore
navigation/cookie-banner junk, use only what's factually useful):
---
{snippet[:2000]}
---

Return ONLY valid JSON (no markdown fences, no other text) in this exact shape:
{{
  "issuer": "organization that issues it, e.g. 'Amazon Web Services (AWS)'",
  "category": "exactly one of {json.dumps(CATEGORIES)}",
  "exam_code": "official exam code if one exists (e.g. 'SAA-C03', 'AZ-400'), else empty string",
  "description": "one or two plain sentences on what this certification validates",
  "skills_validated": ["3 to 5 short skill/topic phrases this exam covers"],
  "validity": "how long it stays valid before renewal, e.g. 'Valid 3 years from issue date'"
}}
If the scraped text doesn't confirm a detail, rely on your general knowledge of this specific,
well-known, real industry certification rather than guessing wildly.
"""


def _extract_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def _call_openai(prompt: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    usage = response.usage
    if usage:
        log_api_call(OPENAI_MODEL, "certifications_enrich",
                     input_tokens=usage.prompt_tokens or 0,
                     output_tokens=usage.completion_tokens or 0)
    else:
        log_api_call(OPENAI_MODEL, "certifications_enrich", input_tokens=1200, output_tokens=300)
    return _extract_json_object(response.choices[0].message.content)


def _call_claude(prompt: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    if usage:
        log_api_call(CLAUDE_MODEL, "certifications_enrich",
                     input_tokens=usage.input_tokens or 0,
                     output_tokens=usage.output_tokens or 0)
    else:
        log_api_call(CLAUDE_MODEL, "certifications_enrich", input_tokens=1200, output_tokens=300)
    return _extract_json_object(response.content[0].text)


def _call_gemini(prompt: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)

    last_error = None
    for model_name in (GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
            )
            usage = response.usage_metadata
            if usage:
                log_api_call(model_name, "certifications_enrich",
                             input_tokens=usage.prompt_token_count or 0,
                             output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
            else:
                log_api_call(model_name, "certifications_enrich", input_tokens=1200, output_tokens=300)
            return _extract_json_object(response.text)
        except Exception as e:
            last_error = e
            continue
    raise last_error or RuntimeError("Gemini unavailable")


def _ai_enrich_one(name: str, status: str, snippet: str) -> dict:
    """Tries the cheapest OpenAI and Claude models first, only falling back to
    Gemini if both are unavailable — so this feature isn't a single point of
    failure hanging off one vendor's key/quota."""
    prompt = _build_prompt(name, status, snippet)
    for call in (_call_openai, _call_claude, _call_gemini):
        try:
            result = call(prompt)
            if isinstance(result, dict) and result:
                return result
        except Exception as e:
            print(f"certifications_service: {call.__name__} failed — {e}")
            continue
    return {}


def _build_entry(name: str, status: str, url: str, ai_data: dict) -> dict:
    category = ai_data.get("category") if ai_data.get("category") in CATEGORIES else "Cloud Platforms"
    skills = ai_data.get("skills_validated")
    if not isinstance(skills, list):
        skills = []
    skills = [s for s in (str(x).strip() for x in skills) if s][:5]

    return {
        "name": name,
        "status": status,
        "issuer": (ai_data.get("issuer") or "").strip() or "Unknown issuer",
        "category": category,
        "exam_code": (ai_data.get("exam_code") or "").strip(),
        "description": (ai_data.get("description") or "").strip()
            or "No description available yet — try refreshing once an AI/API key is configured.",
        "skills_validated": skills,
        "validity": (ai_data.get("validity") or "").strip() or "Unknown",
        "official_url": url,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_certifications(force_refresh: bool = False) -> list:
    """Scans the resume files for certification names, then enriches each one via
    a live internet search + AI classification, caching the result in
    data/certifications.json so normal page loads are instant and don't hit the
    network every time. Pass force_refresh=True to re-search/re-enrich everything."""
    cached = _load()
    cached_by_norm = {_normalize(c["name"]): c for c in cached}

    resume_certs = _extract_cert_names_from_resumes()
    seen_norm = set()
    result = []
    changed = force_refresh

    for name, status in resume_certs:
        norm = _normalize(name)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)

        existing = cached_by_norm.get(norm)
        if existing and not force_refresh:
            if existing.get("status") != status:
                existing = {**existing, "status": status}
                changed = True
            result.append(existing)
            continue

        url, snippet = _search_certification_info(name)
        ai_data = _ai_enrich_one(name, status, snippet)
        result.append(_build_entry(name, status, url, ai_data))
        changed = True

    if changed:
        _save(result)
    return result

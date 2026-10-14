"""Measured, deterministic resume scoring — separate from the tailoring AI pass.

score_resume()         — Gemini call using the recruiter-scorer prompt.
detect_anachronisms()  — Pure Python date × tool check; no AI.
load_candidate_truth() — Reads backend/data/candidate_truth.md.
"""
import json
import logging
import os
import re

from google import genai
from google.genai import types

from services.model_config import (
    GEMINI_FAST_MODEL,
    GEMINI_PRO_FALLBACK_MODEL,
    GEMINI_QUALITY_MODEL,
)
from services.usage_tracker import log_api_call

logger = logging.getLogger("main")

# Expose for testability — monkeypatch _TRUTH_PATH and clear _truth_cache in tests
_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "candidate_truth.md")
_truth_cache: set | None = None
_truth_mtime: float | None = None

_TOOL_DATES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tool_release_dates.json")


def _load_tool_dates_from_json(path: str) -> tuple[dict[str, tuple[int, int]], dict[str, str]]:
    """Load TOOL_RELEASE_DATES and _TOOL_ALIASES from JSON. Falls back to ({}, {}) on any error
    so the service starts even when the file is missing or malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tools: dict[str, tuple[int, int]] = {}
        for name, ym_str in data.get("tools", {}).items():
            year_s, month_s = ym_str.split("-", 1)
            tools[name.lower()] = (int(year_s), int(month_s))
        aliases: dict[str, str] = {k.lower(): v.lower() for k, v in data.get("aliases", {}).items()}
        return tools, aliases
    except Exception as _e:  # noqa: BLE001
        import warnings
        warnings.warn(f"Could not load tool_release_dates.json ({path}): {_e}; anachronism detection disabled")
        return {}, {}


TOOL_RELEASE_DATES, _TOOL_ALIASES = _load_tool_dates_from_json(_TOOL_DATES_PATH)

# Keep for backwards compatibility (tests may reference it)
TOOL_RELEASE_YEAR = {tool: ym[0] for tool, ym in TOOL_RELEASE_DATES.items()}

_MONTH_ABBREVS = (
    "Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May",
    "Jun(?:e)?", "Jul(?:y)?", "Aug(?:ust)?", "Sep(?:tember)?",
    "Oct(?:ober)?", "Nov(?:ember)?", "Dec(?:ember)?"
)
_MONTH_PAT = "(?:" + "|".join(_MONTH_ABBREVS) + ")"

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Matches "Apr 2019 – Mar 2024" or "Feb 2014 – June 2016" or "Apr 2024 – Present"
# Named groups: sm/sy = start month/year; em/ey = end month/year; end = full end token
_DATE_RANGE_RE = re.compile(
    rf"(?P<sm>{_MONTH_PAT})\s+(?P<sy>\d{{4}})\s*[–—\-]+\s*"
    rf"(?P<end>Present|(?P<em>{_MONTH_PAT})\s+(?P<ey>\d{{4}}))",
    re.IGNORECASE,
)

_NETWORK_ERROR_SIGNATURES = (
    "Errno -3", "Try again", "getaddrinfo", "Name or service not known",
    "Temporary failure in name resolution", "Failed to establish a new connection",
    "Connection refused", "Network is unreachable", "Errno -2",
)


def _is_network_error(exc: Exception) -> bool:
    text = str(exc)
    return any(sig in text for sig in _NETWORK_ERROR_SIGNATURES)


def detect_anachronisms(resume_text: str) -> list[dict]:
    """Split resume into employer blocks by date-range header lines, then flag any
    tool from TOOL_RELEASE_DATES whose (year, month) release is strictly after the
    block's end date. Uses datetime.now() for 'Present'. Deduplicates per
    (role, canonical_tool) using _TOOL_ALIASES so 'eks' and 'amazon eks' in the
    same block generate exactly one flag."""
    from datetime import datetime
    now = datetime.now()
    _current: tuple[int, int] = (now.year, now.month)

    lines = resume_text.splitlines()
    blocks: list[tuple[str, tuple[int, int], tuple[int, int], str]] = []

    current_start: int | None = None
    current_role = ""
    current_start_ym: tuple[int, int] = (0, 1)
    current_end_ym: tuple[int, int] = (0, 1)

    for i, line in enumerate(lines):
        m = _DATE_RANGE_RE.search(line)
        if m:
            if current_start is not None:
                blocks.append((current_role, current_start_ym, current_end_ym,
                                "\n".join(lines[current_start:i])))
            current_start = i
            start_year = int(m.group("sy"))
            start_month = _MONTH_MAP.get(m.group("sm").lower()[:3], 1)
            current_start_ym = (start_year, start_month)

            end_str = m.group("end")
            if end_str.lower().startswith("present"):
                current_end_ym = _current
            else:
                end_year = int(m.group("ey"))
                end_month = _MONTH_MAP.get(m.group("em").lower()[:3], 1)
                current_end_ym = (end_year, end_month)

            role_part = line.split("|")[0].strip() if "|" in line else line[:60].strip()
            current_role = _DATE_RANGE_RE.sub("", role_part).strip(" |–—-")

    if current_start is not None:
        blocks.append((current_role, current_start_ym, current_end_ym,
                       "\n".join(lines[current_start:])))

    flags: list[dict] = []
    for role, _start_ym, end_ym, block_text in blocks:
        seen: set[tuple[str, str]] = set()  # (role, canonical) already flagged
        for tool, release_ym in TOOL_RELEASE_DATES.items():
            canonical = _TOOL_ALIASES.get(tool, tool)
            key = (role, canonical)
            if key in seen:
                continue
            if release_ym > end_ym:  # noqa: SIM102
                if re.search(r"(?i)\b" + re.escape(tool) + r"\b", block_text):
                    seen.add(key)
                    flags.append({
                        "role": role,
                        "tool": canonical,
                        "released": f"{release_ym[0]}-{release_ym[1]:02d}",
                        "role_end": f"{end_ym[0]}-{end_ym[1]:02d}",
                    })
    return flags


def load_candidate_truth() -> set[str]:
    """Read backend/data/candidate_truth.md and return lowercased skill names for
    lines matching '- <Skill>: yes'. Invalidates cache when the file's mtime
    changes. Missing file returns empty set, never raises."""
    global _truth_cache, _truth_mtime

    path = os.path.abspath(_TRUTH_PATH)
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        return set()

    if _truth_cache is not None and _truth_mtime == current_mtime:
        return _truth_cache

    skills: set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                m = re.match(r"^-\s+(.+?):\s+yes\b", stripped, re.IGNORECASE)
                if m:
                    skill_name = m.group(1).strip().split("|")[0].strip()
                    skills.add(skill_name.lower())
    except OSError:
        pass

    _truth_cache = skills
    _truth_mtime = current_mtime
    return skills


def load_unconfirmed_skills() -> set[str]:
    """Return lowercased skill names for lines matching '- <Skill>: ?' in
    candidate_truth.md. Missing file returns empty set, never raises."""
    path = os.path.abspath(_TRUTH_PATH)
    skills: set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                m = re.match(r"^-\s+(.+?):\s+\?", stripped, re.IGNORECASE)
                if m:
                    skill_name = m.group(1).strip().split("|")[0].strip()
                    skills.add(skill_name.lower())
    except OSError:
        pass
    return skills


def score_resume(resume_text: str, jd_text: str) -> dict:
    """Call Gemini with the recruiter-scorer prompt. Also applies deterministic
    anachronism penalties so they can't be omitted by the AI. Returns the full
    scoring dict with guaranteed final_score reflecting the penalty."""
    from services.ai_service import (
        AIProviderNetworkError,  # avoid circular at module level
    )

    anachronisms = detect_anachronisms(resume_text)
    anachronisms_json = json.dumps(anachronisms, indent=2)

    prompt = (
        "You are a senior technical recruiter and hiring manager scoring a resume against a job description.\n"
        "Score the way a real human screener and a technical interviewer would. Do NOT just count keywords.\n"
        "\n"
        "<job_description>\n"
        f"{jd_text}\n"
        "</job_description>\n"
        "<resume>\n"
        f"{resume_text}\n"
        "</resume>\n"
        "<known_anachronisms>\n"
        f"{anachronisms_json}\n"
        "</known_anachronisms>\n"
        "\n"
        "STEP 1 – EXTRACT REQUIREMENTS: list every distinct JD requirement; tier = must_have (weight 3),\n"
        "responsibility (weight 2), preferred (weight 1). Merge duplicates (keep highest tier).\n"
        "\n"
        "STEP 2 – GRADE EVIDENCE per requirement:\n"
        "1.0 STRONG = concrete experience bullet (action + context, ideally a metric) or present in 2+ roles;\n"
        "0.7 MODERATE = one thin/generic experience bullet;\n"
        "0.4 WEAK = only in summary, skills table, or an “Environment:” line;\n"
        "0.0 MISSING. Accept clear equivalents (EKS→Kubernetes; post-incident reviews → partial RCA).\n"
        "Quote the exact resume text used as evidence; if you can't quote it, it's MISSING.\n"
        "\n"
        "STEP 3 – base = sum(weight×evidence)/sum(weight)×100, rounded.\n"
        "\n"
        "STEP 4 – PENALTIES: -5 per must_have with 0.0; -3 per item in known_anachronisms (max -12);\n"
        "-3 title inconsistency (header/summary/latest role conflict, or older role more senior than newer);\n"
        "-3 keyword stuffing (JD phrases in skills with no supporting bullet); -1 per typo (max -3);\n"
        "-10 if years of experience below JD minimum. final_score = max(0, base - penalties).\n"
        "\n"
        "STEP 5 – FIXES: for each requirement below 1.0, quote the existing bullet to rewrite (no new bullets),\n"
        "give suggested text, set only_if_true=true when it would claim something not in the resume, estimate points.\n"
        "\n"
        'Return ONLY JSON:\n'
        '{"final_score":0,"base_score":0,"keyword_match_pct":0,"verdict":"strong_fit|good_fit|stretch|poor_fit",\n'
        ' "requirements":[{"requirement":"","tier":"","weight":0,"evidence_level":0.0,"evidence_quote":"","where":""}],\n'
        ' "penalties":[{"type":"","points":0,"detail":""}],\n'
        ' "top_gaps":[""],\n'
        ' "fixes":[{"requirement":"","rewrite_bullet":"","suggested_text":"","only_if_true":true,"est_points":0}],\n'
        ' "interview_risks":[""]}\n'
        "keyword_match_pct = % of requirements present at any evidence level.\n"
        "Verdict: >=90 strong_fit, 80-89 good_fit, 65-79 stretch, <65 poor_fit. Be strict and consistent.\n"
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    models_to_try = [GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL]
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            usage = response.usage_metadata
            if usage:
                log_api_call(model_name, "score_resume",
                             input_tokens=usage.prompt_token_count or 0,
                             output_tokens=(usage.candidates_token_count or 0) +
                             (usage.thoughts_token_count or 0))
            else:
                log_api_call(model_name, "score_resume", input_tokens=10000, output_tokens=1000)

            result = json.loads(response.text)

            # Deterministic anachronism penalty — ensure it's at least the computed value
            # even if the AI omitted or understated it in its own penalties list
            anachronism_penalty = min(len(anachronisms) * 3, 12)
            if anachronism_penalty > 0:
                ai_anach_penalty = sum(
                    abs(p.get("points", 0))
                    for p in result.get("penalties", [])
                    if "anachronism" in p.get("type", "").lower()
                )
                gap = max(0, anachronism_penalty - ai_anach_penalty)
                result["final_score"] = max(0, result.get("final_score", 0) - gap)

            return result
        except Exception as e:  # noqa: BLE001
            last_error = e
            if _is_network_error(e):
                raise AIProviderNetworkError(f"Network error reaching AI provider: {e}")
            if any(code in str(e) for code in ("503", "UNAVAILABLE", "429", "404", "NOT_FOUND")):
                logger.info(f"{model_name} unavailable for scoring, trying next model...")
                continue
            raise RuntimeError(f"Scoring API error: {e}")

    raise RuntimeError(f"All models unavailable: {last_error}")

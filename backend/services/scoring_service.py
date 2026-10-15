"""Measured, deterministic resume scoring — separate from the tailoring AI pass.



score_resume()         — Gemini call using the recruiter-scorer prompt.

detect_anachronisms()  — Pure Python date × tool check; no AI.

load_candidate_truth() — Reads backend/data/candidate_truth.md.

"""

import hashlib

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

_REQUIREMENTS_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "requirements_cache.json")





def _load_tool_dates_from_json(path: str) -> tuple[dict[str, tuple[int, int]], dict[str, str], dict[str, list[str]]]:

    """Load TOOL_RELEASE_DATES, _TOOL_ALIASES, and _TOOL_MATCH_PHRASES from JSON.

    Falls back to ({}, {}, {}) on any error so the service starts even when the

    file is missing or malformed."""

    try:

        with open(path, encoding="utf-8") as f:

            data = json.load(f)

        tools: dict[str, tuple[int, int]] = {}

        for name, ym_str in data.get("tools", {}).items():

            year_s, month_s = ym_str.split("-", 1)

            tools[name.lower()] = (int(year_s), int(month_s))

        aliases: dict[str, str] = {k.lower(): v.lower() for k, v in data.get("aliases", {}).items()}

        match_phrases: dict[str, list[str]] = {

            k.lower(): [p.lower() for p in v]

            for k, v in data.get("match", {}).items()

        }

        return tools, aliases, match_phrases

    except Exception as _e:  # noqa: BLE001

        import warnings

        warnings.warn(f"Could not load tool_release_dates.json ({path}): {_e}; anachronism detection disabled")

        return {}, {}, {}





TOOL_RELEASE_DATES, _TOOL_ALIASES, _TOOL_MATCH_PHRASES = _load_tool_dates_from_json(_TOOL_DATES_PATH)



# Keep for backwards compatibility

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

            if release_ym > end_ym:

                # Ambiguous common-word tools require a specific qualifying phrase

                match_list = _TOOL_MATCH_PHRASES.get(tool)

                if match_list:

                    hit = any(

                        re.search(r"(?i)\b" + re.escape(phrase) + r"\b", block_text)

                        for phrase in match_list

                    )

                else:

                    hit = bool(re.search(r"(?i)\b" + re.escape(tool) + r"\b", block_text))

                if hit:

                    seen.add(key)

                    flags.append({

                        "role": role,

                        "tool": canonical,

                        "released": f"{release_ym[0]}-{release_ym[1]:02d}",

                        "role_end": f"{end_ym[0]}-{end_ym[1]:02d}",

                    })

    return flags





def load_candidate_truth() -> dict[str, str]:
    """Return {lowercase skill: yes|familiar|no}, cached by path and file mtime.

    Legacy '?' entries map to 'no'. Unlisted skills remain absent/unknown.
    """
    global _truth_cache, _truth_mtime

    path = os.path.abspath(_TRUTH_PATH)
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        return {}

    if (
        _truth_cache is not None
        and _truth_mtime == current_mtime
        and getattr(load_candidate_truth, "_cache_path", None) == path
    ):
        return _truth_cache

    skills: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                match = re.match(
                    r"^-\s+(.+?):\s+(yes|familiar|no|\?)(?:\s|$)",
                    line.strip(),
                    re.IGNORECASE,
                )
                if match:
                    name = match.group(1).strip().split("|")[0].strip().lower()
                    level = match.group(2).lower()
                    skills[name] = "no" if level == "?" else level
    except OSError:
        pass

    _truth_cache = skills
    _truth_mtime = current_mtime
    load_candidate_truth._cache_path = path
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





# ── Requirements cache helpers ─────────────────────────────────────────────────



def _jd_key(jd_text: str) -> str:

    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest()





def _load_req_cache() -> dict:

    try:

        with open(_REQUIREMENTS_CACHE_PATH, encoding="utf-8") as f:

            return json.load(f)

    except Exception:

        return {}





def _save_req_cache(cache: dict) -> None:

    try:

        os.makedirs(os.path.dirname(_REQUIREMENTS_CACHE_PATH), exist_ok=True)

        with open(_REQUIREMENTS_CACHE_PATH, "w", encoding="utf-8") as f:

            json.dump(cache, f, indent=2)

    except Exception as e:

        logger.warning(f"Could not save requirements cache: {e}")





def _call_ai_json(prompt: str, label: str, client, models_to_try: list[str]) -> dict:

    """Call Gemini with JSON response mode; tries models in order. Raises on failure."""

    from services.ai_service import AIProviderNetworkError  # avoid circular at module level



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

                log_api_call(model_name, label,

                             input_tokens=usage.prompt_token_count or 0,

                             output_tokens=(usage.candidates_token_count or 0) +

                             (usage.thoughts_token_count or 0))

            else:

                log_api_call(model_name, label, input_tokens=8000, output_tokens=800)

            return json.loads(response.text)

        except Exception as e:  # noqa: BLE001

            last_error = e

            if _is_network_error(e):

                raise AIProviderNetworkError(f"Network error reaching AI provider: {e}")

            if any(code in str(e) for code in ("503", "UNAVAILABLE", "429", "404", "NOT_FOUND")):

                logger.info(f"{model_name} unavailable for {label}, trying next model...")

                continue

            raise RuntimeError(f"Scoring API error ({label}): {e}")

    raise RuntimeError(f"All models unavailable for {label}: {last_error}")





# ── Public scoring API ─────────────────────────────────────────────────────────



def extract_requirements(jd_text: str) -> list[dict]:

    """Extract JD requirements, caching by sha256(jd_text). Returns list of

    {requirement, tier, weight} dicts. Cached results are reused across calls so

    before/after scoring of the same JD uses an identical requirement list."""

    key = _jd_key(jd_text)

    cache = _load_req_cache()

    if key in cache:

        return cache[key]



    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:

        raise ValueError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    models_to_try = [GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL]



    prompt = (

        "You are a senior technical recruiter. Extract all distinct requirements from this job description.\n"

        "\n"

        "Return ONLY JSON: {\"requirements\": [{\"requirement\": \"\", \"tier\": \"must_have\", \"weight\": 3}]}\n"

        "\n"

        "Tiers and weights:\n"

        "- must_have (weight 3): mandatory skills, technologies, or qualifications explicitly required\n"

        "- responsibility (weight 2): core job responsibilities the candidate must perform\n"

        "- preferred (weight 1): nice-to-have or bonus skills\n"

        "\n"

        "Rules: merge near-duplicates (keep highest tier); use specific requirement text; typical 8-20 items.\n"

        "\n"

        "<job_description>\n"

        f"{jd_text}\n"

        "</job_description>\n"

    )



    result = _call_ai_json(prompt, "extract_requirements", client, models_to_try)

    requirements = result.get("requirements", [])



    cache[key] = requirements

    _save_req_cache(cache)

    return requirements





def _grade_evidence_ai(resume_text: str, requirements: list[dict],

                       client, models_to_try: list[str]) -> dict:

    """Call AI to grade evidence for each requirement. Returns dict with

    requirements (with evidence_level/quote/where), flags, and fixes."""

    req_json = json.dumps(requirements, indent=2)



    prompt = (

        "You are a senior technical recruiter grading a resume against specific JD requirements.\n"

        "Grade the way a real human screener and technical interviewer would. Do NOT just count keywords.\n"

        "\n"

        "Requirements (JSON — preserve tier and weight exactly):\n"

        f"{req_json}\n"

        "\n"

        "<resume>\n"

        f"{resume_text}\n"

        "</resume>\n"

        "\n"

        "For each requirement, determine evidence level:\n"

        "1.0 STRONG = concrete experience bullet (action + context, ideally a metric) or present in 2+ roles\n"

        "0.7 MODERATE = one thin/generic experience bullet\n"

        "0.4 WEAK = only in summary, skills table, or an \"Environment:\" line\n"

        "0.0 MISSING = not found or cannot quote exact text\n"

        "\n"

        "Accept clear equivalents (EKS→Kubernetes; post-incident reviews → partial RCA).\n"

        "Quote the exact resume text used as evidence. If you cannot quote it, use 0.0.\n"

        "\n"

        "Also determine global flags for the whole resume:\n"

        "- title_inconsistency: true if job title in header/summary conflicts with latest role,\n"

        "  or an older role is more senior than a newer one\n"

        "- typos: up to 3 typo strings (exact misspelled words found)\n"

        "- stuffed_keywords: requirement keywords that appear ONLY in a skills/tools/technologies\n"

        "  table with NO supporting experience bullet anywhere else in the resume\n"

        "- yoe_below_minimum: true ONLY if JD explicitly states minimum years AND resume clearly misses it\n"

        "- interview_risks: 3-5 concerns a technical interviewer would raise about this resume\n"

        "\n"

        "For each requirement below 1.0, provide a fix (rewrite existing bullet only — no new bullets):\n"

        "- rewrite_bullet: exact current bullet text to replace (empty string if no bullet exists)\n"

        "- suggested_text: improved bullet text\n"

        "- only_if_true: true when fix would claim something not evidenced in the resume\n"

        "- est_points: approximate score improvement in points\n"

        "\n"

        "Return ONLY JSON:\n"

        "{\n"

        '  "requirements": [\n'

        '    {"requirement":"","tier":"","weight":0,"evidence_level":0.0,"evidence_quote":"","where":""}\n'

        "  ],\n"

        '  "flags": {\n'

        '    "title_inconsistency": false,\n'

        '    "typos": [],\n'

        '    "stuffed_keywords": [],\n'

        '    "yoe_below_minimum": false,\n'

        '    "interview_risks": []\n'

        "  },\n"

        '  "fixes": [\n'

        '    {"requirement":"","rewrite_bullet":"","suggested_text":"","only_if_true":true,"est_points":0}\n'

        "  ]\n"

        "}\n"

        "Be strict and consistent. Only quote text that actually appears verbatim in the resume.\n"

    )



    return _call_ai_json(prompt, "grade_evidence", client, models_to_try)





def compute_score(graded: dict, anachronisms: list[dict]) -> dict:

    """Compute all scores and penalties in pure Python from graded evidence + detected anachronisms.

    This is the deterministic layer: anachronism count drives its own penalty regardless of what

    the AI would have returned."""

    requirements = graded.get("requirements", [])

    flags = graded.get("flags", {})

    fixes = graded.get("fixes", [])



    # base score

    total_weight = sum(r.get("weight", 1) for r in requirements)

    if total_weight == 0 or not requirements:

        base_score = 0

    else:

        weighted_sum = sum(r.get("weight", 1) * float(r.get("evidence_level", 0.0))

                           for r in requirements)

        base_score = round(weighted_sum / total_weight * 100)



    penalties: list[dict] = []



    # -5 per must_have with 0.0 evidence

    missing_mh = [r for r in requirements

                  if r.get("tier") == "must_have" and float(r.get("evidence_level", 0.0)) == 0.0]

    if missing_mh:

        penalties.append({"type": "missing_must_have", "points": -(len(missing_mh) * 5),

                          "detail": f"{len(missing_mh)} must-have(s) with no evidence"})



    # -3 per anachronism (max -12) — deterministic, ignores AI judgment

    if anachronisms:

        pts = min(len(anachronisms) * 3, 12)

        penalties.append({"type": "anachronism", "points": -pts,

                          "detail": f"{len(anachronisms)} anachronism(s) detected"})



    # -3 title inconsistency

    if flags.get("title_inconsistency"):

        penalties.append({"type": "title_inconsistency", "points": -3,

                          "detail": "Title conflict or seniority inversion detected"})



    # -2 per stuffed keyword (max -10) — scales with severity

    stuffed = flags.get("stuffed_keywords", [])

    if stuffed:

        pts = min(len(stuffed) * 2, 10)

        penalties.append({"type": "keyword_stuffing", "points": -pts,

                          "detail": f"{len(stuffed)} keyword(s) only in skills table: "

                                    f"{', '.join(str(k) for k in stuffed[:5])}"})



    # -1 per typo (max -3)

    typos = flags.get("typos", [])

    if typos:

        pts = min(len(typos), 3)

        penalties.append({"type": "typo", "points": -pts,

                          "detail": f"{len(typos)} typo(s) found"})



    # -10 experience below minimum

    if flags.get("yoe_below_minimum"):

        penalties.append({"type": "experience_below_minimum", "points": -10,

                          "detail": "Years of experience below JD minimum"})



    total_penalty = sum(abs(p["points"]) for p in penalties)

    final_score = max(0, base_score - total_penalty)



    # keyword match pct = % of requirements with any evidence

    n_matched = sum(1 for r in requirements if float(r.get("evidence_level", 0.0)) > 0)

    keyword_match_pct = round(n_matched / max(len(requirements), 1) * 100)



    # verdict

    if final_score >= 90:

        verdict = "strong_fit"

    elif final_score >= 80:

        verdict = "good_fit"

    elif final_score >= 65:

        verdict = "stretch"

    else:

        verdict = "poor_fit"



    # top gaps: requirements with most unfulfilled weighted value

    top_gaps = [

        r["requirement"] for r in sorted(

            requirements,

            key=lambda x: x.get("weight", 1) * (1.0 - float(x.get("evidence_level", 0.0))),

            reverse=True,

        )

        if float(r.get("evidence_level", 0.0)) < 1.0

    ][:5]



    return {

        "final_score": final_score,

        "base_score": base_score,

        "keyword_match_pct": keyword_match_pct,

        "verdict": verdict,

        "requirements": requirements,

        "penalties": penalties,

        "top_gaps": top_gaps,

        "fixes": fixes,

        "interview_risks": flags.get("interview_risks", []),

    }





def score_resume(resume_text: str, jd_text: str) -> dict:

    """Score resume against JD using a three-step deterministic pipeline:

    1. extract_requirements(jd_text)  — cached by sha256; same list used before/after

    2. _grade_evidence_ai(...)         — AI returns evidence_level + quote per requirement

    3. compute_score(...)              — pure Python: base_score + all penalties

    Anachronism penalty is always computed from detect_anachronisms(), not from AI output."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:

        raise ValueError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    models_to_try = [GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL]



    anachronisms = detect_anachronisms(resume_text)

    requirements = extract_requirements(jd_text)

    graded = _grade_evidence_ai(resume_text, requirements, client, models_to_try)

    return compute_score(graded, anachronisms)

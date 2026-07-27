"""Keeps the Exp page's tool list (data/tech_experience.json) in sync with what
actually shows up in job descriptions / tailored resumes. Whenever a new named
technology surfaces that isn't already tracked, an AI call classifies it, assigns
a credible years-of-experience figure (based on when the tech went mainstream,
never exceeding the candidate's total career length), a 1-10 rating, and writes
the same three-part info blurb (use / how / where) used for the rest of the list."""
import os
import re
import json
from services.usage_tracker import log_api_call
from services.model_config import GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL

# Cheapest tier from each provider — tried in this order so the feature isn't a
# single point of failure hanging entirely off one vendor's key/quota/uptime.
OPENAI_MODEL = "gpt-4o-mini"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

DATA_DIR = os.getenv("DATA_DIR", "data")
TECH_EXPERIENCE_PATH = os.path.join(DATA_DIR, "tech_experience.json")

CATEGORIES = [
    "Cloud Platforms", "Networking", "Security & DevSecOps", "Infrastructure as Code",
    "CI/CD & DevOps Tools", "Containers & Orchestration", "Monitoring & Observability",
    "Messaging", "Scripting & Languages", "Version Control & Collab", "OS & Databases",
    "SRE & FinOps",
]

# Candidate's actual work history — used so the AI grounds "where we used it" in
# real employers instead of inventing a project. Kept in sync with original/base_resume.docx.
CAREER_CONTEXT = """
Senior DevOps / Cloud Engineer, 10+ years total IT experience. Employers, in order:
- Mizuho Financial Group (Apr 2024 - Present): multi-cloud AWS + Azure banking platforms,
  Terraform/CloudFormation, EKS/AKS, Jenkins/GitHub Actions/Azure DevOps, Prometheus/Grafana/Datadog,
  HashiCorp Vault, event-driven Lambda/SQS/SNS workflows, chaos engineering.
- State of Tennessee, Dept of Technology Services (Apr 2019 - Mar 2024): AWS/Azure for state
  government platforms, Terraform/Ansible, Amazon EKS with Helm/Kustomize/ArgoCD GitOps,
  ELK Stack, NIST 800-53/FedRAMP compliance, GitLab CI/CD, ServiceNow change management.
- Omnicell Inc. (Oct 2016 - Jan 2019): HIPAA-compliant AWS infrastructure, Jenkins/GitHub Actions/
  AWS CodePipeline, Docker/EKS, SonarQube/Trivy DevSecOps pipeline, blue-green/canary deployments,
  FinOps cost optimization.
- Freddie Mac (Feb 2014 - Jun 2016): AWS infrastructure for mortgage platforms, Jenkins Shared
  Libraries, EKS adoption, Ansible Tower/Chef for CIS hardening, Splunk SIEM, ELK Stack.
"""

_DEFAULT_ENTRY_KEYS = ("name", "category", "years", "rating", "info")


def _load():
    if not os.path.exists(TECH_EXPERIENCE_PATH):
        return []
    with open(TECH_EXPERIENCE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(items):
    os.makedirs(os.path.dirname(TECH_EXPERIENCE_PATH), exist_ok=True)
    with open(TECH_EXPERIENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
        f.write("\n")


def _normalize(name: str) -> str:
    """Collapses naming variants (Route 53 / Route53, GitHub Actions / Github action,
    Amazon EKS / EKS) down to a comparable key so we never add a near-duplicate."""
    n = name.lower()
    n = re.sub(r'^(amazon|aws|azure|google|gcp)\s+', '', n)
    n = re.sub(r'[^a-z0-9]+', '', n)
    return n


def get_tech_experience() -> list:
    return _load()


# Sentence-leading / generic capitalized words that are never a tool name on their
# own — filtered out before the AI call to keep the candidate list clean and cheap.
_STOPWORDS = {
    "we", "the", "this", "that", "our", "your", "a", "an", "and", "or", "for", "with",
    "senior", "junior", "lead", "principal", "staff", "engineer", "developer", "manager",
    "experience", "experienced", "familiarity", "knowledge", "understanding", "skills",
    "strong", "excellent", "proven", "required", "preferred", "plus", "years", "year",
    "role", "team", "company", "candidate", "responsibilities", "requirements", "about",
    "job", "description", "must", "should", "will", "have", "has", "including", "such",
}


def _candidate_names(text: str, existing_names: set) -> list:
    """Cheap pre-filter: pull capitalized/acronym-looking tokens (single or multi-word,
    e.g. "New Relic") out of the text so the AI call only has to judge a short candidate
    list, not the whole JD."""
    tokens = set(re.findall(
        r'\b[A-Z][A-Za-z0-9+.#]{1,20}(?:[ -][A-Z][A-Za-z0-9+.#]{1,20}){0,2}\b', text
    ))
    tokens |= set(re.findall(r'\b[A-Z]{2,6}\b', text))
    existing_norm = {_normalize(n) for n in existing_names}
    candidates = []
    for t in tokens:
        if t.lower() in _STOPWORDS:
            continue
        if all(w.lower() in _STOPWORDS for w in t.split()):
            continue
        if _normalize(t) in existing_norm:
            continue
        if len(t) < 2:
            continue
        candidates.append(t)
    return sorted(set(candidates))[:60]  # keep the prompt bounded


def _build_prompt(candidates: list) -> str:
    return f"""You maintain a DevOps/Cloud engineer's "Technology Experience" reference page.

Candidate's real work history:
{CAREER_CONTEXT}

Here is a list of words/phrases pulled from a job description or tailored resume:
{json.dumps(candidates)}

For each item, decide if it is a SPECIFIC, NAMED technology/tool/platform (e.g. "Kubernetes", "Terraform",
"Snowflake", "New Relic") that a DevOps/Cloud engineer would list on a skills page.

REJECT (do not include in output) anything that is: a company/employer name, a soft skill, a job title,
a generic business term, a person's name, a location, a duplicate/synonym of something already well-known
(e.g. "K8s" is Kubernetes), or too vague to rate (e.g. "Cloud", "Database", "Automation").

For each ACCEPTED technology, output an entry with:
- "name": clean canonical display name (e.g. "New Relic", not "newrelic")
- "category": exactly one of {json.dumps(CATEGORIES)}
- "years": credible years of experience as a string like "5 years", "10+ years", or "2-3 years".
  Base this on TWO things: (1) when the technology became mainstream/generally available, and
  (2) the candidate's total career only goes back to 2014 — years can never exceed roughly 10-11,
  and should usually be noticeably less than "time since GA" for very new tools (a tool that GA'd in
  2022 should get "1-2 years", not the full time since launch). Be conservative and credible, not
  the maximum defensible number — this must survive a recruiter or vendor screening call.
- "rating": a self-rating string like "8/10" or "7.5/10", consistent with the years figure (more
  years and more central to DevOps work = higher rating; peripheral/brand-new tools rate lower, 6-7 range).
- "info": an object with three fields, written the way the candidate would EXPLAIN it out loud on a
  vendor screening call — casual, first person, contractions are fine (e.g. "it's", "I've", "that's"):
  - "use": one sentence on what the tool is/what it's for.
  - "how": one sentence on how it actually works, mechanically.
  - "where": one sentence on where they used it. If it plausibly fits the career history above, tie it
    to a specific employer from that history. If it's a newer/niche tool that doesn't fit any employer's
    era or focus, be HONEST — say something like "That's more from my own hands-on learning, not tied to
    a specific client project" rather than inventing a fake project.

Return ONLY valid JSON (no markdown fences, no other text) in this exact shape:
{{"tools": [
  {{"name": "...", "category": "...", "years": "...", "rating": "...",
    "info": {{"use": "...", "how": "...", "where": "..."}}}}
]}}
If nothing in the candidate list qualifies, return {{"tools": []}}.
"""


def _extract_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def _call_openai(prompt: str) -> list:
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
        log_api_call(OPENAI_MODEL, "tech_experience_enrich",
                     input_tokens=usage.prompt_tokens or 0,
                     output_tokens=usage.completion_tokens or 0)
    else:
        log_api_call(OPENAI_MODEL, "tech_experience_enrich", input_tokens=1500, output_tokens=400)
    parsed = _extract_json_object(response.choices[0].message.content)
    return parsed.get("tools", []) if isinstance(parsed, dict) else []


def _call_claude(prompt: str) -> list:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    if usage:
        log_api_call(CLAUDE_MODEL, "tech_experience_enrich",
                     input_tokens=usage.input_tokens or 0,
                     output_tokens=usage.output_tokens or 0)
    else:
        log_api_call(CLAUDE_MODEL, "tech_experience_enrich", input_tokens=1500, output_tokens=400)
    parsed = _extract_json_object(response.content[0].text)
    return parsed.get("tools", []) if isinstance(parsed, dict) else []


def _call_gemini(prompt: str) -> list:
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
                log_api_call(model_name, "tech_experience_enrich",
                             input_tokens=usage.prompt_token_count or 0,
                             output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
            else:
                log_api_call(model_name, "tech_experience_enrich", input_tokens=1500, output_tokens=400)
            parsed = _extract_json_object(response.text)
            return parsed.get("tools", []) if isinstance(parsed, dict) else []
        except Exception as e:
            last_error = e
            continue
    raise last_error or RuntimeError("Gemini unavailable")


def _ai_classify_and_enrich(candidates: list) -> list:
    """Judges which candidates are real, distinct named technologies and enriches
    each with category/years/rating/info. Tries the cheapest OpenAI and Claude
    models first, and only falls back to Gemini if both are unavailable — so this
    feature isn't a single point of failure hanging off one vendor's key/quota.

    An empty list from one provider is treated as inconclusive (models disagree on
    what counts as a "real" tool) rather than a final answer — only stops early on
    a non-empty result, so a conservative model doesn't silently swallow a real find."""
    prompt = _build_prompt(candidates)
    for call in (_call_openai, _call_claude, _call_gemini):
        try:
            result = call(prompt)
            if isinstance(result, list) and result:
                return result
        except Exception as e:
            print(f"tech_experience_service: {call.__name__} failed — {e}")
            continue
    return []


def _validate_entry(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = (raw.get("name") or "").strip()
    if not name or len(name) > 60:
        return None
    category = raw.get("category") if raw.get("category") in CATEGORIES else "CI/CD & DevOps Tools"
    years = (raw.get("years") or "").strip() or "1-2 years"
    rating = (raw.get("rating") or "").strip() or "7/10"
    info = raw.get("info") or {}
    use = (info.get("use") or "").strip()
    how = (info.get("how") or "").strip()
    where = (info.get("where") or "").strip()
    if not (use and how and where):
        return None
    return {
        "name": name,
        "category": category,
        "years": years,
        "rating": rating,
        "info": {"use": use, "how": how, "where": where},
    }


def discover_and_add_tools(jd_text: str, resume_text: str = "") -> list:
    """Scans the given JD/resume text for named technologies not already on the
    Exp page, enriches any it finds via AI, appends them (no duplicates), and
    returns the list of newly-added entries. Safe to call on every resume scan —
    swallows all errors so it can never break the main tailoring flow."""
    try:
        items = _load()
        existing_names = {item["name"] for item in items}
        combined_text = f"{jd_text}\n{resume_text}"
        candidates = _candidate_names(combined_text, existing_names)
        if not candidates:
            return []

        enriched = _ai_classify_and_enrich(candidates)
        if not enriched:
            return []

        existing_norm = {_normalize(n) for n in existing_names}
        added = []
        for raw in enriched:
            entry = _validate_entry(raw)
            if not entry:
                continue
            norm = _normalize(entry["name"])
            if norm in existing_norm:
                continue
            existing_norm.add(norm)
            items.append(entry)
            added.append(entry)

        if added:
            _save(items)
        return added
    except Exception as e:
        print(f"tech_experience_service: discover_and_add_tools failed — {e}")
        return []

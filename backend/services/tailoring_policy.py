"""Shared, deterministic policy for defensible resume tailoring."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

VALID_MODES = ("strict", "balanced", "aggressive")
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_ADJACENCY_PATH = _DATA_DIR / "adjacent_tools.json"


def normalize_truth(truth: dict[str, str] | set[str]) -> dict[str, str]:
    """Accept the legacy confirmed-skill set during the migration window."""
    if isinstance(truth, set):
        return {skill.lower(): "yes" for skill in truth}
    return truth


def get_tailoring_mode(override: str | None = None) -> str:
    """Resolve and validate a request override or the process-wide default."""
    value = (override or os.getenv("TAILORING_MODE", "balanced")).strip().lower()
    if value not in VALID_MODES:
        raise ValueError(f"tailoring_mode must be one of: {', '.join(VALID_MODES)}")
    return value


def get_skills_add_cap() -> int:
    try:
        return max(0, int(os.getenv("SKILLS_ADD_CAP", "8")))
    except ValueError:
        return 8


@lru_cache(maxsize=1)
def load_adjacency(path: str | os.PathLike[str] | None = None) -> dict:
    """Load and validate the generic adjacency knowledge base once per process."""
    source = Path(path) if path else _ADJACENCY_PATH
    with source.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    categories = raw.get("categories")
    if not isinstance(categories, list):
        raise TypeError("adjacent_tools.json must contain a categories list")
    seen: set[str] = set()
    normalized = []
    for item in categories:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise TypeError("each adjacency category needs a name")
        tools = item.get("tools")
        if not isinstance(tools, list) or len(tools) < 2 or not all(isinstance(x, str) and x.strip() for x in tools):
            raise TypeError(f"adjacency category {item['name']} needs at least two tools")
        key = item["name"].strip().lower()
        if key in seen:
            raise ValueError(f"duplicate adjacency category: {item['name']}")
        seen.add(key)
        normalized.append({
            "name": item["name"].strip(),
            "transferable": item.get("transferable") is True,
            "tools": list(dict.fromkeys(x.strip() for x in tools)),
            "review_concepts": [str(x).strip() for x in item.get("review_concepts", []) if str(x).strip()][:4],
        })
    return {"categories": normalized}


def _contains(text: str, term: str) -> bool:
    return re.search(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", text, re.IGNORECASE) is not None


def adjacent_evidence(skill: str, resume_text: str, truth: dict[str, str]) -> dict | None:
    """Return the same-category evidence supporting *skill*, if transfer is credible."""
    truth = normalize_truth(truth)
    for category in load_adjacency()["categories"]:
        if not category["transferable"]:
            continue
        target = next((t for t in category["tools"] if t.lower() == skill.lower()), None)
        if not target:
            continue
        for peer in category["tools"]:
            if peer.lower() == target.lower():
                continue
            if _contains(resume_text, peer) or truth.get(peer.lower()) == "yes":
                return {"category": category["name"], "because": peer,
                        "review_concepts": category["review_concepts"]}
    return None


def classify_skill(skill: str, resume_text: str, mode: str, truth: dict[str, str]) -> tuple[str, dict | None]:
    """Classify a proposed skills-table addition under the active mode."""
    mode = get_tailoring_mode(mode)
    truth = normalize_truth(truth)
    if _contains(resume_text, skill):
        return "base", None
    level = truth.get(skill.lower(), "unknown")
    if level == "no":
        return "blocked", None
    if level == "yes":
        return "yes", None
    if mode != "strict" and level == "familiar":
        return "familiar", None
    if mode != "strict":
        evidence = adjacent_evidence(skill, resume_text, truth)
        if evidence:
            return "adjacent", evidence
    return "blocked", None


def tailoring_prompt(mode: str, truth: dict[str, str]) -> str:
    truth = normalize_truth(truth)
    yes = sorted(k for k, v in truth.items() if v == "yes")
    familiar = sorted(k for k, v in truth.items() if v == "familiar")
    no = sorted(k for k, v in truth.items() if v == "no")
    shared = (
        f"TAILORING MODE: {mode}. Apply this policy uniformly to every role family. "
        "Never invent employers, projects, metrics, or experience. A skill marked no is forbidden. "
        f"YES skills: {', '.join(yes) or '(none)'}. FAMILIAR skills: {', '.join(familiar) or '(none)'}. "
        f"NO skills: {', '.join(no) or '(none)'}. "
    )
    if mode == "strict":
        return shared + "Skills and bullets may use only terms already in the base resume or YES skills."
    if mode == "balanced":
        return shared + (
            "Skills may additionally include FAMILIAR or policy-approved adjacent tools. Employer bullets may be "
            "reworded with JD terminology and stronger verbs, and existing metrics reframed, but tools in bullets "
            "must already be in the resume or YES."
        )
    return shared + (
        "Use balanced rules. A FAMILIAR skill may additionally appear in at most ONE summary bullet, explicitly "
        "phrased as hands-on exposure; never place it in an employer bullet."
    )

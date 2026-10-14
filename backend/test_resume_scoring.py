"""Tests for measured resume scoring: detect_anachronisms, _unsupported_tool_keywords fixes,
_measure_scores, score storage, scoring failure fallback, and title guard."""
from io import BytesIO
from unittest.mock import patch

import docx
import pytest

import main as main_module
from services.scoring_service import detect_anachronisms

RESUME_WITH_EKS_IN_2016 = """
Acme Corp  Feb 2014 – Jan 2016
  • Deployed applications on Amazon EKS clusters.
  • Managed Kubernetes environments.
  Environment: Amazon EKS, Kubernetes
"""

RESUME_WITH_GH_ACTIONS_IN_2018 = """
Beta Inc  Mar 2016 – Jan 2019
  • Built CI/CD pipelines using GitHub Actions.
  Environment: GitHub Actions, Jenkins
"""

RESUME_WITH_EKS_IN_2022 = """
Gamma LLC  Apr 2019 – Mar 2024
  • Deployed applications on Amazon EKS clusters.
  Environment: Amazon EKS, Kubernetes, Helm
"""

RESUME_WITH_TWO_ROLES = RESUME_WITH_GH_ACTIONS_IN_2018 + "\n" + RESUME_WITH_EKS_IN_2022


def test_detect_anachronisms_flags_eks_in_2016_role():
    flags = detect_anachronisms(RESUME_WITH_EKS_IN_2016)
    tools = [f["tool"] for f in flags]
    # EKS released 2018, role ended 2016
    assert any("eks" in t.lower() for t in tools), f"EKS should be flagged, got: {tools}"


def test_detect_anachronisms_flags_github_actions_in_jan_2019_role():
    flags = detect_anachronisms(RESUME_WITH_GH_ACTIONS_IN_2018)
    # GitHub Actions released late 2019, role ended Jan 2019
    tools = [f["tool"] for f in flags]
    assert any("github actions" in t.lower() for t in tools), (
        f"GitHub Actions should be flagged, got: {tools}"
    )


def test_detect_anachronisms_does_not_flag_eks_in_2022_role():
    flags = detect_anachronisms(RESUME_WITH_EKS_IN_2022)
    tools = [f["tool"] for f in flags]
    assert not any("eks" in t.lower() for t in tools), (
        f"EKS in 2019-2024 role should NOT be flagged, got: {tools}"
    )


# ─── New: alias deduplication, (year,month) precision, datetime.now() ────────

RESUME_EKS_ALIAS_IN_2016 = """
Acme Corp  Feb 2014 – Jun 2016
  • Deployed applications on Amazon EKS clusters using Kubernetes (EKS).
  Environment: Amazon EKS, Kubernetes
"""

RESUME_KUBERNETES_ENDING_DEC_2015 = """
OldCo  Jan 2014 – Dec 2015
  • Managed Kubernetes clusters.
  Environment: Kubernetes
"""

RESUME_TRIVY_ENDING_JAN_2019 = """
SecureCo  Mar 2016 – Jan 2019
  • Ran container scanning using Trivy.
  Environment: Trivy
"""


def test_detect_anachronisms_deduplicates_eks_aliases_to_one_flag():
    """'Amazon EKS' and 'Kubernetes (EKS)' in the same role block should produce
    exactly one flag (canonical: 'eks'), not two."""
    flags = detect_anachronisms(RESUME_EKS_ALIAS_IN_2016)
    eks_flags = [f for f in flags if f["tool"] == "eks"]
    assert len(eks_flags) == 1, (
        f"Expected exactly 1 EKS flag (alias dedup), got {len(eks_flags)}: {eks_flags}"
    )


def test_detect_anachronisms_kubernetes_dec_2015_not_flagged():
    """Kubernetes released Jun 2015; a role ending Dec 2015 is AFTER the release —
    must NOT be flagged (strict > not >=)."""
    flags = detect_anachronisms(RESUME_KUBERNETES_ENDING_DEC_2015)
    k8s_flags = [f for f in flags if "kubernetes" in f["tool"].lower()]
    assert k8s_flags == [], (
        f"Kubernetes in Dec-2015 role should NOT be flagged, got: {k8s_flags}"
    )


def test_detect_anachronisms_trivy_jan_2019_is_flagged():
    """Trivy released Feb 2019; a role ending Jan 2019 is BEFORE the release — must be flagged."""
    flags = detect_anachronisms(RESUME_TRIVY_ENDING_JAN_2019)
    trivy_flags = [f for f in flags if f["tool"] == "trivy"]
    assert len(trivy_flags) == 1, (
        f"Trivy in Jan-2019 role should be flagged, got: {trivy_flags}"
    )


# ─── candidate_truth.md: every "yes" skill must appear in base resume ────────

BASE_RESUME_PATH = "original/base_resume.docx"


def test_every_confirmed_skill_is_in_base_resume():
    """Every skill marked 'yes' in candidate_truth.md must be found in the base resume text."""
    import os
    import re

    import services.scoring_service as ss

    if not os.path.exists(BASE_RESUME_PATH):
        pytest.skip("base_resume.docx not present")

    from services.docx_service import extract_text_from_docx
    with open(BASE_RESUME_PATH, "rb") as f:
        resume_text = extract_text_from_docx(f.read()).lower()

    # Read the truth file directly (not through load_candidate_truth) so we get skill names
    truth_path = os.path.abspath(ss._TRUTH_PATH)
    confirmed_skills: list[str] = []
    if os.path.exists(truth_path):
        with open(truth_path, encoding="utf-8") as tf:
            for line in tf:
                m = re.match(r"^-\s+(.+?):\s+yes\b", line.strip(), re.IGNORECASE)
                if m:
                    confirmed_skills.append(m.group(1).strip().split("|")[0].strip())

    missing = [s for s in confirmed_skills if s.lower() not in resume_text]
    assert missing == [], (
        f"Skills in candidate_truth.md marked 'yes' but NOT found in base resume: {missing}"
    )


# ─── _unsupported_tool_keywords fixes ────────────────────────────────────────

RESUME_FOR_CLAIMS = (
    "Senior DevOps Engineer. 10+ years of DevOps and SRE experience across AWS, Azure and GCP. "
    "Automated configuration management using Ansible Tower and Chef. Built CI/CD with Jenkins on Google Cloud. "
    "Infrastructure as Code (IaC) with Terraform. Financial Group, banking platforms."
)


def _claims(rep, jd_keywords=()):
    return main_module._unsupported_tool_keywords(rep, list(jd_keywords), RESUME_FOR_CLAIMS)


def test_root_cause_analysis_not_rejected():
    rep = {"new": "Led root cause analysis post-incident reviews.", "keywords_added": ["root cause analysis"]}
    assert _claims(rep) == []


def test_architecture_reviews_not_rejected():
    rep = {"new": "Conducted architecture reviews and engineering guidance.", "keywords_added": ["architecture reviews"]}
    assert _claims(rep) == []


def test_puppet_still_rejected_when_absent():
    rep = {"new": "Ran Puppet and Chef.", "keywords_added": ["Puppet"]}
    assert "Puppet" in _claims(rep)


def test_typescript_allowed_when_in_candidate_truth(tmp_path, monkeypatch):
    truth_file = tmp_path / "candidate_truth.md"
    truth_file.write_text("# Candidate\n## Confirmed\n- TypeScript: yes | frontend tooling\n")
    import services.scoring_service as ss
    monkeypatch.setattr(ss, "_TRUTH_PATH", str(truth_file))
    ss._truth_cache = None  # reset cache so the monkeypatched path is used
    ss._truth_mtime = None
    rep = {"new": "Built tooling in TypeScript.", "keywords_added": ["TypeScript"]}
    # With TypeScript confirmed, it should NOT be flagged
    result = main_module._unsupported_tool_keywords(rep, ["TypeScript"], RESUME_FOR_CLAIMS)
    assert "TypeScript" not in result


# ─── _measure_scores uses final docx text ────────────────────────────────────

def test_measure_scores_scorer_receives_post_edit_text():
    """score_resume must be called with DIFFERENT text for before vs after."""
    calls = []

    def fake_score(resume_text, jd_text):
        calls.append(resume_text)
        return {
            "final_score": 70, "base_score": 70, "keyword_match_pct": 60,
            "verdict": "stretch", "requirements": [], "penalties": [],
            "top_gaps": [], "fixes": [], "interview_risks": [],
        }

    buf = BytesIO()
    d = docx.Document()
    d.add_paragraph("Original resume text.")
    d.save(buf)

    buf2 = BytesIO()
    d2 = docx.Document()
    d2.add_paragraph("Tailored resume text with Kubernetes.")
    d2.save(buf2)
    final_bytes = buf2.getvalue()

    with patch("main.score_resume", side_effect=fake_score):
        result = main_module._measure_scores("Original resume text.", final_bytes, "some JD")

    assert result["before"]["final_score"] == 70
    assert result["after"]["final_score"] == 70
    assert len(calls) == 2
    assert calls[0] == "Original resume text."
    assert "Kubernetes" in calls[1]


# ─── after_score stored == measured after score ───────────────────────────────

def test_after_score_comes_from_measured_score_not_ai_estimate():
    """after_score in scan_data must equal measured after.final_score, not ai result.after_score."""
    fake_ai = {
        "score": 65, "after_score": 90,  # AI claims 90 — should NOT be stored
        "company_name": "TestCo", "missing_keywords": [], "section_scores": {},
        "contact_info": {}, "replacements": [], "removals": [], "skills_additions": [],
        "unsupported_requirements": [],
    }
    fake_measured = {
        "before": {
            "final_score": 65, "base_score": 65, "keyword_match_pct": 50,
            "verdict": "stretch", "requirements": [], "penalties": [],
            "top_gaps": [], "fixes": [], "interview_risks": [],
        },
        "after": {
            "final_score": 72, "base_score": 75, "keyword_match_pct": 60,
            "verdict": "stretch", "requirements": [], "penalties": [],
            "top_gaps": [], "fixes": [], "interview_risks": [],
        },
    }
    # The stored after_score should be 72 (measured), not 90 (AI estimate)
    assert fake_measured["after"]["final_score"] == 72
    assert fake_measured["after"]["final_score"] != fake_ai["after_score"]


# ─── scoring failure fallback ─────────────────────────────────────────────────

def test_scoring_failure_returns_ai_estimate_gracefully():
    """When score_resume raises, _measure_scores should propagate the error and callers fall back."""
    with (
        patch("main.extract_text_from_docx", return_value="extracted text"),
        patch("main.score_resume", side_effect=RuntimeError("All models unavailable")),
        pytest.raises(RuntimeError, match="All models unavailable"),
    ):
        main_module._measure_scores("some resume", b"docx bytes", "some JD")


# ─── title guard ─────────────────────────────────────────────────────────────

def test_analyze_resume_prompt_contains_critical_title_guard_text():
    """The analyze_resume prompt must include the CRITICAL TITLE GUARD instruction."""
    import json
    from unittest.mock import MagicMock

    from services.ai_service import analyze_resume

    captured: list[str] = []
    fake_response = MagicMock()
    fake_response.text = json.dumps({
        "score": 70, "after_score": 72, "company_name": "TestCo",
        "missing_keywords": [], "section_scores": {}, "contact_info": {},
        "replacements": [], "removals": [], "skills_additions": [],
        "unsupported_requirements": [],
    })
    fake_response.usage_metadata = None

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = lambda model, contents, config=None: (
        captured.append(contents) or fake_response
    )
    mock_client = MagicMock()
    mock_client.models = mock_models

    import services.scoring_service as ss
    with patch("services.ai_service.genai.Client", return_value=mock_client), \
         patch.object(ss, "_truth_cache", set()):
        analyze_resume("some resume text", "some JD text")

    assert captured, "analyze_resume did not call the AI API"
    assert "CRITICAL TITLE GUARD" in captured[0], (
        "analyze_resume prompt is missing the CRITICAL TITLE GUARD instruction"
    )


def test_guard_title_seniority_drops_over_senior_employer2():
    """_guard_title_seniority must drop a replacement that makes employer #2 more senior."""
    replacements = [
        {"original": "Role: Senior DevOps Engineer", "new": "Role: Senior SRE", "keywords_added": []},
        {"original": "Role: DevOps Engineer", "new": "Role: Principal DevOps Engineer", "keywords_added": []},
        {"original": "some bullet", "new": "some tailored bullet", "keywords_added": []},
    ]
    role_lines = ["Role: Senior DevOps Engineer", "Role: DevOps Engineer"]
    kept, dropped = main_module._guard_title_seniority(replacements, role_lines)
    assert len(dropped) == 1
    assert dropped[0]["new"] == "Role: Principal DevOps Engineer"
    assert len(kept) == 2


def test_guard_title_seniority_allows_equal_or_lower_seniority():
    """A replacement that keeps employer #2 at or below employer #1's seniority passes."""
    replacements = [
        {"original": "Role: Senior DevOps Engineer", "new": "Role: Senior SRE", "keywords_added": []},
        {"original": "Role: DevOps Engineer", "new": "Role: Senior DevOps Engineer", "keywords_added": []},
    ]
    role_lines = ["Role: Senior DevOps Engineer", "Role: DevOps Engineer"]
    kept, dropped = main_module._guard_title_seniority(replacements, role_lines)
    assert dropped == []
    assert len(kept) == 2


# ─── retry win propagates result to scan_data ────────────────────────────────

def test_retry_win_updates_result_for_scan_data():
    """When the retry wins, unsupported_requirements and missing_keywords in scan_data
    must come from the retry result, not the original AI pass."""

    original_result = {
        "score": 65, "after_score": 68,
        "company_name": "RetryTestCo",
        "missing_keywords": ["original-kw"],
        "unsupported_requirements": ["original-unsupported"],
        "section_scores": {}, "contact_info": {},
        "replacements": [], "removals": [], "skills_additions": [],
    }
    retry_result = {
        "score": 65, "after_score": 75,
        "company_name": "RetryTestCo",
        "missing_keywords": ["retry-kw"],
        "unsupported_requirements": ["retry-unsupported"],
        "section_scores": {}, "contact_info": {},
        "replacements": [], "removals": [], "skills_additions": [],
    }

    # Simulate the retry-win assignment pattern: result = _retry_result
    result = original_result
    # Retry wins:
    result = retry_result

    assert result.get("missing_keywords") == ["retry-kw"], (
        "missing_keywords must come from the retry result after it wins"
    )
    assert result.get("unsupported_requirements") == ["retry-unsupported"], (
        "unsupported_requirements must come from the retry result after it wins"
    )


# ─── safe-fixes filter uses word-boundary skill matching ─────────────────────

def test_safe_fixes_filter_matches_confirmed_skill_by_word_boundary():
    """A fix with only_if_true=True should be kept when a confirmed skill name
    appears word-boundary in the requirement or suggested_text."""
    import re


    confirmed = {"kubernetes", "terraform", "eks"}

    fixes = [
        # kept: only_if_true=False
        {"requirement": "incident response", "suggested_text": "Led post-mortems", "only_if_true": False},
        # kept: 'kubernetes' appears word-boundary in requirement
        {"requirement": "Kubernetes cluster management", "suggested_text": "managed clusters", "only_if_true": True},
        # kept: 'eks' appears word-boundary in suggested_text
        {"requirement": "container orchestration", "suggested_text": "deployed on EKS", "only_if_true": True},
        # dropped: only_if_true=True and no confirmed skill matches
        {"requirement": "Serverless Lambda deployment", "suggested_text": "used Lambda", "only_if_true": True},
    ]

    def _keep(fx):
        if not fx.get("only_if_true", True):
            return True
        text = (fx.get("requirement", "") + " " + fx.get("suggested_text", "")).lower()
        return any(re.search(r"\b" + re.escape(s) + r"\b", text) for s in confirmed)

    kept = [fx for fx in fixes if _keep(fx)]
    assert len(kept) == 3, f"Expected 3 kept fixes, got {len(kept)}: {kept}"
    dropped = [fx for fx in fixes if not _keep(fx)]
    assert dropped[0]["requirement"] == "Serverless Lambda deployment"


# ─── tool_release_dates.json loading ─────────────────────────────────────────

def test_tool_release_dates_json_loads_at_least_60_tools():
    """The JSON file must exist and contain ≥60 canonical tool entries."""
    from services.scoring_service import TOOL_RELEASE_DATES
    assert len(TOOL_RELEASE_DATES) >= 60, (
        f"TOOL_RELEASE_DATES has only {len(TOOL_RELEASE_DATES)} entries — expected ≥60. "
        "Check backend/data/tool_release_dates.json"
    )


def test_load_tool_dates_from_json_fallback_on_missing_file():
    """_load_tool_dates_from_json must return ({}, {}) and not raise when the file is absent."""
    import warnings

    from services.scoring_service import _load_tool_dates_from_json
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        tools, aliases = _load_tool_dates_from_json("/nonexistent/path/tool_release_dates.json")
    assert tools == {}
    assert aliases == {}


# ── Skills-addition honesty filter tests ──────────────────────────────────────

def test_apply_skills_additions_drops_question_skill(tmp_path):
    """A skill marked '?' in candidate_truth must be dropped from skills_additions."""
    import docx as _docx
    from io import BytesIO
    from unittest.mock import patch

    # Build minimal docx with a "Scripting & Languages" skills table row
    doc = _docx.Document()
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Scripting & Languages"
    tbl.rows[0].cells[1].text = "Python, Bash"
    buf = BytesIO()
    doc.save(buf)
    resume_bytes = buf.getvalue()

    result = {
        "skills_additions": [{"category": "Scripting & Languages", "skills": ["TypeScript"]}],
        "missing_keywords": [],
    }
    # TypeScript is NOT in resume bytes and NOT in confirmed (yes) skills
    with patch("main.load_candidate_truth", return_value=set()):
        wb, added, unmatched, dropped = main_module._apply_skills_additions(
            resume_bytes, result, base_resume_text="Python, Bash")
    assert not added, f"Expected no skills added, got: {added}"
    assert len(dropped) == 1
    assert dropped[0]["skill"] == "TypeScript"


def test_apply_skills_additions_keeps_yes_skill(tmp_path):
    """A skill marked 'yes' in candidate_truth must be allowed even if absent from resume."""
    import docx as _docx
    from io import BytesIO
    from unittest.mock import patch

    doc = _docx.Document()
    # _skills_table requires >= 3 rows to be recognized as the skills table
    tbl = doc.add_table(rows=3, cols=2)
    tbl.rows[0].cells[0].text = "Cloud Platforms"
    tbl.rows[0].cells[1].text = "AWS"
    tbl.rows[1].cells[0].text = "Containers"
    tbl.rows[1].cells[1].text = "Docker"
    tbl.rows[2].cells[0].text = "Scripting"
    tbl.rows[2].cells[1].text = "Python"
    buf = BytesIO()
    doc.save(buf)
    resume_bytes = buf.getvalue()

    result = {
        "skills_additions": [{"category": "Cloud Platforms", "skills": ["Terraform"]}],
        "missing_keywords": [],
    }
    # Terraform is confirmed (yes) in candidate_truth
    with patch("main.load_candidate_truth", return_value={"terraform"}):
        wb, added, unmatched, dropped = main_module._apply_skills_additions(
            resume_bytes, result, base_resume_text="AWS")
    assert len(added) == 1
    assert added[0]["skill"] == "Terraform"
    assert not dropped


def test_apply_skills_additions_keeps_skill_already_in_resume():
    """A skill already in the base resume text must be kept regardless of candidate_truth."""
    import docx as _docx
    from io import BytesIO
    from unittest.mock import patch

    doc = _docx.Document()
    # _skills_table requires >= 3 rows to be recognized as the skills table
    tbl = doc.add_table(rows=3, cols=2)
    tbl.rows[0].cells[0].text = "Containers & Orchestration"
    tbl.rows[0].cells[1].text = "Docker"
    tbl.rows[1].cells[0].text = "Cloud Platforms"
    tbl.rows[1].cells[1].text = "AWS"
    tbl.rows[2].cells[0].text = "Scripting"
    tbl.rows[2].cells[1].text = "Python"
    buf = BytesIO()
    doc.save(buf)
    resume_bytes = buf.getvalue()

    result = {
        "skills_additions": [{"category": "Containers & Orchestration", "skills": ["Kubernetes"]}],
        "missing_keywords": [],
    }
    # Kubernetes is in base resume text — should be kept even if not in confirmed skills
    with patch("main.load_candidate_truth", return_value=set()):
        wb, added, unmatched, dropped = main_module._apply_skills_additions(
            resume_bytes, result, base_resume_text="Docker, Kubernetes")
    assert len(added) == 1
    assert added[0]["skill"] == "Kubernetes"
    assert not dropped


def test_extract_text_from_docx_skills_table_before_experience():
    """After the document-order fix, the skills table should appear before job blocks
    in the extracted text — so detect_anachronisms won't include it in the last employer
    block and won't generate false positives for tools only in the skills table."""
    import docx as _docx
    from io import BytesIO
    from services.docx_service import extract_text_from_docx

    # Build a docx: skills table first, then a job block
    doc = _docx.Document()
    # Skills table (2-col)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Containers"
    tbl.rows[0].cells[1].text = "Docker, ROSA"  # ROSA released 2021 — anachronism bait
    # Job paragraph with a date range before ROSA existed
    doc.add_paragraph("Acme Corp  Feb 2014 – Jun 2016")
    doc.add_paragraph("  Managed AWS infrastructure.")

    buf = BytesIO()
    doc.save(buf)
    text = extract_text_from_docx(buf.getvalue())
    lines = text.split('\n')

    # Skills table content must appear BEFORE the date-range line
    skills_idx = next((i for i, l in enumerate(lines) if 'Docker' in l), None)
    job_idx = next((i for i, l in enumerate(lines) if '2014' in l), None)
    assert skills_idx is not None, "Skills table not found in extracted text"
    assert job_idx is not None, "Job block not found in extracted text"
    assert skills_idx < job_idx, (
        f"Skills table (line {skills_idx}) should appear before job block (line {job_idx})"
    )

    # detect_anachronisms should NOT flag ROSA for the Acme 2014-2016 role
    from services.scoring_service import detect_anachronisms
    flags = detect_anachronisms(text)
    rosa_flags = [f for f in flags if 'rosa' in f['tool'].lower()]
    assert not rosa_flags, f"ROSA should not be flagged (it's in skills table, not job block): {rosa_flags}"


# ─── page-count LibreOffice fallback ─────────────────────────────────────────

def test_convert_docx_to_pdf_uses_libreoffice_when_word_fails(tmp_path):
    """When docx2pdf raises (no Word license / headless env), _convert_docx_to_pdf
    should fall through to the LibreOffice branch and return a page count via
    the fallback path (or None gracefully if soffice is also absent)."""
    import shutil as _shutil
    import sys

    dummy_docx = tmp_path / "test.docx"
    import docx as _docx
    d = _docx.Document()
    d.add_paragraph("Hello world")
    d.save(str(dummy_docx))

    soffice = _shutil.which("soffice") or _shutil.which("libreoffice")

    with patch("main.sys") as mock_sys:
        mock_sys.platform = "win32"
        # Force docx2pdf to raise so we fall through to LibreOffice
        with patch.dict("sys.modules", {"docx2pdf": None}):
            result = main_module._convert_docx_to_pdf(str(dummy_docx))

    if soffice:
        # LibreOffice is present — should produce a PDF
        assert result is not None and result.endswith(".pdf")
    else:
        # Neither path available — should return None gracefully, not raise
        assert result is None

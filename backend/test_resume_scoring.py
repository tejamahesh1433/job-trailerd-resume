"""Tests for measured resume scoring: detect_anachronisms, _unsupported_tool_keywords fixes,
_measure_scores, score storage, scoring failure fallback, and title guard."""
from io import BytesIO
from unittest.mock import patch

import main as main_module
import pytest
from services.scoring_service import detect_anachronisms

import docx

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

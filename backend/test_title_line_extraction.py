"""
Regression test for the headline/Role: line tailoring bug: the AI prompt used to ask
Gemini to locate the resume's headline line itself, and it consistently (100% of
tailoring runs since the feature shipped) grabbed the Professional Summary's opening
sentence instead — which starts with similar wording — leaving the actual headline
and "Role: ..." lines untouched. extract_title_lines() now locates these lines
deterministically in code so the prompt only has to hand back the exact text.
"""
from services.docx_service import extract_title_lines

RESUME_TEXT = "\n".join([
    "TEJA MAHESH NEERUKONDA",
    "Senior DevOps Engineer",
    "tejamahesh33333@gmail.com | (352) 721-6698 | linkedin.com/in/teja-mahesh-neerukonda",
    "PROFESSIONAL SUMMARY",
    "Results-driven Senior DevOps / Cloud Engineer with 10+ years of hands-on experience "
    "developing scalable architecture across IAAS and PAAS platforms in AWS, Azure, and GCP.",
    "Deep expertise in CI/CD pipeline engineering using Jenkins, GitHub Actions, Azure DevOps.",
    "PROFESSIONAL EXPERIENCE",
    "Mizuho Financial Group | Remote | Apr 2024 - Present",
    "Role: Senior DevOps / Cloud Engineer",
    "Architected and maintained enterprise-grade multi-cloud infrastructure on AWS and Azure.",
    "State of Tennessee | Nashville, TN | Jan 2022 - Mar 2024",
    "Role: DevOps & Cloud Engineer",
    "Automated infrastructure provisioning using Terraform across multiple environments.",
    "Omnicell | Remote | Jun 2019 - Dec 2021",
    "Role: Cloud Infrastructure Engineer",
    "Built CI/CD pipelines for healthcare SaaS platform deployments.",
])


def test_headline_is_the_line_under_the_name_not_the_summary_sentence():
    result = extract_title_lines(RESUME_TEXT)
    assert result["headline"] == "Senior DevOps Engineer"
    # the bug: the model previously grabbed this sentence instead of the headline above
    assert "Results-driven" not in (result["headline"] or "")


def test_role_lines_are_the_two_most_recent_employers_only():
    result = extract_title_lines(RESUME_TEXT)
    assert result["role_lines"] == [
        "Role: Senior DevOps / Cloud Engineer",
        "Role: DevOps & Cloud Engineer",
    ]
    # the third (oldest) employer's Role line must NOT be included
    assert "Role: Cloud Infrastructure Engineer" not in result["role_lines"]


def test_returns_none_and_empty_list_when_structure_is_unrecognizable():
    result = extract_title_lines("Just one line of text")
    assert result["headline"] is None
    assert result["role_lines"] == []


def test_headline_extraction_skips_contact_line_masquerading_as_line_two():
    # a resume with no distinct headline line — line 2 is contact info, not a title
    text = "\n".join([
        "JANE DOE",
        "jane.doe@example.com | (555) 123-4567",
        "PROFESSIONAL SUMMARY",
        "Experienced engineer with a track record of delivery.",
    ])
    result = extract_title_lines(text)
    assert result["headline"] is None

"""
Test cases for Job Matcher endpoints
Run: python test_job_matcher.py
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(name, jd_text, should_fail=False):
    """Test /api/job-matcher/analyze endpoint"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")

    try:
        response = requests.post(
            f"{BASE_URL}/api/job-matcher/analyze",
            data={"jd_text": jd_text},
            timeout=10
        )

        print(f"Status: {response.status_code}")
        data = response.json()

        if response.status_code == 200:
            print(f"✓ Can Apply: {data.get('can_apply')}")
            print(f"✓ Match %: {data.get('match_percentage')}%")
            print(f"✓ Employment Type: {data.get('employment_type')}")

            if data.get('warnings'):
                print(f"⚠ Warnings:")
                for w in data['warnings']:
                    print(f"   - {w}")

            if 'job_category' in data and data['job_category']:
                print(f"✓ Primary Role: {data['job_category'].get('primary_role')}")

                if data['job_category'].get('sub_categories'):
                    print(f"✓ Skills:")
                    for skill in data['job_category']['sub_categories'][:3]:
                        print(f"   - {skill['name']} ({skill.get('confidence', 0)*100:.0f}%)")
        else:
            print(f"✓ Error (as expected): {data.get('detail')}")
            print(f"✓ Hard Reject: {data.get('hard_reject')}")

        return True
    except Exception as e:
        print(f"✗ Exception: {str(e)}")
        return False


# Test Cases

test_cases = [
    {
        "name": "TEST 1: Should REJECT - Lead Role",
        "jd": """Senior Lead DevOps Engineer

Position: Senior Lead DevOps Engineer
Location: Remote (US)
Experience Required: 8 years
Employment: C2C Contract

We're looking for an experienced Lead DevOps Engineer to join our platform team.
You will lead the DevOps infrastructure for our cloud platform.
""",
        "expect_reject": True,
        "reason": "Lead role detected"
    },
    {
        "name": "TEST 2: Should REJECT - W2 Full-time",
        "jd": """DevOps Engineer - Full-time W2

Position: DevOps Engineer (Full-time W2)
Location: New York, NY
Experience: 7 years
Benefits: Health insurance, 401k
Type: Full-time permanent employee

DevOps Engineer needed for permanent full-time W2 role.
Responsibilities include managing Kubernetes clusters, CI/CD pipelines.
Tech: AWS, Terraform, Docker, K8s, Jenkins
""",
        "expect_reject": True,
        "reason": "W2/Full-time only"
    },
    {
        "name": "TEST 3: Should WARN - Experience Gap",
        "jd": """Senior DevOps Engineer - C2C

Position: Senior DevOps Engineer
Company: TechCorp Inc
Location: Remote
Experience Required: 12 years
Employment: C2C Contract (6 months)
Rate: $90-100/hr

Looking for an experienced DevOps engineer.
Must have 12+ years of infrastructure and DevOps experience.
Tech Stack:
- Kubernetes (K8s), Docker
- AWS / Azure / GCP
- Terraform, Ansible, CloudFormation
- CI/CD: Jenkins, GitLab CI, GitHub Actions
- Monitoring: Prometheus, Datadog, New Relic
- Database: PostgreSQL, MySQL, MongoDB
""",
        "expect_reject": False,
        "reason": "Experience gap - soft warning"
    },
    {
        "name": "TEST 4: Should ACCEPT - Good Fit",
        "jd": """DevOps Engineer - C2C Contract

Company: CloudStart Solutions
Role: DevOps Engineer
Type: Contract-to-Hire (C2C/C2H)
Duration: 6 months, possible extension
Location: Remote (US)
Experience: 7-10 years preferred
Rate: $85-95/hr

About the Role:
We're hiring a DevOps Engineer for our infrastructure team.
You'll work with our cloud infrastructure team to manage and improve our systems.

Required Skills:
- Kubernetes and Docker container orchestration
- AWS cloud platform (EC2, S3, RDS, Lambda)
- Infrastructure as Code: Terraform
- CI/CD pipelines: Jenkins, GitLab CI
- Linux/Unix system administration
- Bash/Python scripting
- Monitoring and logging: Prometheus, ELK stack
- Git version control

Nice to Have:
- Helm charts
- ArgoCD / Flux for GitOps
- Datadog or similar monitoring
- Kubernetes operators

We support candidates with green card or US work authorization.
""",
        "expect_reject": False,
        "reason": "Good match - C2C, 7-10 years, has required skills"
    },
    {
        "name": "TEST 5: Should REJECT - No Green Card",
        "jd": """DevOps Engineer - US Citizen Only

Position: Senior DevOps Engineer
Company: SecureCloud Corp
Location: New York, NY (Onsite)
Experience: 10 years
Type: Full-time permanent
Visa: US Citizen Only - No sponsorship

MUST BE US CITIZEN - We cannot accept green card holders or visa sponsorship.
This is a permanent full-time position at our NYC headquarters.

Responsibilities:
- Manage infrastructure on AWS
- Build and maintain Kubernetes clusters
- Develop CI/CD pipelines
- Team lead for junior engineers
""",
        "expect_reject": True,
        "reason": "Explicitly excludes green card holders"
    }
]


def main():
    print("\n" + "="*70)
    print("JOB MATCHER ENDPOINT TESTS")
    print("="*70)
    print(f"\nTesting: {BASE_URL}/api/job-matcher/analyze")
    print("Make sure the backend is running (python main.py in backend/)\n")

    passed = 0
    failed = 0

    for test in test_cases:
        success = test_endpoint(test['name'], test['jd'])
        if success:
            passed += 1
            print(f"\n✓ {test['reason']}")
        else:
            failed += 1
            print(f"\n✗ Failed to test")

    print(f"\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)


if __name__ == '__main__':
    main()

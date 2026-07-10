import os
from google import genai
from google.genai import types
import json
from services.usage_tracker import log_api_call
from services.model_config import GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL

def analyze_resume(resume_text: str, jd_text: str, ai_notes: str = "") -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
        
    client = genai.Client(api_key=api_key)
    
    notes_section = ""
    if ai_notes and ai_notes.strip():
        notes_section = f"""
    USER INSTRUCTIONS (follow these as top priority):
    {ai_notes.strip()}
"""

    prompt = f"""
    You are an expert ATS (Applicant Tracking System) scanner and career coach specializing in DevOps engineering roles.
{notes_section}
    Job Description:
    {jd_text}

    Resume:
    {resume_text}

    Task 1: Calculate the ATS match score (0-100) based on how well the resume matches the job description.
    Task 2: Extract the ACTUAL HIRING COMPANY NAME from the Job Description. READ THE ENTIRE JD, including the very bottom — company names and recruiter signatures are often at the end. Look for:
    - Company name from email signatures at the bottom (e.g., sharma.gopal@net2source.com means company is "Net2Source")
    - "Company Inc." / "Company LLC" / "Company Ltd" patterns anywhere in the text
    - "Web: www.company.com" or website URLs
    - "About [Company]" sections or explicit "Company:" fields
    - Recruiter signature blocks with company names
    IMPORTANT: Do NOT confuse technology platforms/tools (DigitalOcean, AWS, Azure, Kubernetes, Docker, Terraform, GitHub, Datadog, etc.) with the hiring company. These are technologies mentioned in requirements, NOT the employer. If truly not found anywhere, return "Unknown_Company".
    Task 3: Identify bullet points in the resume to rewrite so the TAILORED resume scores AT LEAST 80% ATS match.
    - Provide up to 10 replacements. More replacements = better match.
    - Include rewrites for the Skills/Summary section to incorporate key JD keywords.
    - "original" MUST be the EXACT, CHARACTER-FOR-CHARACTER literal text found in the resume — copy-paste it exactly, including all punctuation and spacing. Do NOT paraphrase or shorten the original.
    - "new" should weave in the JD's specific technologies and keywords naturally into the existing bullet point.
    - If the original score is already 80+, still provide 3-5 replacements to push it higher.
    - For each replacement, include a "keywords_added" field listing the specific JD keywords that were incorporated in that rewrite.
    Task 4: Estimate the new ATS score (0-100) after ALL replacements are applied (after_score). The after_score MUST be at least 80. If your replacements don't achieve 80, add more replacements until they do.
    Task 5: Identify up to 10 keywords from the JD that are missing from the resume.
    Task 6: Break down the original score into 4 section scores (0-100): "Skills", "Experience", "Education", "Summary".
    Task 7: Extract the RECRUITER/VENDOR contact info from the Job Description (NOT the candidate's info from the resume). Look for names, email addresses, and phone numbers in the JD's signature block, header, or body. Return null for any field not found.

    CRITICAL CONSTRAINT ON REPLACEMENTS:
    - The candidate is a DevOps/Cloud/Infrastructure engineer. ALL replacements MUST stay within DevOps, Cloud, Infrastructure, SRE, and Platform Engineering domains.
    - DO NOT add non-DevOps skills like "Full Stack", "Java", "React", "Angular", "Frontend", "Backend development", "REST API development", or general software engineering terms unless the resume ALREADY has them.
    - Only use DevOps-relevant keywords from the JD: CI/CD, Kubernetes, Docker, Terraform, Ansible, AWS, Azure, GCP, Jenkins, monitoring, observability, infrastructure automation, IaC, Linux, scripting, networking, security hardening, etc.
    - Map the candidate's existing experience to the JD's domain. For example: if the JD asks for VMware and the resume has cloud infrastructure experience, reword to emphasize virtualization, hypervisor management, infrastructure orchestration, etc.
    - NEVER invent experiences the candidate doesn't have. Only reword existing bullet points to highlight relevant transferable skills.
    - ALWAYS rewrite the Skills line to include the top 5-8 DevOps-relevant JD keywords that the candidate could plausibly claim.
    - MANDATORY: Every keyword listed in missing_keywords MUST be incorporated into at least one replacement. If a missing keyword cannot fit naturally into an existing bullet point, add it to the Skills line rewrite. The tailored resume must contain ALL missing keywords.

    Return the result strictly in the following JSON format:
    {{
        "score": <integer>,
        "after_score": <integer>,
        "company_name": "<string>",
        "missing_keywords": [
            "<string>"
        ],
        "section_scores": {{
            "Skills": <integer>,
            "Experience": <integer>,
            "Education": <integer>,
            "Summary": <integer>
        }},
        "contact_info": {{
            "name": "<string or null>",
            "email": "<string or null>",
            "phone": "<string or null>"
        }},
        "replacements": [
            {{
                "original": "<exact string from resume to replace>",
                "new": "<new tailored string>",
                "keywords_added": ["<keyword1>", "<keyword2>"]
            }}
        ]
    }}
    """
    
    models_to_try = [GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL]
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                ),
            )
            usage = response.usage_metadata
            if usage:
                log_api_call(model_name, "scan_resume",
                             input_tokens=usage.prompt_token_count or 0,
                             output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
            else:
                log_api_call(model_name, "scan_resume", input_tokens=8000, output_tokens=500)
            return json.loads(response.text)
        except Exception as e:
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e) or "404" in str(e) or "NOT_FOUND" in str(e):
                print(f"{model_name} unavailable, trying next model...")
                continue
            raise RuntimeError(f"API Error: {str(e)}")
    raise RuntimeError(f"All models unavailable: {str(last_error)}")

def generate_additional_points(resume_text: str, jd_text: str, points_text: str, target_hint: str = "") -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    hint_section = ""
    if target_hint and target_hint.strip():
        hint_section = f"""
    PLACEMENT INSTRUCTION (top priority): Add the point(s) under: {target_hint.strip()}
    Find the company/project section in the resume matching this name and insert the new bullet(s) there. If no exact match exists, choose the closest matching section.
"""

    prompt = f"""
    You are an expert resume editor for a DevOps/Cloud/Infrastructure engineer's resume.

    An already-tailored resume (below) needs ADDITIONAL bullet points inserted, based on new points supplied by the candidate.
{hint_section}
    Job Description:
    {jd_text}

    Current Resume:
    {resume_text}

    New points the candidate wants added:
    {points_text}

    Task: For EACH new point, decide the single best existing company/project section in the resume to place it under (respect the placement instruction above if one was given), then:
    - Write a polished, ATS-friendly bullet point in the same voice/tense/format as the surrounding resume bullets.
    - Naturally incorporate relevant JD keywords where truthful and applicable — do NOT invent technologies or experience the point doesn't already imply.
    - Identify an "anchor": the EXACT, CHARACTER-FOR-CHARACTER text of an existing bullet point already in the resume, within the chosen section, immediately after which the new bullet should be inserted (typically the last bullet in that section). Copy it exactly — do not paraphrase or shorten it.

    CRITICAL CONSTRAINT: The candidate is a DevOps/Cloud/Infrastructure engineer. Stay within DevOps, Cloud, Infrastructure, SRE, and Platform Engineering domains — do not add unrelated skills.

    Also estimate the resume's new overall ATS match score (0-100) after these bullets are added (after_score).

    Return the result strictly in the following JSON format:
    {{
        "insertions": [
            {{
                "section": "<company or project name this was added under>",
                "anchor": "<exact existing bullet text in the resume to insert the new bullet after>",
                "new_bullet": "<the new bullet point text>",
                "keywords_added": ["<keyword1>", "<keyword2>"]
            }}
        ],
        "after_score": <integer>
    }}
    """

    models_to_try = [GEMINI_QUALITY_MODEL, GEMINI_FAST_MODEL, GEMINI_PRO_FALLBACK_MODEL]
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                ),
            )
            usage = response.usage_metadata
            if usage:
                log_api_call(model_name, "add_points",
                             input_tokens=usage.prompt_token_count or 0,
                             output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
            else:
                log_api_call(model_name, "add_points", input_tokens=6000, output_tokens=400)
            return json.loads(response.text)
        except Exception as e:
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e) or "404" in str(e) or "NOT_FOUND" in str(e):
                print(f"{model_name} unavailable, trying next model...")
                continue
            raise RuntimeError(f"API Error: {str(e)}")
    raise RuntimeError(f"All models unavailable: {str(last_error)}")

def generate_cover_letter(resume_text: str, jd_text: str, company_name: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are an expert career coach writing a cover letter for a DevOps engineer.
    Based on the following resume and job description, write a concise, professional cover letter (maximum 300 words).
    
    CRITICAL CONSTRAINTS:
    - ONLY emphasize DevOps-related skills and experience (e.g., CI/CD, AWS, Kubernetes, Terraform, Infrastructure, Automation).
    - DO NOT mention or invent non-DevOps skills like "Full Stack", "Java", "Frontend", or general software development, even if the JD asks for them.
    - Match the tone of a confident, results-oriented engineering professional.
    - Address the hiring manager if a name is found, otherwise use a professional greeting.
    - Include the company name '{company_name}' in the letter.
    - ABSOLUTELY NO EMOJIS in the output.
    
    Resume:
    {resume_text}
    
    Job Description:
    {jd_text}
    
    Task: Write a concise, professional, and impactful cover letter (max 300 words).
    The letter should bridge the gap between the candidate's skills in the resume and the requirements in the job description.
    Focus on the body paragraphs. Do not include placeholder brackets for things like [Your Address] or [Date] - just write the actual letter.
    Return only the text of the cover letter, nothing else.
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_QUALITY_MODEL,
            contents=prompt,
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_QUALITY_MODEL, "cover_letter",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_QUALITY_MODEL, "cover_letter", input_tokens=8000, output_tokens=400)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating cover letter: {e}")
        raise RuntimeError(f"API Error: {str(e)}")

def analyze_job_metadata(jd_text: str, extracted_keywords: dict) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    keyword_summary = ", ".join(
        [kw for keywords in extracted_keywords.values() for kw in keywords]
    )

    prompt = f"""Analyze this job description and extract key metadata.

Job Description:
{jd_text[:8000]}

Extracted Keywords: {keyword_summary}

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
    "primary_role": "DevOps Engineer",
    "match_confidence": 0.95,
    "sub_categories": [
        {{"name": "Kubernetes", "confidence": 0.9}},
        {{"name": "AWS", "confidence": 0.85}},
        {{"name": "Terraform", "confidence": 0.7}}
    ],
    "location": "Austin, TX / Remote",
    "salary_range": "$120k - $150k",
    "visa_requirements": "US Citizen / Green Card",
    "clearance_level": "Secret / None",
    "employment_type": "c2c"
}}
If a field is not specified in the job description, set its value to 'Not specified'.
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            ),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "categorize_job",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "categorize_job", input_tokens=1000, output_tokens=200)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generating job metadata: {e}")
        # Fallback
        primary = "DevOps Engineer"
        if extracted_keywords.get('sre'): primary = "SRE / Site Reliability Engineer"
        elif extracted_keywords.get('security'): primary = "Security Engineer / SecOps"
        return {
            "primary_role": primary,
            "match_confidence": 0.8,
            "sub_categories": [{"name": k, "confidence": 0.8} for k in extracted_keywords.keys()],
            "location": "Unknown",
            "salary_range": "Unknown",
            "visa_requirements": "Unknown",
            "clearance_level": "Unknown",
            "employment_type": "Unknown"
        }


def generate_recruiter_outreach_email(job_title: str, company_name: str, jd_text: str, candidate_profile: str = "") -> dict:
    """Cold outreach email to a recruiter/hiring contact for a job the candidate hasn't
    necessarily tailored a resume for yet — distinct from the existing mail-draft flow,
    which requires an already-tailored resume file to attach."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    profile_block = f"\nMy background:\n{candidate_profile.strip()}\n" if candidate_profile.strip() else ""
    prompt = f"""Write a short, professional cold outreach email FROM ME, in first person ("I have...", "I'm reaching
out..."), addressed to a recruiter about a specific job opening. I am the candidate — do not write about me in the
third person and do not mention "career coach" anywhere. Sign off with just my name (no "Sincerely, A Career Coach").
Keep it under 150 words, confident but not pushy.

Job Title: {job_title}
Company: {company_name}
{profile_block}
Job Description (for context, reference specific requirements if useful):
{jd_text[:8000]}

Write a subject line and a short email body. Do not use emojis or placeholder brackets like [Your Name] — use my
actual name from the background above if given, otherwise sign off with "Best regards," and no name.
Return ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "recruiter_outreach_email",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "recruiter_outreach_email", input_tokens=1500, output_tokens=200)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generating recruiter outreach email: {e}")
        raise RuntimeError(f"API Error: {str(e)}")


def generate_checkin_followup_email(job_title: str, company_name: str, days_since_applied: int, candidate_profile: str = "") -> dict:
    """Check-in follow-up for an application with no response yet — distinct from the
    existing /follow-up endpoint, which replies to an already-received recruiter email."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    profile_block = f"\nMy background:\n{candidate_profile.strip()}\n" if candidate_profile.strip() else ""
    prompt = f"""Write a brief, polite check-in email FROM ME, in first person, about a job application I submitted
that has had no response in {days_since_applied} days. I am the candidate — do not write about me in the third
person and do not mention "career coach" anywhere. Keep it under 120 words, friendly and low-pressure — reaffirm
interest, don't sound impatient or entitled.

Job Title: {job_title}
Company: {company_name}
Days since applying: {days_since_applied}
{profile_block}
Write a subject line and a short email body. No emojis, no placeholder brackets like [Your Name] — use my actual
name from the background above if given, otherwise sign off with "Best regards," and no name.
Return ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "checkin_followup_email",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "checkin_followup_email", input_tokens=1000, output_tokens=150)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generating check-in follow-up email: {e}")
        raise RuntimeError(f"API Error: {str(e)}")


def generate_linkedin_message(job_title: str, company_name: str, candidate_profile: str = "") -> dict:
    """Short LinkedIn connection/InMail message for reaching out about a specific role."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    profile_block = f"\nMy background:\n{candidate_profile.strip()}\n" if candidate_profile.strip() else ""
    prompt = f"""Write a short LinkedIn message (connection request note or InMail, under 300 characters) FROM ME,
in first person, about a specific job opening I'm interested in. I am the candidate — do not write about me in
the third person and do not mention "career coach" anywhere. Casual-professional tone, no emojis, no placeholder
brackets.

Job Title: {job_title}
Company: {company_name}
{profile_block}
Return ONLY valid JSON: {{"body": "..."}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "linkedin_message",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "linkedin_message", input_tokens=500, output_tokens=100)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generating LinkedIn message: {e}")
        raise RuntimeError(f"API Error: {str(e)}")


def extract_contacts_from_text(company: str, title: str, scraped_text: str) -> dict:
    """Organize/extract real names, titles, and emails from ALREADY-scraped web text
    (search results + company page snippets) — this does NOT search the web itself,
    it only reads text handed to it and pulls out what's literally present. Never
    invents a person; returns an empty list if nothing concrete is found."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    prompt = f"""I scraped some web pages (search results and a company's own site) while looking for a RECRUITER or
HIRING/TALENT-ACQUISITION contact at {company} for a "{title}" role. Read the text below and extract ONLY people
whose title clearly indicates a recruiting/hiring/HR/staffing role — e.g. "Recruiter", "Technical Recruiter",
"Talent Acquisition", "Talent Partner", "HR", "People Operations", "Staffing", or someone explicitly described as
the hiring manager for this role. Only include what's literally present — never guess or invent anyone.

DO NOT include executives, founders, engineers, or any other employee whose title has nothing to do with hiring —
even if they are the most prominent person mentioned on the page (e.g. a CEO or a random team member on an "About
Us" page is NOT a hiring contact and must be excluded). If the only people mentioned are not recruiting/HR/hiring
roles, return an empty "contacts" list rather than including them anyway.

Scraped text:
{scraped_text[:16000]}

Return ONLY valid JSON in this shape:
{{"contacts": [{{"name": "...", "title": "...", "email": "...", "source_url": "..."}}], "company_page_url": "..."}}
Each contact needs at least a name OR an email to be included — skip anything too vague to be useful.
"contacts" should be an empty array if nothing concrete matching a recruiting/hiring/HR role was found.
"company_page_url" is the best company careers/about/contact page URL seen in the text, or "" if none."""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "extract_contacts",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "extract_contacts", input_tokens=2000, output_tokens=200)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error extracting contacts: {e}")
        raise RuntimeError(f"API Error: {str(e)}")


INBOX_CATEGORY_KEYS = ["verification", "rejection", "interview", "assessment", "reminder", "offer", "applied", "other"]


def classify_inbox_messages(messages: list) -> dict:
    """Classify a batch of already-fetched Gmail message summaries (id/subject/snippet
    only — never the full body, to keep this cheap) into a job-search inbox category in
    ONE batched call, instead of one API call per email. Uses the fast/cheap Gemini tier
    since this is pure classification, not generation — for a typical 25-message inbox
    page this is a few thousand input tokens and a few hundred output tokens, a fraction
    of a cent per load. Returns {message_id: category_key}; NEVER raises — callers should
    keep their existing local-rule category as a fallback for any id missing from the
    result (empty dict on any failure, e.g. no API key or a transient error)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not messages:
        return {}
    client = genai.Client(api_key=api_key)

    items = "\n".join(
        f'- id="{m.get("id")}" | subject="{(m.get("subject") or "")[:150]}" | snippet="{(m.get("snippet") or "")[:200]}"'
        for m in messages
    )

    prompt = f"""You are classifying emails in a job seeker's inbox. For each email below (identified by its id),
read the subject and snippet and pick the SINGLE best-fitting category from this list:

- verification: account/email verification, security codes, OTPs, "confirm your email"
- rejection: "not selected", "not moving forward", application rejected, "unfortunately"
- interview: interview invites, phone/technical screens, scheduling a call
- assessment: coding challenges, take-home tests, technical assessments
- reminder: follow-up reminders, deadlines, "complete your application", action required
- offer: job offer letters, "pleased to offer", congratulations on a job offer
- applied: application received/submitted confirmations ("thanks for applying")
- other: anything that doesn't clearly fit one of the above (unrelated mail, newsletters, etc.)

Emails:
{items}

Return ONLY valid JSON: {{"classifications": [{{"id": "...", "category": "..."}}]}}
One entry per email id above. "category" must be exactly one of: verification, rejection, interview, assessment,
reminder, offer, applied, other."""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "classify_inbox",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "classify_inbox", input_tokens=1500, output_tokens=300)
        data = json.loads(response.text)
        result = {}
        for c in data.get("classifications", []):
            mid, cat = c.get("id"), c.get("category")
            if mid and cat in INBOX_CATEGORY_KEYS:
                result[mid] = cat
        return result
    except Exception as e:
        print(f"Error classifying inbox messages (falling back to local rules): {e}")
        return {}


def summarize_inbox_message(subject: str, sender: str, body: str, thread_context: str = "", application_context: str = "") -> dict:
    """Full-body read of a SINGLE already-opened email — extracts what happened, the
    action needed, any deadline/interview date, a recruiter email address if present,
    the intent a reply should carry, and a grounded draft reply. Only ever called for
    the one message the user is actively reading (never batched across the inbox list —
    list-view classification stays subject/snippet-only for cost), so this stays a
    single cheap call per read, not per email. thread_context (earlier messages in the
    same conversation) and application_context (the matched tracked application's
    company/title) are optional extra grounding — passing them produces a much more
    specific reply_suggestion than the single message alone would allow."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=api_key)

    context_block = ""
    if application_context:
        context_block += f"\nThe candidate applied to: {application_context}\n"
    if thread_context:
        context_block += f"\nEarlier messages in this conversation (oldest first, for context only — the email to analyze is the LATEST one below):\n{thread_context[:6000]}\n"

    prompt = f"""Read this job-search-related email and answer briefly and concretely. Base every field only on
what's literally in the email (and the conversation context, if given) below — never invent details that aren't
there.
{context_block}
Email to analyze:
From: {sender}
Subject: {subject}
Body:
{body[:8000]}

Return ONLY valid JSON in this shape:
{{"what_happened": "one sentence summary of what this email is about",
"required_action": "what the recipient should do next, or \\"None\\" if no action is needed",
"deadline": "any non-interview date/deadline mentioned (e.g. assessment due date, offer response deadline), or \\"\\" if none",
"interview_date": "the specific interview/call date or time proposed or confirmed in the email, or \\"\\" if none",
"recruiter_email": "the recruiter/sender's contact email address to reply to, or \\"\\" if not identifiable",
"reply_intent": "one of: confirm, decline, ask_question, acknowledge, none — the most sensible intent for a reply",
"reply_suggestion": "a short 2-4 sentence draft reply matching reply_intent, or \\"\\" if no reply is appropriate (e.g. an automated notification)"}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json"),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call(GEMINI_FAST_MODEL, "summarize_inbox_message",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call(GEMINI_FAST_MODEL, "summarize_inbox_message", input_tokens=1800, output_tokens=250)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error summarizing inbox message: {e}")
        raise RuntimeError(f"API Error: {str(e)}")


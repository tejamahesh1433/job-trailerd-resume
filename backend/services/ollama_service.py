import os
import re
import json
from openai import OpenAI
from services.usage_tracker import log_api_call

SIGNATURE = (
    "\n\nThank you for your time and consideration. "
    "I look forward to hearing from you.\n\n"
    "Best Regards,\n\n"
    "Teja Mahesh Neerukonda\n"
    "352-721-6698\n"
    "tejamahesh33333@gmail.com\n"
    "linkedin.com/in/teja-mahesh-neerukonda-0b9363207"
)


_COMPANY_SUFFIXES = re.compile(
    r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Pvt|Private|Limited|Group|'
    r'Consulting|Solutions|Technologies|Services|Staffing|Systems)\b', re.IGNORECASE
)
_ROLE_KEYWORDS = re.compile(
    r'\b(Recruiter|Talent|Acquisition|HR|Manager|Director|Lead|Coordinator|Staffing)\b', re.IGNORECASE
)

def _extract_recruiter_name(jd_text: str) -> str:
    """Extract the recruiter/hiring manager name from the JD signature block."""
    lines = jd_text.strip().split('\n')

    greeting_patterns = ['best regards', 'regards', 'thanks', 'sincerely',
                         'thank you', 'cheers', 'warm regards', 'kind regards']
    for i, line in enumerate(lines):
        if line.strip().lower().rstrip(',') in greeting_patterns:
            for j in range(i + 1, min(i + 6, len(lines))):
                candidate = lines[j].strip().rstrip(',')
                if not candidate:
                    continue
                # Skip lines that are clearly not names
                if candidate.startswith(('http', 'www', 'Email', 'Web', 'Phone', 'Tel',
                                         'Address', 'Global', 'USA', 'India', '+1', '--')):
                    continue
                # Skip company names (contain Inc, LLC, etc.)
                if _COMPANY_SUFFIXES.search(candidate):
                    continue
                # Skip role/title lines
                if _ROLE_KEYWORDS.search(candidate):
                    continue
                # A person's name: 2-4 words, each starting with uppercase (allow single initials like "J")
                if re.match(r'^[A-Z][a-z]*(?:\s+[A-Z][a-z]*){0,3}$', candidate):
                    # Return first name (skip single-letter initials)
                    parts = candidate.split()
                    for part in parts:
                        if len(part) > 1:
                            return part
                    return parts[0]
            break

    # Fallback: extract from email prefix like shanmukhj@ -> Shanmukh
    email_match = re.search(r'([\w.+-]+)@[\w-]+\.\w{2,}', jd_text)
    if email_match:
        prefix = email_match.group(1)
        parts = re.split(r'[._]', prefix)
        for part in parts:
            if len(part) > 2 and part.isalpha():
                return part.title()

    return ""


def _extract_job_title(jd_text: str) -> str:
    """Extract the job title from the JD."""
    lines = jd_text.strip().split('\n')

    for line in lines[:10]:
        line = line.strip()
        m = re.match(r'(?:job\s*title|position|role)\s*[:\-]\s*(.+)', line, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            title = re.split(r'\s+(?:must|should|need|require|with\s+\d)', title, flags=re.IGNORECASE)[0].strip()
            return title
        if 5 < len(line) < 80 and not line.endswith(':') and re.search(r'engineer|developer|architect|manager|analyst|admin|specialist|lead|devops|sre|cloud|platform', line, re.IGNORECASE):
            title = re.sub(r'^(?:job\s*title\s*[:\-]\s*)', '', line, flags=re.IGNORECASE).strip()
            title = re.split(r'\s+(?:must|should|need|require|with\s+\d)', title, flags=re.IGNORECASE)[0].strip()
            return title

    return "DevOps Engineer"


def generate_mail_draft(resume_text: str, jd_text: str, cover_letter_text: str, company_name: str, profile_text: str = "") -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    recruiter_name = _extract_recruiter_name(jd_text)
    job_title = _extract_job_title(jd_text)
    greeting = f"Hi {recruiter_name}," if recruiter_name else "Hi there,"

    context_parts = [
        f"FULL RESUME:\n{resume_text.strip()}",
        f"FULL JOB DESCRIPTION:\n{jd_text.strip()}",
    ]
    if cover_letter_text and cover_letter_text.strip():
        context_parts.append(f"COVER LETTER:\n{cover_letter_text.strip()}")
    if profile_text:
        context_parts.append(f"CANDIDATE PROFILE (personal details to naturally weave in if relevant to the JD):\n{profile_text}")

    context = "\n\n---\n\n".join(context_parts)

    profile_instruction = ""
    if profile_text:
        profile_instruction = (
            "- The CANDIDATE PROFILE contains personal facts (work authorization, location, availability, etc.). "
            "If the JD mentions location, visa sponsorship, or relocation — naturally mention the relevant fact from the profile. "
            "Do NOT list all profile facts — only include what is relevant to this specific JD.\n"
        )

    prompt = (
        f"Read ALL the documents below carefully (resume, JD, cover letter, profile), then write a job application email to {company_name} for the role: {job_title}.\n\n"
        f"{context}\n\n"
        "---\n\n"
        "Instructions:\n"
        f"- Start the body with EXACTLY: '{greeting}\\n\\nI hope you are doing well.'\n"
        f"- State interest in the '{job_title}' position\n"
        "- READ the entire resume to find: total years of experience, key skills, specific tools used, and measurable achievements\n"
        "- READ the entire JD to find: key requirements, technologies mentioned, and what they're looking for\n"
        "- If a cover letter is provided, match its tone and key points\n"
        f"{profile_instruction}"
        "- Mention total years of experience and 4-5 key skills that MATCH between the resume and JD\n"
        "- One sentence about specific background: tools used, platforms operated at scale, automation built — use REAL details from the resume\n"
        "- End with: 'I have attached my resume for your review. Please let me know if you need any additional information.'\n"
        "- Keep the body 80-120 words, simple and professional\n"
        "- NEVER use 'Dear' or 'Dear Hiring Manager'\n"
        "- Do NOT use placeholder brackets like [Your Name] or [Company]\n"
        "- Do NOT mention the company name anywhere in the email body\n"
        "- ABSOLUTELY NO EMOJIS in the output\n\n"
        "Reply with ONLY valid JSON:\n"
        '{"subject": "Application for ' + job_title + '", "body": "<email body without signature>"}'
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        usage = response.usage
        if usage:
            log_api_call("gpt-4o-mini", "mail_draft",
                         input_tokens=usage.prompt_tokens or 0,
                         output_tokens=usage.completion_tokens or 0)
        else:
            log_api_call("gpt-4o-mini", "mail_draft", input_tokens=5000, output_tokens=200)

        result['body'] = result.get('body', '').rstrip() + SIGNATURE
        return result

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse response: {e}")
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {str(e)}")


def generate_follow_up(resume_text: str, jd_text: str, company_name: str, received_email: str, original_mail_body: str = "", profile_text: str = "") -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    recruiter_name = _extract_recruiter_name(received_email) or _extract_recruiter_name(jd_text)
    job_title = _extract_job_title(jd_text)
    greeting = f"Hi {recruiter_name}," if recruiter_name else "Hi there,"

    context_parts = [
        f"RECEIVED EMAIL FROM COMPANY:\n{received_email.strip()}",
        f"FULL JOB DESCRIPTION:\n{jd_text.strip()}",
        f"FULL RESUME:\n{resume_text.strip()}",
    ]
    if original_mail_body:
        context_parts.append(f"MY ORIGINAL APPLICATION EMAIL:\n{original_mail_body.strip()}")
    if profile_text:
        context_parts.append(f"CANDIDATE PROFILE:\n{profile_text}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"Read ALL the documents below, then write a follow-up reply to the email received from {company_name} regarding the '{job_title}' position.\n\n"
        f"{context}\n\n"
        "---\n\n"
        "Instructions:\n"
        f"- Start with EXACTLY: '{greeting}'\n"
        "- READ the received email carefully. Understand what they are asking or saying.\n"
        "- If they are asking for availability — provide it enthusiastically\n"
        "- If they are asking for more info — provide relevant details from the resume\n"
        "- If they are scheduling an interview — confirm eagerly with flexibility\n"
        "- If they are rejecting — thank them gracefully and express interest in future opportunities\n"
        "- If it's a general follow-up — express continued interest and ask about next steps\n"
        "- Reference specific details from the original application/resume that are relevant\n"
        "- Keep the body 60-100 words, professional and enthusiastic\n"
        "- NEVER use 'Dear' or 'Dear Hiring Manager'\n"
        "- Do NOT use placeholder brackets like [Your Name] or [Company]\n"
        "- Do NOT mention the company name anywhere in the email body\n"
        "- ABSOLUTELY NO EMOJIS in the output\n\n"
        "Reply with ONLY valid JSON:\n"
        '{"subject": "Re: <appropriate subject>", "body": "<email body without signature>"}'
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        usage = response.usage
        if usage:
            log_api_call("gpt-4o-mini", "follow_up",
                         input_tokens=usage.prompt_tokens or 0,
                         output_tokens=usage.completion_tokens or 0)
        else:
            log_api_call("gpt-4o-mini", "follow_up", input_tokens=5000, output_tokens=200)

        result['body'] = result.get('body', '').rstrip() + SIGNATURE
        return result

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse response: {e}")
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {str(e)}")

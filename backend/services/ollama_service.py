import os
import re
import json
import requests

OLLAMA_BASE = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SIGNATURE = (
    "\n\nThank you for your time and consideration.\n\n"
    "Best Regards,\n\n"
    "Teja Mahesh Neerukonda\n"
    "(352) 721-6698\n"
    "tejamahesh33333@gmail.com\n"
    "linkedin.com/in/teja-mahesh-neerukonda-0b9363207"
)

_EXP_HEADERS = re.compile(
    r'(?:^|\n)((?:professional\s+)?experience|work\s+(?:history|experience)|employment(?:\s+history)?)',
    re.IGNORECASE,
)

def _smart_resume_excerpt(text: str, budget: int = 4000) -> str:
    """Return up to `budget` chars, prioritising the candidate header + experience section."""
    header = text[:350]  # always keep name / contact / summary top
    m = _EXP_HEADERS.search(text)
    if m:
        exp_body = text[m.start():]
        combined = header.rstrip() + "\n\n" + exp_body
        return combined[:budget].strip()
    return text[:budget].strip()


def generate_mail_draft(resume_text: str, jd_info_text: str, cover_letter_text: str, company_name: str) -> dict:
    resume_excerpt  = _smart_resume_excerpt(resume_text, budget=4000)
    jd_excerpt      = jd_info_text[:900].strip()
    cl_excerpt      = cover_letter_text[:400].strip() if cover_letter_text.strip() else ""

    context_parts = [
        f"RESUME (experience & skills):\n{resume_excerpt}",
        f"JOB DESCRIPTION SUMMARY:\n{jd_excerpt}",
    ]
    if cl_excerpt:
        context_parts.append(f"COVER LETTER TONE REFERENCE:\n{cl_excerpt}")

    context = "\n\n".join(context_parts)

    prompt = (
        f"Write a professional DevOps job application email to {company_name}.\n\n"
        f"{context}\n\n"
        "Instructions:\n"
        "- 180-220 words in the body (not counting the closing line)\n"
        "- Mention 2-3 specific experiences, job titles, or measurable achievements from the resume\n"
        "- Focus on DevOps skills: CI/CD, AWS, Kubernetes, Terraform, Infrastructure, Automation\n"
        "- Use the candidate's real full name from the resume header\n"
        "- End the body with exactly this sentence: Please find my resume attached for your review.\n"
        "- Do NOT use placeholder brackets like [Your Name] or [Company]\n\n"
        "Reply with ONLY valid JSON, no markdown, no explanation:\n"
        '{"subject": "Application for DevOps Engineer – Teja Mahesh Neerukonda", "body": "<full email body>"}'
    )

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_ctx": 8192, "temperature": 0.4},
            },
            timeout=240,
        )

        if not resp.ok:
            try:
                err = resp.json().get("error", resp.text[:300])
            except Exception:
                err = resp.text[:300]
            raise RuntimeError(f"Ollama {resp.status_code}: {err}")

        raw = resp.json().get("message", {}).get("content", "").strip()

        # Strip markdown code fences some models add despite instructions
        if "```" in raw:
            for part in raw.split("```"):
                cleaned = part.lstrip("json\n").strip()
                if cleaned.startswith("{"):
                    raw = cleaned
                    break

        def _attach_signature(data: dict) -> dict:
            data['body'] = data.get('body', '').rstrip() + SIGNATURE
            return data

        try:
            return _attach_signature(json.loads(raw))
        except json.JSONDecodeError:
            pass

        start = raw.find('{')
        end   = raw.rfind('}') + 1
        if start >= 0 and end > start:
            return _attach_signature(json.loads(raw[start:end]))

        raise ValueError(f"No JSON found in response: {raw[:200]}")

    except requests.exceptions.ConnectionError:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama timed out — model may be loading. Try again in a moment.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Ollama error: {str(e)}")

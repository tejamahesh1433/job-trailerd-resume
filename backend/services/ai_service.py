import os
from google import genai
from google.genai import types
import json
from services.usage_tracker import log_api_call

def analyze_resume(resume_text: str, jd_text: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are an expert ATS (Applicant Tracking System) scanner and career coach specializing in DevOps engineering roles.

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
    Task 3: ALWAYS identify up to 5 bullet points in the resume to rewrite to better match the JD, regardless of the score. Even if the score is high, there are always improvements to make. Provide the exact original text and the new tailored text. "original" MUST be the EXACT, CHARACTER-FOR-CHARACTER literal text found in the resume — copy-paste it exactly, including all punctuation and spacing. Do NOT paraphrase or shorten the original.
    Task 4: Estimate the new ATS score (0-100) after these replacements are applied (after_score). If no replacements, after_score equals the original score.
    Task 5: Identify up to 10 keywords from the JD that are missing from the resume.
    Task 6: Break down the original score into 4 section scores (0-100): "Skills", "Experience", "Education", "Summary".
    Task 7: Extract the candidate's contact info from the resume: full name, email address, and phone number. Return null for any field not found.

    CRITICAL CONSTRAINT ON REPLACEMENTS:
    - This is a DevOps resume. ONLY emphasize DevOps-related skills (CI/CD, AWS, Kubernetes, Terraform, Infrastructure, Automation).
    - DO NOT add, invent, or emphasize non-DevOps skills like "Full Stack", "Java", "Frontend", or general application development, even if the JD explicitly asks for them.
    - NEVER hallucinate experiences. Only reword existing bullet points to highlight the candidate's DevOps capabilities.

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
                "new": "<new tailored string>"
            }}
        ]
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            ),
        )
        usage = response.usage_metadata
        if usage:
            log_api_call("gemini-2.5-pro", "scan_resume",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call("gemini-2.5-pro", "scan_resume", input_tokens=8000, output_tokens=500)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error during AI analysis: {e}")
        raise RuntimeError(f"API Error: {str(e)}")

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
            model='gemini-2.5-pro',
            contents=prompt,
        )
        usage = response.usage_metadata
        if usage:
            log_api_call("gemini-2.5-pro", "cover_letter",
                         input_tokens=usage.prompt_token_count or 0,
                         output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
        else:
            log_api_call("gemini-2.5-pro", "cover_letter", input_tokens=8000, output_tokens=400)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating cover letter: {e}")
        raise RuntimeError(f"API Error: {str(e)}")

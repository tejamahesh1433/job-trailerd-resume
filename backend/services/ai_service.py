import os
from google import genai
from google.genai import types
import json

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
    Task 2: Extract the Company Name from the Job Description. If not found, return "Unknown_Company".
    Task 3: If the score is below 85, identify up to 5 bullet points in the resume to rewrite to better match the JD. Provide the exact original text and the new tailored text. "original" MUST be the exact literal text found in the resume.
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
            model='gemini-flash-latest',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            ),
        )
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
            model='gemini-flash-latest',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error generating cover letter: {e}")
        raise RuntimeError(f"API Error: {str(e)}")

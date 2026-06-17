import os
import io
import base64
import json
import pdfplumber
from google import genai
from google.genai import types
from services.docx_service import extract_text_from_docx
from services.usage_tracker import log_api_call

DATA_DIR = os.getenv("DATA_DIR", "data")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.txt")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF locally — no AI needed."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text.strip())
    return '\n'.join(text_parts)


def _extract_pdf_with_vision(file_bytes: bytes) -> str:
    """Extract text from scanned/image-based PDF using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type='application/pdf'),
            "Extract ALL text visible in this PDF document. Return only the raw text, nothing else.",
        ],
        config=types.GenerateContentConfig(temperature=0.1),
    )
    usage = response.usage_metadata
    if usage:
        log_api_call("gemini-2.5-flash", "profile_pdf_ocr",
                     input_tokens=usage.prompt_token_count or 0,
                     output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
    else:
        log_api_call("gemini-2.5-flash", "profile_pdf_ocr", input_tokens=2000, output_tokens=500)
    return response.text.strip()


def extract_text_from_image(file_bytes: bytes, filename: str) -> str:
    """Extract text from image using Gemini vision."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    ext = filename.lower().rsplit('.', 1)[-1]
    mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                'webp': 'image/webp', 'gif': 'image/gif', 'bmp': 'image/bmp'}
    mime_type = mime_map.get(ext, 'image/jpeg')

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            "Extract ALL text visible in this document/image. Return only the raw text, nothing else.",
        ],
        config=types.GenerateContentConfig(temperature=0.1),
    )
    usage = response.usage_metadata
    if usage:
        log_api_call("gemini-2.5-flash", "profile_image_ocr",
                     input_tokens=usage.prompt_token_count or 0,
                     output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
    else:
        log_api_call("gemini-2.5-flash", "profile_image_ocr", input_tokens=2000, output_tokens=500)
    return response.text.strip()


def extract_profile_facts(raw_text: str, doc_type: str = "document") -> str:
    """Use Gemini to extract only job-application-relevant facts from raw text."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    prompt = f"""Extract ONLY job-application-relevant facts from this {doc_type}.

Raw text:
{raw_text}

Extract these categories if found (skip any not present):
- Full Legal Name
- Work Authorization Status (e.g., US Citizen, Green Card holder, H1B, etc.)
- Location / State / City
- Availability / Notice Period
- Willing to Relocate (Yes/No)
- Any certifications or licenses relevant to employment

Return ONLY the extracted facts as simple "Key: Value" lines.
Do NOT include sensitive numbers like SSN, DL number, card numbers, or dates of birth.
Do NOT include any raw document identifiers or government ID numbers.
If no relevant facts found, return "No relevant facts found."
"""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1),
    )
    usage = response.usage_metadata
    if usage:
        log_api_call("gemini-2.5-flash", "profile_extract_facts",
                     input_tokens=usage.prompt_token_count or 0,
                     output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
    else:
        log_api_call("gemini-2.5-flash", "profile_extract_facts", input_tokens=1000, output_tokens=200)
    return response.text.strip()


def process_uploaded_doc(file_bytes: bytes, filename: str) -> dict:
    """Process an uploaded personal document: extract text, then extract facts."""
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''

    # Step 1: Extract raw text based on file type
    raw_text = ""
    if ext == 'docx':
        raw_text = extract_text_from_docx(file_bytes)
    elif ext == 'pdf':
        # Try local text extraction first
        raw_text = extract_text_from_pdf(file_bytes)
        # If PDF is scanned/image-based, fall back to Gemini vision
        if not raw_text or len(raw_text.strip()) < 10:
            raw_text = _extract_pdf_with_vision(file_bytes)
    elif ext in ('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'):
        raw_text = extract_text_from_image(file_bytes, filename)
    else:
        raise ValueError(f"Unsupported file type: .{ext}. Use PDF, DOCX, or image files.")

    if not raw_text or len(raw_text.strip()) < 10:
        raise ValueError("Could not extract text from the uploaded file.")

    # Step 2: Extract only job-relevant facts (strips sensitive data)
    doc_type = "driver's license / ID" if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp') else "document"
    facts = extract_profile_facts(raw_text, doc_type)

    if "no relevant facts" in facts.lower():
        return {"facts": "", "message": "No job-relevant facts found in this document."}

    # Step 3: Merge with existing profile
    existing_profile = ""
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            existing_profile = f.read().strip()

    # Merge: add new facts, avoid duplicates
    existing_lines = set(line.strip().lower() for line in existing_profile.split('\n') if line.strip())
    new_lines = []
    for line in facts.split('\n'):
        line = line.strip()
        if line and line.lower() not in existing_lines:
            # Check if same key already exists (e.g., "Location: X" vs "Location: Y")
            key = line.split(':')[0].strip().lower() if ':' in line else ''
            existing_keys = {l.split(':')[0].strip().lower() for l in existing_profile.split('\n') if ':' in l}
            if key and key in existing_keys:
                # Update existing key with new value
                updated_lines = []
                for el in existing_profile.split('\n'):
                    if ':' in el and el.split(':')[0].strip().lower() == key:
                        updated_lines.append(line)
                    else:
                        updated_lines.append(el)
                existing_profile = '\n'.join(updated_lines)
            else:
                new_lines.append(line)

    if new_lines:
        merged = existing_profile + '\n' + '\n'.join(new_lines) if existing_profile else '\n'.join(new_lines)
    else:
        merged = existing_profile

    merged = merged.strip()

    # Save merged profile
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(merged + '\n')

    return {
        "facts": facts,
        "profile": merged,
        "message": f"Extracted facts from {filename} and merged into profile.",
    }

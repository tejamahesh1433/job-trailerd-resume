"""Central place for Gemini model selection so call sites never hardcode model names.

GEMINI_QUALITY_MODEL — resume ATS analysis/tailoring, cover letters, job description
    cleanup: tasks where output quality directly affects what gets sent to an employer.
GEMINI_FAST_MODEL — drafts, extraction, metadata categorization, contact parsing: cheap,
    high-volume, low-judgment tasks.
GEMINI_PRO_FALLBACK_MODEL — last-resort fallback only, never the default. Pro-tier calls
    cost ~8x more than Flash, so it only gets used if both Flash-tier models are unavailable.
"""

GEMINI_QUALITY_MODEL = "gemini-flash-latest"
GEMINI_FAST_MODEL = "gemini-flash-lite-latest"
GEMINI_PRO_FALLBACK_MODEL = "gemini-pro-latest"

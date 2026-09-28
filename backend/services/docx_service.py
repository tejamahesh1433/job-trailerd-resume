import docx
from io import BytesIO
import difflib
import copy
import re
from docx.text.paragraph import Paragraph

def extract_title_lines(resume_text: str) -> dict:
    """Deterministically locate the resume's headline line (directly beneath the
    candidate's name) and each of the two most recent employers' 'Role:' lines,
    from the already-extracted resume text (see extract_text_from_docx). Handing
    these literal strings back to the AI prompt — instead of asking it to find
    them itself — avoids it confusing the headline with the Professional
    Summary's opening sentence, which shares similar wording."""
    lines = [l.strip() for l in resume_text.split('\n') if l.strip()]

    headline = None
    if len(lines) > 1:
        candidate = lines[1]
        looks_like_contact_line = '@' in candidate or sum(c.isdigit() for c in candidate) >= 3
        if not looks_like_contact_line and len(candidate) <= 80 and not candidate.endswith('.'):
            headline = candidate

    role_lines = [l for l in lines if re.match(r'^Role\s*:', l, re.IGNORECASE)]

    return {
        "headline": headline,
        "role_lines": role_lines[:2],
    }

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = docx.Document(BytesIO(file_bytes))
    full_text = []

    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text.strip())

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        full_text.append(para.text.strip())

    return '\n'.join(full_text)

def _normalize(text: str) -> str:
    """Normalize whitespace for comparison."""
    return ' '.join(text.split())

def _find_best_paragraph_match(paragraphs, original_text):
    """Find the paragraph that best matches the original text using fuzzy matching."""
    norm_original = _normalize(original_text)
    best_para = None
    best_ratio = 0.0

    for para in paragraphs:
        para_text = para.text.strip()
        if not para_text:
            continue

        # Exact match
        if original_text in para_text:
            return para, original_text

        # Normalized exact match
        norm_para = _normalize(para_text)
        if norm_original in norm_para:
            return para, original_text

        # Fuzzy match — the paragraph text should contain something very similar
        ratio = difflib.SequenceMatcher(None, norm_original, norm_para).ratio()
        if ratio > best_ratio and ratio >= 0.75:
            best_ratio = ratio
            best_para = para

        # Also check if original is a substantial substring match
        if len(norm_original) > 20:
            # Try matching the first 60 chars as anchor
            anchor = norm_original[:60]
            if anchor in norm_para:
                return para, original_text

    return best_para, original_text

def replace_text_in_paragraph(paragraph, original_text, new_text):
    """Exact/normalized match ONLY — no fuzzy fallback here. create_tailored_docx's
    first pass calls this expecting purely exact matching, with fuzzy matching handled
    separately (and correctly) by _find_best_paragraph_match in its second pass, which
    picks the single BEST match across the whole document. This function fuzzy-matching
    on its own used to defeat that design: the first pass iterates paragraphs in
    document order and stops at whichever paragraph FIRST crossed the 0.75 similarity
    threshold, not necessarily the correct/best one — on a resume with two similar
    bullets (e.g. "Managed AWS infrastructure..." appearing under two different jobs),
    this could silently overwrite the wrong bullet instead of the one the AI actually
    intended to replace."""
    if not paragraph.text.strip() or not original_text.strip():
        return False

    para_text = paragraph.text
    norm_para = _normalize(para_text)
    norm_original = _normalize(original_text)

    # Check if original text exists (exact or normalized)
    exact_match = original_text in para_text
    normalized_match = norm_original in norm_para

    if not exact_match and not normalized_match:
        return False

    if exact_match:
        # 1. Simple case: original_text exactly matches one run
        for run in paragraph.runs:
            if original_text in run.text:
                run.text = run.text.replace(original_text, new_text)
                return True

        # 2. Complex case: text spans multiple runs
        return _replace_across_runs(paragraph, original_text, new_text)

    if normalized_match:
        # Whitespace differs — replace the entire paragraph content preserving first run's formatting
        _replace_entire_paragraph(paragraph, new_text)
        return True

    return False

def _replace_entire_paragraph(paragraph, new_text):
    """Replace entire paragraph text while preserving the first run's formatting."""
    if not paragraph.runs:
        paragraph.text = new_text
        return

    # Keep first run's formatting, put all new text there
    paragraph.runs[0].text = new_text
    for run in paragraph.runs[1:]:
        run.text = ""

def _replace_across_runs(paragraph, original_text, new_text):
    """Handle replacement when text spans multiple runs."""
    text = paragraph.text
    start_idx = text.find(original_text)
    if start_idx < 0:
        return False

    end_idx = start_idx + len(original_text)

    curr_idx = 0
    match_runs = []

    for i, run in enumerate(paragraph.runs):
        run_len = len(run.text)
        if curr_idx + run_len > start_idx and curr_idx < end_idx:
            match_runs.append((i, curr_idx))
        curr_idx += run_len

    if not match_runs:
        return False

    first_run_idx, first_run_start = match_runs[0]
    first_run = paragraph.runs[first_run_idx]
    prefix = first_run.text[:max(0, start_idx - first_run_start)]

    last_run_idx, last_run_start = match_runs[-1]
    last_run = paragraph.runs[last_run_idx]
    suffix = last_run.text[max(0, end_idx - last_run_start):]

    # Inject new text into first run
    first_run.text = prefix + new_text + (suffix if first_run_idx == last_run_idx else "")

    # Clear subsequent runs involved in the match
    for idx, _ in match_runs[1:]:
        if idx == last_run_idx:
            paragraph.runs[idx].text = suffix
        else:
            paragraph.runs[idx].text = ""

    return True

def _all_paragraphs(doc):
    """Collect all paragraphs from the document body and any tables."""
    paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
    return paragraphs

def create_tailored_docx(original_bytes: bytes, replacements: list) -> BytesIO:
    doc = docx.Document(BytesIO(original_bytes))
    applied_count = 0

    all_paragraphs = _all_paragraphs(doc)

    for rep in replacements:
        orig = rep.get('original', '')
        new_txt = rep.get('new', '')
        if not orig or not new_txt:
            continue

        replaced = False

        # First pass: try exact match in all paragraphs
        for para in all_paragraphs:
            if replace_text_in_paragraph(para, orig, new_txt):
                replaced = True
                applied_count += 1
                break

        # Second pass: fuzzy match if exact failed
        if not replaced:
            best_para, _ = _find_best_paragraph_match(all_paragraphs, orig)
            if best_para:
                _replace_entire_paragraph(best_para, new_txt)
                applied_count += 1

    out_stream = BytesIO()
    doc.save(out_stream)
    out_stream.seek(0)
    return out_stream

def remove_bullets(original_bytes: bytes, removals: list) -> tuple:
    """Delete whole paragraphs (not just their text) so the AI's page-length/shortening
    instructions can actually reduce the document, unlike create_tailored_docx's
    replacements which always keep one paragraph per bullet. Only removes paragraphs
    that live directly in the document body — paragraphs inside table cells are skipped
    since a cell must always keep at least one paragraph, and this resume template
    doesn't use tables for bullets anyway.
    Returns (BytesIO, applied) where applied is the subset of `removals` that actually
    matched and got deleted — callers must use this (not the original `removals` list)
    for accurate "N bullets removed" reporting, since some entries may not match any
    paragraph."""
    doc = docx.Document(BytesIO(original_bytes))
    applied = []

    for text in removals:
        if not text or not text.strip():
            continue

        para, _ = _find_best_paragraph_match(list(doc.paragraphs), text)
        if para is None:
            continue

        parent_tag = para._p.getparent().tag
        if not parent_tag.endswith('}body'):
            continue

        para._p.getparent().remove(para._p)
        applied.append(text)

    out_stream = BytesIO()
    doc.save(out_stream)
    out_stream.seek(0)
    return out_stream, applied

def _skills_table(doc):
    """The resume's Technical Proficiency block is a 2-column table (category | comma-
    separated skills). Returns that table, or None if the resume doesn't use one."""
    for table in doc.tables:
        if len(table.columns) == 2 and len(table.rows) >= 3:
            return table
    return None


def _norm_category(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', name.lower().replace('&', ' and ')).strip()


def extract_skills_table(file_bytes: bytes) -> list:
    """Return [{"category": ..., "skills": <cell text>}, ...] for the resume's skills
    table so the AI prompt can be handed the real category names + current contents
    (instead of being told to 'rewrite the Skills line', which doesn't exist as a single
    paragraph in this template). Empty list if the resume has no skills table."""
    table = _skills_table(docx.Document(BytesIO(file_bytes)))
    if table is None:
        return []
    return [{"category": row.cells[0].text.strip(), "skills": row.cells[1].text.strip()}
            for row in table.rows if row.cells[0].text.strip()]


def _contains_term(haystack: str, term: str) -> bool:
    """Whole-term, case-insensitive containment ('Go' must not match 'Google')."""
    return re.search(r'(?<![\w+#.])' + re.escape(term.strip()) + r'(?![\w+#])',
                     haystack, re.IGNORECASE) is not None


def _match_category_row(table, category: str):
    target = _norm_category(category)
    if not target:
        return None
    best_row, best_ratio = None, 0.0
    for row in table.rows:
        cand = _norm_category(row.cells[0].text)
        if not cand:
            continue
        if cand == target:
            return row
        ratio = difflib.SequenceMatcher(None, target, cand).ratio()
        if ratio > best_ratio:
            best_row, best_ratio = row, ratio
    return best_row if best_ratio >= 0.6 else None


def add_skills_to_docx(original_bytes: bytes, additions: list) -> tuple:
    """Append JD skills to the matching category row of the skills table.

    `additions` is [{"category": <existing category name>, "skills": [...]}, ...].
    Purely additive: existing skills are never rewritten or dropped, and a skill already
    listed anywhere in that table is skipped, so repeated runs can't duplicate. The new
    text goes into the cell's last run, so it inherits the template's font/size.
    Returns (BytesIO, added, unplaced): `added` is [(category, skill), ...] actually
    written, `unplaced` is the skills whose category matched no row (caller reports them
    rather than silently losing them)."""
    doc = docx.Document(BytesIO(original_bytes))
    table = _skills_table(doc)
    added, unplaced = [], []

    if table is None:
        unplaced = [s for a in additions for s in a.get('skills', [])]
    else:
        table_text = ' \n '.join(row.cells[1].text for row in table.rows)
        for addition in additions:
            skills = [s.strip() for s in addition.get('skills', []) if s and s.strip()]
            row = _match_category_row(table, addition.get('category', ''))
            if row is None:
                unplaced.extend(s for s in skills if not _contains_term(table_text, s))
                continue

            new_skills = []
            for skill in skills:
                if _contains_term(table_text, skill) or skill.lower() in (n.lower() for n in new_skills):
                    continue
                new_skills.append(skill)
            if not new_skills:
                continue

            para = next((p for p in reversed(row.cells[1].paragraphs) if p.text.strip()), None)
            if para is None:
                unplaced.extend(new_skills)
                continue
            last_run = next((r for r in reversed(para.runs) if r.text), None)
            if last_run is None:
                unplaced.extend(new_skills)
                continue

            last_run.text = last_run.text.rstrip().rstrip(',.;') + ', ' + ', '.join(new_skills)
            table_text += ' \n ' + ', '.join(new_skills)
            added.extend((row.cells[0].text.strip(), s) for s in new_skills)

    out_stream = BytesIO()
    doc.save(out_stream)
    out_stream.seek(0)
    return out_stream, added, unplaced


def find_absent_keywords(file_bytes: bytes, keywords: list) -> list:
    """Keywords (from the JD's missing list) that still don't appear anywhere in the
    final resume text — used to verify tailoring actually landed them, instead of
    trusting the AI's own claim that it did."""
    text = extract_text_from_docx(file_bytes)
    seen, absent = set(), []
    for kw in keywords:
        key = kw.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if not _contains_term(text, kw):
            absent.append(kw.strip())
    return absent


def insert_bullets_after(original_bytes: bytes, insertions: list) -> BytesIO:
    """Insert new bullet paragraphs into the document, each cloned right after
    its matched anchor paragraph so it inherits the same list/formatting style."""
    doc = docx.Document(BytesIO(original_bytes))
    applied_count = 0

    for ins in insertions:
        anchor_text = ins.get('anchor', '')
        new_bullet = ins.get('new_bullet', '')
        if not anchor_text or not new_bullet:
            continue

        anchor_para, _ = _find_best_paragraph_match(_all_paragraphs(doc), anchor_text)
        if anchor_para is None:
            continue

        new_p_elem = copy.deepcopy(anchor_para._p)
        anchor_para._p.addnext(new_p_elem)
        new_para = Paragraph(new_p_elem, anchor_para._parent)

        if new_para.runs:
            new_para.runs[0].text = new_bullet
            for run in new_para.runs[1:]:
                run.text = ""
        else:
            new_para.text = new_bullet

        applied_count += 1

    out_stream = BytesIO()
    doc.save(out_stream)
    out_stream.seek(0)
    return out_stream

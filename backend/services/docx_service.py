import docx
from io import BytesIO

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

def replace_text_in_paragraph(paragraph, original_text, new_text):
    if not paragraph.text.strip() or not original_text.strip():
        return False
        
    if original_text not in paragraph.text:
        return False

    # 1. Simple case: original_text exactly matches one run (preserves format perfectly)
    for run in paragraph.runs:
        if original_text in run.text:
            run.text = run.text.replace(original_text, new_text)
            return True

    # 2. Complex case: text spans multiple runs (happens often due to word spellcheck boundaries)
    text = paragraph.text
    start_idx = text.find(original_text)
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

def create_tailored_docx(original_bytes: bytes, replacements: list) -> BytesIO:
    doc = docx.Document(BytesIO(original_bytes))
    
    for rep in replacements:
        orig = rep.get('original', '')
        new_txt = rep.get('new', '')
        if not orig or not new_txt:
            continue
            
        replaced = False
        
        # Search paragraphs
        for para in doc.paragraphs:
            if replace_text_in_paragraph(para, orig, new_txt):
                replaced = True
                break
                
        # Search tables
        if not replaced:
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for para in cell.paragraphs:
                            if replace_text_in_paragraph(para, orig, new_txt):
                                replaced = True
                                break
                        if replaced: break
                    if replaced: break
                if replaced: break
                
    out_stream = BytesIO()
    doc.save(out_stream)
    out_stream.seek(0)
    return out_stream

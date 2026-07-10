import { useState, useEffect, useCallback, useRef } from 'react';
import './index.css';

const API = 'http://localhost:8000';

const PIPELINE_STAGES = ['Found', 'Shortlisted', 'Applied', 'Interviewing', 'Offered', 'Rejected'];
const STAGE_LABELS = {
  Found: 'Discovered', Shortlisted: 'Saved', Applied: 'Applied',
  Interviewing: 'Interview', Offered: 'Offer', Rejected: 'Rejected',
};

function recommendationBadge(job) {
  if (job.status === 'Rejected') return { label: 'Skip', color: '#d94f4f' };
  const score = job.score || 0;
  if (score >= 80) return { label: 'Strong Apply', color: '#2ebd73' };
  if (score >= 60) return { label: 'Maybe Apply', color: '#c89b3c' };
  if (score > 0) return { label: 'Needs Review', color: '#818cf8' };
  return { label: 'Not Scored', color: '#68604e' };
}

function workModeBadge(tags) {
  const t = (tags || []).map(x => x.toLowerCase());
  if (t.some(x => x.includes('remote'))) return 'Remote';
  if (t.some(x => x.includes('hybrid'))) return 'Hybrid';
  if (t.some(x => x.includes('on-site') || x.includes('onsite'))) return 'Onsite';
  return null;
}

// Colors for job.employment_type_label — the backend detection is the SAME regex
// classification the search-time hard-reject rule uses to decide C2C/C2H/W2/etc., not
// a loose guess off Claude's tags, so this is trustworthy enough to highlight.
const EMPLOYMENT_TYPE_COLORS = { c2c: '#2ebd73', c2h: '#2ebd73', w2: '#d94f4f', contract: '#c89b3c' };

function computeNextBestAction(job) {
  const desc = (job.description || '').trim();
  if (desc.length < 40) return { text: 'Job description is too thin to act on — fetch or paste the full posting.', action: 'fetch_description' };
  if (!job.score) return { text: 'This job has not been scored yet.', action: 'rescore' };
  if (job.status === 'Rejected') return { text: job.rejection_reason || 'This job was skipped.', action: null };
  if (job.status === 'Found' && job.score < 60) return { text: 'Low match score — consider skipping unless the details look better than the score suggests.', action: 'skip' };
  if (job.status === 'Found') return { text: 'Save this job before doing anything else with it.', action: 'save' };
  if (job.status === 'Shortlisted' && !job.file_path) return { text: 'Tailor a resume for this role before applying.', action: 'tailor' };
  if (job.status === 'Shortlisted') return { text: 'You have a tailored resume — apply directly.', action: 'mark_applied' };
  if (job.status === 'Applied') {
    const days = job.status_updated_at ? Math.floor((Date.now() - new Date(job.status_updated_at)) / 86400000) : 0;
    if (days >= 7) return { text: `Applied ${days} days ago with no update — send a follow-up.`, action: 'follow_up' };
    return { text: `Applied ${days} day${days !== 1 ? 's' : ''} ago — sit tight, or reach out to a recruiter.`, action: 'find_contact' };
  }
  return { text: 'Keep this application moving — update its status as things change.', action: null };
}

function timeAgo(iso) {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso)) / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return '1 day ago';
  return `${days} days ago`;
}

export default function JobDetailWorkspace({ jobId, onClose, onSendToTailor, onSaveToApplications, onJobUpdated, selectedResumeName }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [banner, setBanner] = useState(null);
  const [descDraft, setDescDraft] = useState('');
  const [showPasteDesc, setShowPasteDesc] = useState(false);
  const [notesDraft, setNotesDraft] = useState('');
  const [draftEdits, setDraftEdits] = useState({});
  const [gmailConnected, setGmailConnected] = useState(false);

  // Guards fetchJob against out-of-order responses: if the user opens job A then
  // quickly switches to job B before A's fetch resolves, A's response must not
  // overwrite B's already-rendered panel.
  const activeJobIdRef = useRef(null);

  const fetchJob = useCallback(async () => {
    if (!jobId) return;
    activeJobIdRef.current = jobId;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/jobs/${jobId}`);
      const data = await res.json().catch(() => ({}));
      if (activeJobIdRef.current !== jobId) return; // superseded by a newer selection
      if (!res.ok) throw new Error('Failed to load job');
      setJob(data);
      setNotesDraft(data.user_notes || '');
      const edits = {};
      Object.entries(data.drafts || {}).forEach(([type, d]) => { edits[type] = { subject: d.subject || '', body: d.body || '' }; });
      setDraftEdits(edits);
    } catch (e) {
      if (activeJobIdRef.current === jobId) setError(e.message);
    } finally {
      if (activeJobIdRef.current === jobId) setLoading(false);
    }
  }, [jobId]);

  useEffect(() => { fetchJob(); }, [fetchJob]);

  useEffect(() => {
    if (!jobId) return;
    fetch(`${API}/api/gmail/status`)
      .then(res => res.json())
      .then(data => setGmailConnected(!!data.connected))
      .catch(() => setGmailConnected(false));
  }, [jobId]);

  if (!jobId) return null;

  const notify = (type, message) => {
    setBanner({ type, message });
    setTimeout(() => setBanner(b => (b && b.message === message ? null : b)), 5000);
  };

  const runAction = async (key, fn, successMsg) => {
    setBusy(key);
    setBanner(null);
    try {
      const result = await fn();
      if (result !== undefined) setJob(result);
      if (successMsg) notify('success', successMsg);
      onJobUpdated && onJobUpdated();
    } catch (e) {
      notify('error', e.message || 'Something went wrong');
    } finally {
      setBusy(null);
    }
  };

  const patchJson = async (path, body, method = 'POST') => {
    const res = await fetch(`${API}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
    return json;
  };

  const handleRescore = () => runAction('rescore', () => patchJson(`/api/jobs/${jobId}/rescore`, {}), 'Re-scored with AI');
  const handleStatus = (status, rejection_reason) =>
    runAction(`status:${status}`, () => patchJson(`/api/jobs/${jobId}/status`, { status, rejection_reason }), `Marked as ${STAGE_LABELS[status] || status}`);
  const handleFindContact = () => runAction('contact', async () => {
    const r = await patchJson(`/api/jobs/${jobId}/contact`, {});
    // Returning an updater (not a plain object built from the closed-over `job`)
    // avoids a lost-update race: multiple action buttons aren't mutually exclusive
    // (only the button whose own busyKey matches `busy` is disabled), so two AI
    // actions can be in flight at once — whichever's setJob applies last must merge
    // against the *current* job state, not a stale snapshot from when it was clicked.
    return prev => ({ ...prev, contact: r.contact });
  }, 'Contact suggestions ready');
  const handleFetchDescription = () => runAction('fetch_description', () => patchJson(`/api/jobs/${jobId}/fetch-description`, {}), 'Description fetched');
  const handlePasteDescription = () => runAction('paste_description', async () => {
    const r = await patchJson(`/api/jobs/${jobId}/description`, { description: descDraft });
    setShowPasteDesc(false);
    return r;
  }, 'Description saved');
  const handleSaveNotes = () => runAction('notes', () => patchJson(`/api/jobs/${jobId}/notes`, { notes: notesDraft }), 'Notes saved');

  const handleGenerateDraft = (draftType) => runAction(`draft:${draftType}`, async () => {
    const r = await patchJson(`/api/jobs/${jobId}/draft`, { draft_type: draftType });
    setDraftEdits(prev => ({ ...prev, [draftType]: { subject: r.draft.subject || '', body: r.draft.body || '' } }));
    return prev => ({ ...prev, drafts: { ...(prev.drafts || {}), [draftType]: r.draft } });
  }, 'Draft generated');

  const handleSaveDraft = (draftType) => runAction(`savedraft:${draftType}`, async () => {
    const edit = draftEdits[draftType] || { subject: '', body: '' };
    const r = await patchJson(`/api/jobs/${jobId}/draft/save`, { draft_type: draftType, subject: edit.subject, body: edit.body });
    return prev => ({ ...prev, drafts: { ...(prev.drafts || {}), [draftType]: r.draft } });
  }, 'Draft saved');

  const handleGenerateCoverLetter = () => runAction('cover_letter', async () => {
    if (!job.file_path) throw new Error('Tailor a resume first — cover letters are generated from a tailored resume file.');
    const res = await fetch(`${API}/api/history/${jobId}/cover-letter`, { method: 'POST' });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || 'Failed to generate cover letter');
    return prev => ({ ...prev, cover_letter_generated: true });
  }, 'Cover letter generated');

  const handleTailorInPlace = () => runAction('tailor', async () => {
    const desc = (job.description || '').trim();
    if (desc.length < 50) throw new Error('Not enough job description text to tailor against — fetch or paste it first.');
    const params = new URLSearchParams();
    if (selectedResumeName) params.set('selected_resume', selectedResumeName);
    const res = await fetch(`${API}/api/jobs/${jobId}/tailor?${params.toString()}`, { method: 'POST' });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || 'Failed to tailor resume');
    return j.job;
  }, 'Resume tailored for this job');

  const handleSaveDraftToGmail = (draftType) => runAction(`gmail:${draftType}`, async () => {
    const edit = draftEdits[draftType] || { subject: '', body: '' };
    const toEmail = job.contact?.email_guess || job.contact?.found_contacts?.[0]?.email || '';
    const payload = {
      to_emails: toEmail ? [toEmail] : [],
      subject: edit.subject || (draftType === 'linkedin_message' ? job.title || '' : ''),
      body: edit.body,
      record_id: jobId,
      attach_resume: draftType === 'recruiter_email' && !!job.file_path,
      attach_cover_letter: draftType === 'recruiter_email' && !!job.cover_letter_generated,
    };
    const res = await fetch(`${API}/api/gmail/save-draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || 'Failed to save Gmail draft');
    return undefined;
  }, 'Saved to Gmail Drafts');

  const handleExplainMatch = () => {
    document.querySelector('.jdw-content')?.scrollTo?.({ top: 0, behavior: 'smooth' });
    if (job.reasons && job.reasons.length > 0) {
      fetch(`${API}/api/jobs/${jobId}/explain-match`, { method: 'POST' }).catch(() => {});
    }
  };

  const handleSendToTailor = () => {
    fetch(`${API}/api/jobs/${jobId}/send-to-tailor`, { method: 'POST' }).catch(() => {});
    onSendToTailor && onSendToTailor(job.description || job.title);
  };

  const handleSaveToApplications = () => runAction('save', async () => {
    if (onSaveToApplications) {
      await onSaveToApplications(job);
    } else {
      await patchJson('/api/applications', { company: job.company, title: job.title, url: job.url, source: 'command-center' });
    }
    return prev => ({ ...prev, status: 'Shortlisted' });
  }, 'Saved to Applications');

  const copyToClipboard = (text) => {
    navigator.clipboard?.writeText(text).then(() => notify('success', 'Copied to clipboard'));
  };

  const openGmail = (subject, body) => {
    window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`, '_blank');
  };

  const rec = job ? recommendationBadge(job) : null;
  const workMode = job ? workModeBadge(job.tags) : null;
  const nextBest = job ? computeNextBestAction(job) : null;

  return (
    <div className="jdw-backdrop" onClick={onClose}>
      <div className="jdw-panel" onClick={e => e.stopPropagation()}>
        <button className="jdw-close" onClick={onClose} aria-label="Close">&times;</button>

        {loading && <div className="cmd-loading">Loading job...</div>}
        {error && <div className="error-banner" style={{ margin: '1rem' }}>{error}</div>}

        {job && (
          <div className="jdw-content">
            {banner && (
              <div className={`jdw-banner jdw-banner-${banner.type}`}>{banner.message}</div>
            )}

            {/* 8. AI Next Best Action */}
            {nextBest && (
              <div className="jdw-next-action">
                <div className="jdw-next-action-label">Recommended Next Action</div>
                <div className="jdw-next-action-text">{nextBest.text}</div>
                {nextBest.action && (
                  <button
                    className="cmd-cta cmd-cta-primary"
                    disabled={!!busy}
                    onClick={() => {
                      if (nextBest.action === 'fetch_description') handleFetchDescription();
                      else if (nextBest.action === 'rescore') handleRescore();
                      else if (nextBest.action === 'skip') handleStatus('Rejected', 'Skipped by user');
                      else if (nextBest.action === 'save') handleSaveToApplications();
                      else if (nextBest.action === 'tailor') handleTailorInPlace();
                      else if (nextBest.action === 'mark_applied') handleStatus('Applied');
                      else if (nextBest.action === 'follow_up') handleGenerateDraft('follow_up_email');
                      else if (nextBest.action === 'find_contact') handleFindContact();
                    }}
                  >
                    {busy ? 'Working...' : 'Do it'}
                  </button>
                )}
              </div>
            )}

            {/* 1. Job Header */}
            <div className="jdw-header">
              <h2 className="jdw-title">{job.title}</h2>
              <div className="jdw-company-line">{job.company} &middot; {job.location || 'Location unknown'}</div>
              <div className="jdw-badges">
                <span className="jdw-badge" style={{ background: `${rec.color}22`, color: rec.color, borderColor: rec.color }}>{rec.label}</span>
                {workMode && <span className="jdw-badge jdw-badge-muted">{workMode}</span>}
                {job.employment_type_label && (
                  <span
                    className={`jdw-badge${EMPLOYMENT_TYPE_COLORS[job.employment_type] ? '' : ' jdw-badge-muted'}`}
                    style={
                      EMPLOYMENT_TYPE_COLORS[job.employment_type]
                        ? { background: `${EMPLOYMENT_TYPE_COLORS[job.employment_type]}22`, color: EMPLOYMENT_TYPE_COLORS[job.employment_type], borderColor: EMPLOYMENT_TYPE_COLORS[job.employment_type] }
                        : undefined
                    }
                  >
                    {job.employment_type_label}
                  </span>
                )}
                <span className="jdw-badge jdw-badge-muted">{STAGE_LABELS[job.status] || job.status}</span>
              </div>
              <div className="jdw-header-meta">
                <div><span className="jdw-meta-label">Match score</span> <strong style={{ color: 'var(--gold)' }}>{job.score || 0}</strong></div>
                <div><span className="jdw-meta-label">Discovered</span> {job.created_at ? new Date(job.created_at).toLocaleDateString() : '—'}</div>
                <div><span className="jdw-meta-label">Source</span> {job.source === 'manual' ? 'Manual' : 'Command Center'}</div>
              </div>
              <div className="jdw-header-actions">
                {job.url && <button className="cmd-filter-pill" onClick={() => window.open(job.url, '_blank')}>Open Original Job</button>}
                <button className="cmd-filter-pill" onClick={handleRescore} disabled={busy === 'rescore'}>
                  {busy === 'rescore' ? 'Scoring...' : 'Score Again with AI'}
                </button>
              </div>
            </div>

            {/* 2. AI Match Explanation */}
            <Section title="AI Match Explanation">
              {job.reasons && job.reasons.length > 0 ? (
                <ul className="jdw-list">{job.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              ) : (
                <div className="jdw-empty">No AI explanation yet. <button className="cmd-filter-pill" onClick={handleRescore}>Score with AI</button></div>
              )}
              {job.tags && job.tags.length > 0 && (
                <div className="jdw-tag-row">
                  {job.tags.map(t => <span key={t} className="cmd-skill-tag">{t}</span>)}
                </div>
              )}
              {job.next_action && <div className="jdw-ai-summary"><strong>AI recommendation:</strong> {job.next_action}</div>}
              {job.rejection_reason && <div className="jdw-risk-flag"><strong>Why skip:</strong> {job.rejection_reason}</div>}
            </Section>

            {/* 3. Job Description */}
            <Section title="Job Description">
              {job.description && job.description.trim().length >= 40 ? (
                <p className="jdw-description">{job.description}</p>
              ) : (
                <div className="jdw-empty">
                  Job description missing.
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                    <button className="cmd-filter-pill" onClick={handleFetchDescription} disabled={busy === 'fetch_description'}>
                      {busy === 'fetch_description' ? 'Fetching...' : 'Fetch job details'}
                    </button>
                    <button className="cmd-filter-pill" onClick={() => { setDescDraft(job.description || ''); setShowPasteDesc(true); }}>
                      Paste job description manually
                    </button>
                  </div>
                  {showPasteDesc && (
                    <div style={{ marginTop: '0.75rem' }}>
                      <textarea className="cmd-select" style={{ width: '100%', minHeight: '120px' }} value={descDraft} onChange={e => setDescDraft(e.target.value)} />
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                        <button className="cmd-cta cmd-cta-primary" onClick={handlePasteDescription} disabled={busy === 'paste_description'}>Save</button>
                        <button className="cmd-filter-pill" onClick={() => setShowPasteDesc(false)}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Section>

            {/* 4. Contact & Outreach */}
            <Section title="Contact & Outreach">
              {job.contact ? (
                <div className="jdw-contact-list">
                  {job.contact.verified && (
                    <div className="jdw-contact-verified-badge">Verified from job posting</div>
                  )}
                  {job.contact.contact_name && <ContactRow label="Contact name" value={job.contact.contact_name} />}
                  {job.contact.contact_phone && <ContactRow label="Contact phone" value={job.contact.contact_phone} />}
                  {job.contact.email_guess && <ContactRow label={job.contact.verified ? 'Email' : 'Email guess — verify before sending'} value={job.contact.email_guess} />}

                  {job.contact.found_contacts && job.contact.found_contacts.length > 0 && (
                    <>
                      <div className="jdw-contact-verified-badge jdw-contact-badge-web">Found from company/contact page</div>
                      {job.contact.found_contacts.map((c, i) => (
                        <div key={i} className="jdw-found-contact">
                          <div className="jdw-found-contact-name">{c.name || '(unnamed)'}{c.title ? ` — ${c.title}` : ''}</div>
                          {c.email && <div className="jdw-found-contact-detail">{c.email}</div>}
                          {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer" className="jdw-contact-link">{c.source_url}</a>}
                        </div>
                      ))}
                    </>
                  )}

                  <div className="jdw-contact-badge-suggested">Suggested LinkedIn search</div>
                  {job.contact.linkedin_recruiter_search && <ContactRow label="LinkedIn — recruiter search" value={job.contact.linkedin_recruiter_search} link />}
                  {job.contact.linkedin_hiring_manager_search && <ContactRow label="LinkedIn — hiring manager search" value={job.contact.linkedin_hiring_manager_search} link />}
                  {job.contact.linkedin_company_url && <ContactRow label="Company LinkedIn" value={job.contact.linkedin_company_url} link />}
                  {job.contact.careers_page && <ContactRow label="Careers page" value={job.contact.careers_page} link />}
                  {job.contact.outreach_strategy && <div className="jdw-outreach-strategy">{job.contact.outreach_strategy}</div>}
                  {!job.contact.verified && (!job.contact.found_contacts || job.contact.found_contacts.length === 0) && (
                    <div className="jdw-contact-disclaimer">Suggested — not verified. Double-check before using.</div>
                  )}
                  <button className="cmd-filter-pill" onClick={handleFindContact} disabled={busy === 'contact'} style={{ marginTop: '0.4rem' }}>
                    {busy === 'contact' ? 'Searching...' : 'Search again'}
                  </button>
                </div>
              ) : (
                <div className="jdw-empty">
                  No contact found yet.
                  <button className="cmd-filter-pill" onClick={handleFindContact} disabled={busy === 'contact'} style={{ marginLeft: '0.5rem' }}>
                    {busy === 'contact' ? 'Searching...' : 'Find contact with AI'}
                  </button>
                </div>
              )}
            </Section>

            {/* 5. AI Action Buttons */}
            <Section title="AI Actions">
              <div className="jdw-action-grid">
                <ActionButton label="Explain Match" busy={false} onClick={handleExplainMatch} />
                <ActionButton label="Generate Tailored Resume" busyKey="tailor" busy={busy} onClick={handleTailorInPlace} />
                <ActionButton label="Send to Resume Tailor" onClick={handleSendToTailor} />
                <ActionButton label="Generate Cover Letter" busyKey="cover_letter" busy={busy} onClick={handleGenerateCoverLetter} />
                <ActionButton label="Generate Recruiter Email" busyKey="draft:recruiter_email" busy={busy} onClick={() => handleGenerateDraft('recruiter_email')} />
                <ActionButton label="Generate Follow-up Email" busyKey="draft:follow_up_email" busy={busy} onClick={() => handleGenerateDraft('follow_up_email')} />
                <ActionButton label="Generate LinkedIn Message" busyKey="draft:linkedin_message" busy={busy} onClick={() => handleGenerateDraft('linkedin_message')} />
                <ActionButton label="Find Contact" busyKey="contact" busy={busy} onClick={handleFindContact} />
                <ActionButton label="Save to Applications" busyKey="save" busy={busy} onClick={handleSaveToApplications} />
                <ActionButton label="Mark Applied" busyKey="status:Applied" busy={busy} onClick={() => handleStatus('Applied')} />
                <ActionButton label="Mark Interview" busyKey="status:Interviewing" busy={busy} onClick={() => handleStatus('Interviewing')} />
                <ActionButton label="Mark Rejected" busyKey="status:Rejected" busy={busy} onClick={() => handleStatus('Rejected', 'Rejected by employer')} />
                <ActionButton label="Skip Job" busyKey="status:Rejected" busy={busy} onClick={() => handleStatus('Rejected', 'Skipped by user')} />
              </div>
            </Section>

            {/* 6. Drafts */}
            <Section title="Drafts">
              {['recruiter_email', 'follow_up_email', 'linkedin_message'].map(type => (
                <DraftEditor
                  key={type}
                  type={type}
                  label={{ recruiter_email: 'Recruiter Outreach Email', follow_up_email: 'Follow-up Email', linkedin_message: 'LinkedIn Message' }[type]}
                  draft={draftEdits[type]}
                  busy={busy}
                  gmailConnected={gmailConnected}
                  onChange={(field, value) => setDraftEdits(prev => ({ ...prev, [type]: { ...(prev[type] || {}), [field]: value } }))}
                  onGenerate={() => handleGenerateDraft(type)}
                  onSave={() => handleSaveDraft(type)}
                  onCopy={() => copyToClipboard(`${draftEdits[type]?.subject ? draftEdits[type].subject + '\n\n' : ''}${draftEdits[type]?.body || ''}`)}
                  onOpenGmail={() => openGmail(draftEdits[type]?.subject || '', draftEdits[type]?.body || '')}
                  onSaveToGmail={() => handleSaveDraftToGmail(type)}
                />
              ))}
              <div className="jdw-draft-card">
                <div className="jdw-draft-header">Notes for Application</div>
                <textarea className="cmd-select" style={{ width: '100%', minHeight: '70px' }} value={notesDraft} onChange={e => setNotesDraft(e.target.value)} />
                <div className="jdw-draft-actions">
                  <button className="cmd-cta cmd-cta-primary" onClick={handleSaveNotes} disabled={busy === 'notes'}>
                    {busy === 'notes' ? 'Saving...' : 'Save Notes'}
                  </button>
                </div>
              </div>
            </Section>

            {/* 7. Application Tracker */}
            <Section title="Application Tracker">
              <div className="jdw-tracker-chips">
                {PIPELINE_STAGES.map(s => (
                  <span key={s} className={`jdw-tracker-chip ${job.status === s ? 'active' : ''}`}>{STAGE_LABELS[s]}</span>
                ))}
              </div>
              <div className="jdw-tracker-grid">
                <div><span className="jdw-meta-label">Status updated</span> {job.status_updated_at ? timeAgo(job.status_updated_at) : '—'}</div>
                {job.status === 'Applied' && (
                  <div><span className="jdw-meta-label">Follow-up due</span> {job.status_updated_at ? new Date(new Date(job.status_updated_at).getTime() + 7 * 86400000).toLocaleDateString() : '—'}</div>
                )}
                <div><span className="jdw-meta-label">Last contacted</span> {job.contact?.generated_at ? timeAgo(job.contact.generated_at) : 'Never'}</div>
                <div><span className="jdw-meta-label">Contact</span> {job.contact ? 'Suggested (see above)' : 'None yet'}</div>
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="jdw-section">
      <div className="jdw-section-title">{title}</div>
      {children}
    </div>
  );
}

function ContactRow({ label, value, link }) {
  if (!value) return null;
  return (
    <div className="jdw-contact-row">
      <span className="jdw-meta-label">{label}</span>
      {link ? <a href={value} target="_blank" rel="noreferrer" className="jdw-contact-link">{value}</a> : <span>{value}</span>}
    </div>
  );
}

function ActionButton({ label, onClick, busy, busyKey }) {
  const isBusy = busyKey && busy === busyKey;
  return (
    <button className="jdw-action-btn" onClick={onClick} disabled={isBusy}>
      {isBusy ? 'Working...' : label}
    </button>
  );
}

function DraftEditor({ type, label, draft, busy, gmailConnected, onChange, onGenerate, onSave, onCopy, onOpenGmail, onSaveToGmail }) {
  const hasDraft = draft && (draft.subject || draft.body);
  const genBusy = busy === `draft:${type}`;
  const saveBusy = busy === `savedraft:${type}`;
  const gmailBusy = busy === `gmail:${type}`;
  return (
    <div className="jdw-draft-card">
      <div className="jdw-draft-header">{label}</div>
      {!hasDraft ? (
        <div className="jdw-empty">
          No draft yet.
          <button className="cmd-filter-pill" onClick={onGenerate} disabled={genBusy} style={{ marginLeft: '0.5rem' }}>
            {genBusy ? 'Generating...' : `Generate ${label}`}
          </button>
        </div>
      ) : (
        <>
          {type !== 'linkedin_message' && (
            <input className="cmd-select" style={{ width: '100%', marginBottom: '0.4rem' }} value={draft.subject} onChange={e => onChange('subject', e.target.value)} placeholder="Subject" />
          )}
          <textarea className="cmd-select" style={{ width: '100%', minHeight: '90px' }} value={draft.body} onChange={e => onChange('body', e.target.value)} />
          <div className="jdw-draft-actions">
            <button className="cmd-cta cmd-cta-primary" onClick={onSave} disabled={saveBusy}>{saveBusy ? 'Saving...' : 'Save Draft'}</button>
            <button className="cmd-filter-pill" onClick={onCopy}>Copy</button>
            <button className="cmd-filter-pill" onClick={onGenerate} disabled={genBusy}>{genBusy ? 'Regenerating...' : 'Regenerate'}</button>
            {type !== 'linkedin_message' && (
              gmailConnected ? (
                <button className="cmd-filter-pill jdw-gmail-btn" onClick={onSaveToGmail} disabled={gmailBusy}>
                  {gmailBusy ? 'Saving to Gmail...' : 'Save to Gmail Drafts'}
                </button>
              ) : (
                <button className="cmd-filter-pill" onClick={onOpenGmail} title="Connect Gmail (Info page) to save a real draft instead">
                  Open in Email App
                </button>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}

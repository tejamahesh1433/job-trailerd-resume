import React, { useState } from 'react';

const API_BASE = 'http://localhost:8000';

const STATUS_OPTIONS = ['Scanned', 'Matched', 'Submitted Profile', 'Applied', 'Phone Screen', 'Interview', 'Offer', 'Rejected'];

const SOURCE_LABELS = {
  'command-center': 'Command Center',
  'job-finder': 'Job Finder',
  'dashboard': 'Resume Tailor',
};

function sourceLabel(source) {
  const key = source || 'dashboard';
  return SOURCE_LABELS[key] || key;
}

const SUBPAGES = [
  { key: 'notes', label: 'Notes' },
  { key: 'progress', label: 'Progress' },
  { key: 'emails', label: 'Mails Received' },
];

function scoreAccent(score) {
  if (score >= 85) return '#2ebd73';
  if (score >= 60) return '#c89b3c';
  return '#d94f4f';
}

function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

const MAIL_QUOTE_START = '── Linked Mail ──';
const MAIL_QUOTE_END = '── End Mail ──';
const MAIL_QUOTE_REGEX = /── Linked Mail ──\n[\s\S]*?── End Mail ──\n?/g;

// Reply emails carry the entire prior thread quoted below the new content
// (Gmail/Outlook convention) — cut that off so only this one message's own
// text gets attached, not every earlier message in the conversation.
function stripQuotedReply(text) {
  if (!text) return text;
  const lines = text.split(/\r?\n/);
  let cutoff = lines.length;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*On .{0,120} wrote:\s*$/i.test(line)) { cutoff = i; break; }
    if (/^-{2,}\s*Original Message\s*-{2,}/i.test(line)) { cutoff = i; break; }
    if (line.trim().startsWith('>')) { cutoff = i; break; }
    if (i > 2 && /^From:\s?.+$/i.test(line) && lines[i + 1] && /^Sent:/i.test(lines[i + 1])) { cutoff = i; break; }
  }
  return lines.slice(0, cutoff).join('\n').trim();
}

function buildEmailNoteBlock(msg, body) {
  const from = (msg.from || '').replace(/<.*>/, '').replace(/"/g, '').trim() || 'Unknown sender';
  const text = stripQuotedReply(body || msg.snippet || '');
  return `${MAIL_QUOTE_START}\nSubject: ${msg.subject || '(no subject)'}\nFrom: ${from}\nDate: ${formatDate(msg.date)}\n${text}\n${MAIL_QUOTE_END}\n`;
}

function parseNotesSegments(text) {
  const segments = [];
  let lastIndex = 0;
  const regex = new RegExp(MAIL_QUOTE_REGEX);
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) segments.push({ type: 'edit', text: text.slice(lastIndex, match.index) });
    segments.push({ type: 'quote', text: match[0] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length || segments.length === 0) {
    segments.push({ type: 'edit', text: text.slice(lastIndex) });
  }
  return segments;
}

export default function NotesPage({ history, gmailConnected, onStatusChange, onRefreshHistory }) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [subpage, setSubpage] = useState('notes');

  const [notesDraft, setNotesDraft] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);
  const [notesSaved, setNotesSaved] = useState(false);

  const [emails, setEmails] = useState([]);
  const [emailsLoading, setEmailsLoading] = useState(false);
  const [emailsError, setEmailsError] = useState(null);
  const [emailsFetchedFor, setEmailsFetchedFor] = useState(null);
  const [openEmailId, setOpenEmailId] = useState(null);
  const [openEmailBody, setOpenEmailBody] = useState(null);
  const [openEmailLoading, setOpenEmailLoading] = useState(false);
  const [linkedEmailId, setLinkedEmailId] = useState(null);

  const selectedJob = history.find(item => item.id === selectedId) || null;

  // Command Center's pre-screen rejects (no C2C/C2H terms, W2-only, etc.) are automatic
  // filtering noise, not real applications — keep them out of the Notes list entirely
  // (same rule History page applies) so they don't drown out jobs actually being tracked.
  const trackedJobs = history.filter(item => !(item.source === 'command-center' && item.status === 'Rejected'));

  const sources = [...new Set(trackedJobs.map(item => item.source || 'dashboard'))].sort();

  const filteredJobs = trackedJobs.filter(item => {
    const matchesSearch = !search || (item.company_name || '').toLowerCase().includes(search.toLowerCase());
    const matchesStatus = !statusFilter || (item.status || 'Scanned') === statusFilter;
    const matchesSource = !sourceFilter || (item.source || 'dashboard') === sourceFilter;
    return matchesSearch && matchesStatus && matchesSource;
  });

  const handleSelectJob = (job) => {
    setSelectedId(job.id);
    setSubpage('notes');
    setNotesDraft(job.user_notes || '');
    setNotesSaved(false);
    setOpenEmailId(null);
    setOpenEmailBody(null);
    setLinkedEmailId(null);
  };

  const handleAddEmailToNotes = (msg) => {
    const block = buildEmailNoteBlock(msg, openEmailId === msg.id ? openEmailBody?.body : null);
    setNotesDraft(prev => (prev && prev.trim() ? `${prev.replace(/\s+$/, '')}\n\n${block}\n` : `${block}\n`));
    setLinkedEmailId(msg.id);
    setSubpage('notes');
  };

  const updateNotesSegment = (idx, value) => {
    const segments = parseNotesSegments(notesDraft);
    segments[idx] = { ...segments[idx], text: value };
    setNotesDraft(segments.map(s => s.text).join(''));
  };

  const handleSaveNotes = async () => {
    if (!selectedJob) return;
    setSavingNotes(true);
    setNotesSaved(false);
    try {
      const res = await fetch(`${API_BASE}/api/history/${selectedJob.id}/notes`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notesDraft }),
      });
      if (res.ok) {
        setNotesSaved(true);
        onRefreshHistory?.();
        setTimeout(() => setNotesSaved(false), 3000);
      }
    } catch { /* ignore */ }
    finally { setSavingNotes(false); }
  };

  const fetchEmails = async (job) => {
    if (!job) return;
    setEmailsLoading(true);
    setEmailsError(null);
    try {
      const email = (job.vendor_contact_email || '').trim();
      const company = (job.company_name || '').trim();
      // Match on the vendor's actual email address (both sent-to and received-from,
      // across all threads) rather than just company-name text, so correspondence with
      // that contact shows up even when the subject/body never mentions the company.
      const parts = [];
      if (email) parts.push(`from:${email}`, `to:${email}`);
      if (company) parts.push(`"${company}"`);
      const q = parts.length ? `(${parts.join(' OR ')})` : '';
      const params = new URLSearchParams({ q, limit: '25', mode: 'cheap' });
      const res = await fetch(`${API_BASE}/api/gmail/inbox?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load mail');
      setEmails(data.messages || []);
      setEmailsFetchedFor(job.id);
    } catch (e) {
      setEmailsError(e.message || 'Failed to load mail');
    } finally {
      setEmailsLoading(false);
    }
  };

  const handleOpenSubpage = (key) => {
    setSubpage(key);
    if (key === 'emails' && selectedJob && gmailConnected && emailsFetchedFor !== selectedJob.id) {
      fetchEmails(selectedJob);
    }
  };

  const handleOpenEmail = async (messageId) => {
    if (openEmailId === messageId) { setOpenEmailId(null); setOpenEmailBody(null); return; }
    setOpenEmailId(messageId);
    setOpenEmailBody(null);
    setOpenEmailLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/gmail/message/${messageId}`);
      const data = await res.json();
      if (res.ok) setOpenEmailBody(data);
    } catch { /* ignore */ }
    finally { setOpenEmailLoading(false); }
  };

  return (
    <div className="inbox-page">
      <div className="inbox-header">
        <div>
          <h1 className="inbox-title">Notes</h1>
          <p className="inbox-subtitle">Pick a scanned job to track mail, progress, and notes in one place.</p>
        </div>
      </div>

      <div className="inbox-layout">
        <section className="inbox-list-panel">
          <div className="inbox-list-head">
            <span>{filteredJobs.length} job{filteredJobs.length === 1 ? '' : 's'}</span>
          </div>
          <div className="history-filters" style={{ padding: '0 0.75rem 0.5rem', margin: 0 }}>
            <input
              type="text"
              className="history-search"
              placeholder="Search company…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <select
              className="history-filter-select"
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
            >
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select
              className="history-filter-select"
              value={sourceFilter}
              onChange={e => setSourceFilter(e.target.value)}
            >
              <option value="">All Sources</option>
              {sources.map(s => <option key={s} value={s}>{sourceLabel(s)}</option>)}
            </select>
            {(search || statusFilter || sourceFilter) && (
              <button className="filter-clear-btn" onClick={() => { setSearch(''); setStatusFilter(''); setSourceFilter(''); }}>✕ Clear</button>
            )}
          </div>
          {filteredJobs.length === 0 ? (
            <div className="inbox-empty-state">No scanned jobs yet.</div>
          ) : (
            <div className="inbox-message-list">
              {filteredJobs.map(job => (
                <button
                  key={job.id}
                  className={`inbox-message-row ${selectedId === job.id ? 'selected' : ''}`}
                  onClick={() => handleSelectJob(job)}
                >
                  <span className="inbox-message-topline">
                    <span className="inbox-message-from">{job.company_name || 'Unknown'}</span>
                    <span className="score-badge" style={{ color: scoreAccent(job.score || 0) }}>{job.score || 0}%</span>
                  </span>
                  <span className={`job-status-badge status-${(job.status || 'Scanned').toLowerCase().replace(' ', '-')}`}>
                    {job.status || 'Scanned'}
                  </span>
                  <span className="inbox-message-meta">{formatDate(job.created_at)}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="inbox-reader-panel">
          {!selectedJob ? (
            <div className="inbox-reader-empty">Select a job to view its notes, progress, and mail.</div>
          ) : (
            <>
              <div className="inbox-reader-header">
                <div>
                  <div className="inbox-reader-subject">{selectedJob.company_name}</div>
                  <div className="inbox-reader-from">Scanned {formatDate(selectedJob.created_at)}</div>
                </div>
                <select
                  className="cmd-select"
                  value={subpage}
                  onChange={e => handleOpenSubpage(e.target.value)}
                >
                  {SUBPAGES.map(sp => (
                    <option key={sp.key} value={sp.key}>{sp.label}</option>
                  ))}
                </select>
              </div>

              {subpage === 'notes' && (
                <div className="jdw-draft-card">
                  <div className="jdw-draft-header">Notes</div>
                  {parseNotesSegments(notesDraft).map((seg, idx) => (
                    seg.type === 'quote' ? (
                      <pre key={idx} className="notes-mail-quote">{seg.text}</pre>
                    ) : (
                      <React.Fragment key={idx}>
                        {idx > 0 && <div className="notes-answer-label">My answer</div>}
                        <textarea
                          className="cmd-select"
                          style={{ width: '100%', minHeight: idx === 0 ? '180px' : '90px' }}
                          value={seg.text}
                          onChange={e => updateNotesSegment(idx, e.target.value)}
                          placeholder={idx === 0 ? 'Add notes about this job…' : 'What should I say next time…'}
                        />
                      </React.Fragment>
                    )
                  ))}
                  <div className="jdw-draft-actions" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="inbox-message-meta">{notesDraft.length} chars</span>
                    <button className="cmd-cta cmd-cta-primary" onClick={handleSaveNotes} disabled={savingNotes}>
                      {savingNotes ? 'Saving…' : notesSaved ? 'Saved' : 'Save Notes'}
                    </button>
                  </div>
                </div>
              )}

              {subpage === 'progress' && (
                <div className="jdw-draft-card">
                  <div className="jdw-draft-header">Progress</div>
                  <select
                    value={selectedJob.status || 'Scanned'}
                    onChange={e => onStatusChange?.(selectedJob.id, e.target.value)}
                    className={`status-dropdown status-${(selectedJob.status || 'Scanned').toLowerCase().replace(' ', '-')}`}
                  >
                    {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  {selectedJob.status_updated_at && (
                    <div className="status-date">Updated {formatDate(selectedJob.status_updated_at)}</div>
                  )}
                </div>
              )}

              {subpage === 'emails' && (
                <div>
                  {!gmailConnected ? (
                    <div className="inbox-empty-state">Connect Gmail from the Inbox page to see mail for this job.</div>
                  ) : emailsLoading ? (
                    <div className="inbox-reader-empty">Loading mail…</div>
                  ) : emailsError ? (
                    <div className="inbox-error-banner">{emailsError}</div>
                  ) : emails.length === 0 ? (
                    <div className="inbox-empty-state">No mail found for {selectedJob.company_name}.</div>
                  ) : (
                    <div className="inbox-message-list">
                      {emails.map(msg => {
                        const vendorEmail = (selectedJob.vendor_contact_email || '').trim().toLowerCase();
                        const isSent = vendorEmail && (msg.to || '').toLowerCase().includes(vendorEmail);
                        const party = isSent
                          ? (msg.to || '').replace(/<.*>/, '').replace(/"/g, '').trim() || 'Unknown recipient'
                          : (msg.from || '').replace(/<.*>/, '').replace(/"/g, '').trim() || 'Unknown sender';
                        return (
                        <React.Fragment key={msg.id}>
                          <button className="inbox-message-row" onClick={() => handleOpenEmail(msg.id)}>
                            <span className="inbox-message-topline">
                              <span className="inbox-message-from">{isSent ? 'To: ' : ''}{party}</span>
                              {isSent && <span className="inbox-message-meta"> (sent)</span>}
                            </span>
                            <span className="inbox-message-subject">{msg.subject || '(no subject)'}</span>
                            <span className="inbox-message-snippet">{msg.snippet}</span>
                            <span className="inbox-message-meta">{formatDate(msg.date)}</span>
                          </button>
                          {openEmailId === msg.id && (
                            <div className="inbox-reader-body-wrap" style={{ padding: '0.75rem 1rem' }}>
                              {openEmailLoading ? 'Loading…' : (
                                <>
                                  <pre className="inbox-reader-body">{openEmailBody?.body || 'No readable plain text body found.'}</pre>
                                  <button
                                    className="inbox-secondary-btn"
                                    onClick={(e) => { e.stopPropagation(); handleAddEmailToNotes(msg); }}
                                  >
                                    {linkedEmailId === msg.id ? 'Added to Notes ✓' : 'Add to Notes'}
                                  </button>
                                </>
                              )}
                            </div>
                          )}
                        </React.Fragment>
                        );
                      })}
                    </div>
                  )}
                  <button className="inbox-secondary-btn" style={{ marginTop: '0.75rem' }} onClick={() => fetchEmails(selectedJob)} disabled={emailsLoading}>
                    Refresh
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

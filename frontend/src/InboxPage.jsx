import React, { useEffect, useRef, useState } from 'react';

const API_BASE = 'http://localhost:8000';
const DEFAULT_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'needs_attention', label: 'Needs Attention' },
  { key: 'verification', label: 'Verification' },
  { key: 'rejection', label: 'Rejection' },
  { key: 'interview', label: 'Interview' },
  { key: 'assessment', label: 'Assessment' },
  { key: 'reminder', label: 'Reminder' },
  { key: 'offer', label: 'Offer' },
  { key: 'applied', label: 'Applied' },
];

const PIPELINE_ACTIONS = [
  { key: 'applied', label: 'Mark Applied', status: 'Applied', reason: null },
  { key: 'interview', label: 'Mark Interview', status: 'Interviewing', reason: null },
  { key: 'assessment', label: 'Mark Assessment', status: 'Interviewing', reason: 'Assessment stage' },
  { key: 'offer', label: 'Mark Offer', status: 'Offered', reason: null },
  { key: 'rejected', label: 'Mark Rejected', status: 'Rejected', reason: 'Rejected by employer' },
];

// Mirrors backend JOB_LABELS in gmail_service.py — which inbox categories have a
// corresponding Gmail label to apply.
const LABELABLE_CATEGORIES = new Set(['interview', 'assessment', 'rejection', 'offer', 'applied']);

export default function InboxPage({ gmailConnected, gmailEmail, gmailCanOrganize, onRefreshStatus, onDisconnect, onOpenJob }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [activeFilter, setActiveFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('smart');
  const [messages, setMessages] = useState([]);
  const [nextPageToken, setNextPageToken] = useState(null);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [selectedMatch, setSelectedMatch] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [messageLoading, setMessageLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  // Tracks which message id is the CURRENT selection so async responses from a
  // message the user has since navigated away from (message body, thread, summary)
  // can detect they've been superseded and no-op instead of overwriting newer state.
  const activeMessageIdRef = useRef(null);
  // Bumped every time the message LIST is (re)requested for a new filter/query/mode
  // context. loadMore captures the generation it started with and discards its result
  // if the user has since switched filters — otherwise a slow "Load more" page for one
  // filter can land after the user switched filters and get appended to (and hand out
  // a page_token scoped to) an unrelated list.
  const queryGenerationRef = useRef(0);
  // Always-current filter/mode, read by the debounced search callback at FIRE time
  // instead of from its keystroke-time closure — otherwise switching filters while a
  // search debounce is pending lets the stale filter's fetch overwrite the newer one.
  const activeFilterRef = useRef(activeFilter);
  const modeRef = useRef(mode);
  useEffect(() => { activeFilterRef.current = activeFilter; }, [activeFilter]);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  const [thread, setThread] = useState(null);
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [replyDraft, setReplyDraft] = useState('');
  const [pipelineBusy, setPipelineBusy] = useState(null);
  const [pipelineMsg, setPipelineMsg] = useState('');
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftSaved, setDraftSaved] = useState(false);
  const [organizeBusy, setOrganizeBusy] = useState(null);
  const [organizeMsg, setOrganizeMsg] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/gmail/inbox/filters`)
      .then(res => res.json())
      .then(data => { if (data.filters?.length) setFilters(data.filters); })
      .catch(() => setFilters(DEFAULT_FILTERS));
  }, []);

  useEffect(() => {
    if (gmailConnected) fetchMessages(activeFilter, query, mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gmailConnected, activeFilter, mode]);

  const fetchMessages = async (category = activeFilter, search = query, useMode = mode) => {
    if (!gmailConnected) return;
    const myGen = ++queryGenerationRef.current;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ category, q: search || '', limit: '25', mode: useMode });
      const res = await fetch(`${API_BASE}/api/gmail/inbox?${params.toString()}`);
      const data = await res.json();
      if (queryGenerationRef.current !== myGen) return; // superseded by a newer filter/search
      if (!res.ok) throw new Error(data.detail || 'Failed to load Gmail messages');
      setMessages(data.messages || []);
      setNextPageToken(data.next_page_token || null);
      if (data.filters?.length) setFilters(data.filters);
    } catch (e) {
      if (queryGenerationRef.current === myGen) setError(e.message || 'Failed to load Gmail messages');
    } finally {
      if (queryGenerationRef.current === myGen) setLoading(false);
    }
  };

  const loadMore = async () => {
    if (!nextPageToken || loadingMore) return;
    const myGen = queryGenerationRef.current; // same context — must still match when the page lands
    setLoadingMore(true);
    try {
      const params = new URLSearchParams({ category: activeFilter, q: query || '', limit: '25', mode, page_token: nextPageToken });
      const res = await fetch(`${API_BASE}/api/gmail/inbox?${params.toString()}`);
      const data = await res.json();
      if (queryGenerationRef.current !== myGen) return; // filter/search changed while this page was loading
      if (!res.ok) throw new Error(data.detail || 'Failed to load more messages');
      setMessages(prev => [...prev, ...(data.messages || [])]);
      setNextPageToken(data.next_page_token || null);
    } catch (e) {
      if (queryGenerationRef.current === myGen) setError(e.message || 'Failed to load more messages');
    } finally {
      if (queryGenerationRef.current === myGen) setLoadingMore(false);
    }
  };

  const handleSearchChange = (value) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    // Read filter/mode from the refs at FIRE time (500ms later), not from this
    // closure's keystroke-time values — otherwise switching filters during the
    // debounce window still fires the search against the old filter.
    debounceRef.current = setTimeout(() => fetchMessages(activeFilterRef.current, value, modeRef.current), 500);
  };

  const resetReaderExtras = () => {
    setThread(null);
    setSummary(null);
    setSummaryLoading(false);
    setReplyDraft('');
    setPipelineMsg('');
    setDraftSaved(false);
    setOrganizeMsg('');
  };

  const openMessage = async (messageId, matchedApplication, category) => {
    activeMessageIdRef.current = messageId;
    setMessageLoading(true);
    setError(null);
    setSelectedMatch(matchedApplication || null);
    setSelectedCategory(category || null);
    resetReaderExtras();
    try {
      const res = await fetch(`${API_BASE}/api/gmail/message/${messageId}`);
      const data = await res.json();
      if (activeMessageIdRef.current !== messageId) return; // superseded by a newer selection
      if (!res.ok) throw new Error(data.detail || 'Failed to read message');
      setSelectedMessage(data);
      if (data.thread_id) {
        fetch(`${API_BASE}/api/gmail/thread/${data.thread_id}`)
          .then(r => r.json())
          .then(t => {
            if (activeMessageIdRef.current !== messageId) return; // superseded
            if (t.messages?.length > 1) setThread(t.messages);
          })
          .catch(() => {});
      }
    } catch (e) {
      if (activeMessageIdRef.current === messageId) setError(e.message || 'Failed to read message');
    } finally {
      if (activeMessageIdRef.current === messageId) setMessageLoading(false);
    }
  };

  const fetchSummary = async () => {
    if (!selectedMessage || summaryLoading) return summary;
    const forMessageId = selectedMessage.id;
    setSummaryLoading(true);
    try {
      const params = selectedMatch ? `?record_id=${selectedMatch.id}` : '';
      const res = await fetch(`${API_BASE}/api/gmail/message/${forMessageId}/summary${params}`);
      const data = await res.json();
      if (activeMessageIdRef.current !== forMessageId) return null; // superseded
      if (!res.ok) throw new Error(data.detail || 'Failed to summarize message');
      setSummary(data);
      return data;
    } catch (e) {
      if (activeMessageIdRef.current === forMessageId) setError(e.message || 'Failed to summarize message');
      return null;
    } finally {
      if (activeMessageIdRef.current === forMessageId) setSummaryLoading(false);
    }
  };

  const handleGenerateReply = async () => {
    const s = summary || await fetchSummary();
    if (s?.reply_suggestion) setReplyDraft(s.reply_suggestion);
  };

  const handleSaveDraft = async () => {
    if (!replyDraft.trim() || !selectedMessage) return;
    setSavingDraft(true);
    setDraftSaved(false);
    try {
      const toEmail = extractEmail(selectedMessage.from);
      const res = await fetch(`${API_BASE}/api/gmail/save-draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to_emails: toEmail ? [toEmail] : [],
          subject: selectedMessage.subject?.startsWith('Re:') ? selectedMessage.subject : `Re: ${selectedMessage.subject || ''}`,
          body: replyDraft,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save draft');
      setDraftSaved(true);
    } catch (e) {
      setError(e.message || 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
  };

  const handlePipelineAction = async (action) => {
    if (!selectedMatch || pipelineBusy) return;
    setPipelineBusy(action.key);
    setPipelineMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${selectedMatch.id}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: action.status, rejection_reason: action.reason }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update job status');
      setPipelineMsg(`${action.label} — pipeline updated.`);
    } catch (e) {
      setPipelineMsg(e.message || 'Failed to update job status');
    } finally {
      setPipelineBusy(null);
    }
  };

  const handleApplyLabel = async () => {
    if (!selectedMessage || !selectedCategory || organizeBusy) return;
    setOrganizeBusy('label');
    setOrganizeMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/gmail/message/${selectedMessage.id}/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: selectedCategory }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to apply label');
      setOrganizeMsg(`Labeled "${data.label}".`);
    } catch (e) {
      setOrganizeMsg(e.message || 'Failed to apply label');
    } finally {
      setOrganizeBusy(null);
    }
  };

  const handleArchive = async () => {
    if (!selectedMessage || organizeBusy) return;
    setOrganizeBusy('archive');
    setOrganizeMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/gmail/message/${selectedMessage.id}/archive`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to archive');
      setOrganizeMsg('Archived.');
    } catch (e) {
      setOrganizeMsg(e.message || 'Failed to archive');
    } finally {
      setOrganizeBusy(null);
    }
  };

  const handleMarkRead = async () => {
    if (!selectedMessage || organizeBusy) return;
    setOrganizeBusy('read');
    setOrganizeMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/gmail/message/${selectedMessage.id}/mark-read`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to mark read');
      setOrganizeMsg('Marked read.');
    } catch (e) {
      setOrganizeMsg(e.message || 'Failed to mark read');
    } finally {
      setOrganizeBusy(null);
    }
  };

  return (
    <div className="inbox-page">
      <div className="inbox-header">
        <div>
          <h1 className="inbox-title">Inbox</h1>
          <p className="inbox-subtitle">Gmail search for job replies, application updates, and recruiter messages.</p>
        </div>
        <div className="inbox-account-box">
          {gmailConnected ? (
            <>
              <span className="inbox-account-dot" />
              <span className="inbox-account-email">{gmailEmail || 'Gmail connected'}</span>
              <button className="inbox-secondary-btn" onClick={onDisconnect}>Disconnect</button>
            </>
          ) : (
            <a className="inbox-primary-btn" href={`${API_BASE}/api/gmail/auth`}>Connect Gmail</a>
          )}
        </div>
      </div>

      {!gmailConnected ? (
        <div className="inbox-connect-panel">
          <h2>Connect Gmail</h2>
          <p>Grants read access (to search and open messages) and compose access (to save draft replies) — nothing more, no archiving or deleting. Each page of results is sorted by AI in a single batched call — not one call per email — so it reads what you actually filtered for while staying a fraction of a cent per load.</p>
          <a className="inbox-primary-btn" href={`${API_BASE}/api/gmail/auth`}>Connect Gmail</a>
        </div>
      ) : (
        <>
          <div className="inbox-toolbar">
            <div className="inbox-filter-row">
              {filters.map(filter => (
                <button
                  key={filter.key}
                  className={`inbox-filter-chip ${activeFilter === filter.key ? 'active' : ''}`}
                  onClick={() => { setActiveFilter(filter.key); setSelectedMessage(null); resetReaderExtras(); }}
                >
                  {filter.label}
                </button>
              ))}
              <div className="inbox-mode-toggle" title="Smart mode uses one batched AI call per page for accurate sorting. Cheap mode uses Gmail keyword search + local rules only — zero AI cost.">
                <button
                  className={`inbox-mode-btn ${mode === 'cheap' ? 'active' : ''}`}
                  onClick={() => setMode('cheap')}
                >
                  Cheap
                </button>
                <button
                  className={`inbox-mode-btn ${mode === 'smart' ? 'active' : ''}`}
                  onClick={() => setMode('smart')}
                >
                  Smart
                </button>
              </div>
            </div>
            <div className="inbox-search-box">
              <input
                value={query}
                onChange={e => handleSearchChange(e.target.value)}
                placeholder="Search company, sender, role, keyword..."
              />
              <button onClick={() => fetchMessages(activeFilter, query, mode)} disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
            </div>
          </div>

          {error && <div className="inbox-error-banner">{error}</div>}

          <div className="inbox-layout">
            <section className="inbox-list-panel">
              <div className="inbox-list-head">
                <span>{loading ? 'Loading messages...' : `${messages.length} message${messages.length === 1 ? '' : 's'}`}</span>
                <button className="inbox-secondary-btn" onClick={() => fetchMessages(activeFilter, query, mode)} disabled={loading}>Refresh</button>
              </div>
              {messages.length === 0 && !loading ? (
                <div className="inbox-empty-state">No messages found for this filter.</div>
              ) : (
                <>
                  <div className="inbox-message-list">
                    {messages.map(msg => (
                      <button
                        key={msg.id}
                        className={`inbox-message-row ${selectedMessage?.id === msg.id ? 'selected' : ''}`}
                        onClick={() => openMessage(msg.id, msg.matched_application, msg.category)}
                      >
                        <span className="inbox-message-topline">
                          <span className="inbox-message-from">{cleanSender(msg.from)}</span>
                          <span className="inbox-category-pill">{msg.category_label || 'All'}</span>
                        </span>
                        <span className="inbox-message-subject">{msg.subject || '(no subject)'}</span>
                        {msg.matched_application && (
                          <span className="inbox-match-pill">Applied: {msg.matched_application.company}</span>
                        )}
                        <span className="inbox-message-snippet">{msg.snippet}</span>
                        <span className="inbox-message-meta">
                          {formatDate(msg.date)} · {msg.classified_by === 'ai' ? 'AI-sorted' : msg.classified_by === 'local-rules' ? `${Math.round((msg.category_confidence || 0) * 100)}% keyword match` : 'cached'}
                        </span>
                      </button>
                    ))}
                  </div>
                  {nextPageToken && (
                    <button className="inbox-secondary-btn inbox-load-more" onClick={loadMore} disabled={loadingMore}>
                      {loadingMore ? 'Loading...' : 'Load more'}
                    </button>
                  )}
                </>
              )}
            </section>

            <section className="inbox-reader-panel">
              {messageLoading ? (
                <div className="inbox-reader-empty">Reading message...</div>
              ) : selectedMessage ? (
                <>
                  <div className="inbox-reader-header">
                    <div>
                      <div className="inbox-reader-subject">{selectedMessage.subject || '(no subject)'}</div>
                      <div className="inbox-reader-from">{selectedMessage.from}</div>
                    </div>
                    <div className="inbox-reader-date">{formatDate(selectedMessage.date)}</div>
                  </div>

                  {selectedMatch && onOpenJob && (
                    <div className="inbox-match-banner">
                      <span>This looks like a reply from <strong>{selectedMatch.company}</strong>{selectedMatch.title ? ` (${selectedMatch.title})` : ''} — you applied there.</span>
                      <button className="inbox-primary-btn" onClick={() => onOpenJob(selectedMatch.id)}>Open Job</button>
                    </div>
                  )}

                  {selectedMatch && (
                    <div className="inbox-pipeline-row">
                      {PIPELINE_ACTIONS.map(action => (
                        <button
                          key={action.key}
                          className="inbox-secondary-btn"
                          onClick={() => handlePipelineAction(action)}
                          disabled={pipelineBusy === action.key}
                        >
                          {pipelineBusy === action.key ? '…' : action.label}
                        </button>
                      ))}
                      {pipelineMsg && <span className="inbox-pipeline-confirm">{pipelineMsg}</span>}
                    </div>
                  )}

                  <div className="inbox-organize-row">
                    {gmailCanOrganize ? (
                      <>
                        {LABELABLE_CATEGORIES.has(selectedCategory) && (
                          <button className="inbox-secondary-btn" onClick={handleApplyLabel} disabled={organizeBusy === 'label'}>
                            {organizeBusy === 'label' ? '…' : `Label as Job/${capitalize(selectedCategory)}`}
                          </button>
                        )}
                        <button className="inbox-secondary-btn" onClick={handleMarkRead} disabled={organizeBusy === 'read'}>
                          {organizeBusy === 'read' ? '…' : 'Mark Read'}
                        </button>
                        <button className="inbox-secondary-btn" onClick={handleArchive} disabled={organizeBusy === 'archive'}>
                          {organizeBusy === 'archive' ? '…' : 'Archive'}
                        </button>
                        {organizeMsg && <span className="inbox-pipeline-confirm">{organizeMsg}</span>}
                      </>
                    ) : (
                      <span className="inbox-organize-hint">
                        Labels/archive need organize permission — <a href={`${API_BASE}/api/gmail/auth`}>reconnect Gmail</a> to enable.
                      </span>
                    )}
                  </div>

                  <div className="inbox-summary-row">
                    <button className="inbox-secondary-btn" onClick={fetchSummary} disabled={summaryLoading}>
                      {summaryLoading ? 'Summarizing...' : summary ? 'Re-summarize' : 'What happened? (AI summary)'}
                    </button>
                    <button className="inbox-secondary-btn" onClick={handleGenerateReply} disabled={summaryLoading}>
                      Generate Reply
                    </button>
                  </div>

                  {summary && (
                    <div className="inbox-summary-card">
                      <div className="inbox-summary-field"><span className="inbox-summary-label">What happened</span>{summary.what_happened}</div>
                      <div className="inbox-summary-field"><span className="inbox-summary-label">Required action</span>{summary.required_action || 'None'}</div>
                      {summary.interview_date && <div className="inbox-summary-field"><span className="inbox-summary-label">Interview date</span>{summary.interview_date}</div>}
                      {summary.deadline && <div className="inbox-summary-field"><span className="inbox-summary-label">Deadline</span>{summary.deadline}</div>}
                      {summary.recruiter_email && <div className="inbox-summary-field"><span className="inbox-summary-label">Recruiter email</span>{summary.recruiter_email}</div>}
                      {summary.reply_intent && summary.reply_intent !== 'none' && <div className="inbox-summary-field"><span className="inbox-summary-label">Suggested reply intent</span>{summary.reply_intent}</div>}
                    </div>
                  )}

                  {replyDraft && (
                    <div className="inbox-reply-card">
                      <textarea
                        className="inbox-reply-textarea"
                        value={replyDraft}
                        onChange={e => setReplyDraft(e.target.value)}
                        rows={5}
                      />
                      <button className="inbox-primary-btn" onClick={handleSaveDraft} disabled={savingDraft}>
                        {savingDraft ? 'Saving...' : draftSaved ? 'Saved to Gmail Drafts' : 'Save Draft to Gmail'}
                      </button>
                    </div>
                  )}

                  {thread ? (
                    <div className="inbox-thread">
                      <div className="inbox-thread-label">Full conversation ({thread.length} messages)</div>
                      {thread.map((tm, i) => (
                        <div key={tm.id || i} className="inbox-thread-message">
                          <div className="inbox-thread-message-head">
                            <span className="inbox-reader-from">{tm.from}</span>
                            <span className="inbox-reader-date">{formatDate(tm.date)}</span>
                          </div>
                          <pre className="inbox-reader-body">{tm.body || '(empty)'}</pre>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <pre className="inbox-reader-body">{selectedMessage.body || 'No readable plain text body found.'}</pre>
                  )}
                </>
              ) : (
                <div className="inbox-reader-empty">Select a message to read it here.</div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function cleanSender(sender) {
  return (sender || 'Unknown sender').replace(/<.*>/, '').replace(/"/g, '').trim() || 'Unknown sender';
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}

function extractEmail(sender) {
  const m = (sender || '').match(/<([^>]+)>/);
  if (m) return m[1];
  return (sender || '').trim();
}

function formatDate(value) {
  if (!value) return 'No date';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

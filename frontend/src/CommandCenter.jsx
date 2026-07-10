import React, { useState, useEffect } from 'react';
import './index.css';
import JobDetailWorkspace from './JobDetailWorkspace';

export default function CommandCenter({ onSendToTailor, onSaveToApplications, onViewAllMatches, selectedResumeName, onChangeResume, initialJobId, onConsumeInitialJobId }) {
  const [selectedJobId, setSelectedJobId] = useState(null);

  // Lets other pages (e.g. Inbox) deep-link into a specific job's workspace here.
  useEffect(() => {
    if (initialJobId) {
      setSelectedJobId(initialJobId);
      onConsumeInitialJobId && onConsumeInitialJobId();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialJobId]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchStatus, setSearchStatus] = useState(null);
  const [searchQuery, setSearchQuery] = useState('DevOps Engineer');
  const [platforms, setPlatforms] = useState({ linkedin: true, dice: true, indeed: true, ziprecruiter: true });
  const [workTypes, setWorkTypes] = useState({ remote: true, hybrid: false, onsite: false });
  const [contractTypes, setContractTypes] = useState({ w2: false, c2c: true, c2h: true });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [addJobOpen, setAddJobOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [checkingInbox, setCheckingInbox] = useState(false);

  useEffect(() => {
    fetchDashboard();
  }, []);


  const handlePlatformChange = (platform) => {
    setPlatforms(prev => ({ ...prev, [platform]: !prev[platform] }));
  };

  const handleWorkTypeChange = (type) => {
    setWorkTypes(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const handleContractTypeChange = (type) => {
    setContractTypes(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const handleDismissInboxReply = async (messageId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/command-center/inbox-replies/${messageId}/dismiss`, { method: 'POST' });
      if (!res.ok) {
        setSearchStatus({ type: 'error', message: 'Failed to dismiss that reply — try again.' });
        return;
      }
      fetchDashboard();
    } catch {
      setSearchStatus({ type: 'error', message: 'Failed to reach the server.' });
    }
  };

  const handleCheckInboxNow = async () => {
    if (checkingInbox) return;
    setCheckingInbox(true);
    try {
      await fetch('http://localhost:8000/api/command-center/inbox-replies/check', { method: 'POST' });
      await fetchDashboard();
    } catch { /* ignore */ } finally {
      setCheckingInbox(false);
    }
  };

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const res = await fetch('http://localhost:8000/api/command-center/dashboard');
      if (!res.ok) throw new Error('Failed to load dashboard');
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAutoSearch = async () => {
    if (!searchQuery.trim() || searching) return;

    setSearching(true);
    setSearchStatus(null);

    try {
      const res = await fetch('http://localhost:8000/api/jobs/auto-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery.trim(),
          platforms: Object.keys(platforms).filter(p => platforms[p]),
          work_types: Object.keys(workTypes).filter(t => workTypes[t]),
          contract_types: Object.keys(contractTypes).filter(t => contractTypes[t])
        })
      });

      if (res.status === 429) {
        setSearchStatus({ type: 'error', message: "You're searching too often — wait a minute and try again." });
        return;
      }

      const json = await res.json();

      if (!res.ok) {
        setSearchStatus({ type: 'error', message: json.detail || 'Search failed. Please try again.' });
        return;
      }

      const jobs = json.jobs || [];
      if (jobs.length === 0) {
        setSearchStatus({ type: 'empty', message: json.message || `No jobs found for "${searchQuery.trim()}".` });
        return;
      }

      const jobsWithLinks = jobs.map(j => ({ ...j, description: j.description || j.title }));
      setData(prev => {
        const existingKeys = new Set(jobsWithLinks.map(j => `${j.company}|${j.title}`));
        const rest = (prev.top_jobs || []).filter(j => !existingKeys.has(`${j.company}|${j.title}`));
        return { ...prev, top_jobs: [...jobsWithLinks, ...rest].slice(0, 5) };
      });
      setSearchStatus({ type: 'success', message: `Found ${jobs.length} job${jobs.length !== 1 ? 's' : ''} for "${searchQuery.trim()}".` });
    } catch (err) {
      console.error('Auto search failed', err);
      setSearchStatus({ type: 'error', message: 'Failed to reach the server. Check your connection and try again.' });
    } finally {
      setSearching(false);
    }
  };

  const handleTailorBestMatch = () => {
    const best = data?.top_jobs?.[0];
    if (best && onSendToTailor) onSendToTailor(best.description || best.title);
  };

  if (loading) return <div className="cmd-loading">Loading Command Center...</div>;
  if (error) return <div className="cmd-error">Error: {error}</div>;
  if (!data) return null;

  const actionItemsTotal = data.action_queue
    ? Object.values(data.action_queue).reduce((sum, bucket) => sum + (bucket?.count || 0), 0)
    : 0;

  const notifItems = data.action_queue
    ? ACTION_QUEUE_SECTIONS.flatMap(section => {
        const bucket = data.action_queue[section.key] || { items: [] };
        return (bucket.items || []).map(item => ({ ...item, sectionTitle: section.title, sectionKey: section.key }));
      }).slice(0, 8)
    : [];

  // inbox_replies items don't have an `id` field at all (see database entries built by
  // services/inbox_matcher.py) — their job-record id is `record_id`, with `message_id`
  // as their own unique identity. Every other section's items use `id` directly.
  const notifItemOpenId = (item) => (item.sectionKey === 'inbox_replies' ? item.record_id : item.id);
  const notifItemKey = (item) => `${item.sectionKey}-${item.sectionKey === 'inbox_replies' ? item.message_id : item.id}`;

  const openNotifItem = (item) => {
    setNotifOpen(false);
    setSelectedJobId(notifItemOpenId(item));
  };

  return (
    <div className="cmd-container">
      {/* Header */}
      <div className="cmd-header">
        <div>
          <h1 className="cmd-title">Command Center</h1>
          <p className="cmd-subtitle">Your AI-powered job search command center</p>
        </div>
        <div className="cmd-controls">
          <select className="cmd-select">
            <option>Date range: This Week</option>
            <option>Date range: This Month</option>
          </select>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
            <div style={{ position: 'relative' }}>
              <button 
                className={`cmd-filter-pill ${filtersOpen ? 'active' : ''}`} 
                onClick={() => setFiltersOpen(!filtersOpen)}
                style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', background: filtersOpen ? 'var(--surface)' : 'transparent' }}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
                Filters
              </button>
              
              {filtersOpen && (
                <div style={{ 
                  position: 'absolute', top: '100%', right: 0, marginTop: '0.5rem', 
                  background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '8px', 
                  padding: '1.25rem', display: 'flex', gap: '2rem', zIndex: 10,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.8)', minWidth: '350px'
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', flex: 1 }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginBottom: '0.2rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Job Boards</div>
                    {['linkedin', 'dice', 'indeed', 'ziprecruiter'].map(p => (
                      <button 
                        key={p} 
                        className={`cmd-filter-pill ${platforms[p] ? 'active' : ''}`}
                        onClick={() => handlePlatformChange(p)}
                        style={{ width: '100%', textAlign: 'left', justifyContent: 'flex-start' }}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', flex: 1 }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginBottom: '0.2rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Work Type</div>
                    {['remote', 'hybrid', 'onsite'].map(t => (
                      <button 
                        key={t} 
                        className={`cmd-filter-pill ${workTypes[t] ? 'active' : ''}`}
                        onClick={() => handleWorkTypeChange(t)}
                        style={{ width: '100%', textAlign: 'left', justifyContent: 'flex-start' }}
                      >
                        {t}
                      </button>
                    ))}
                    
                    <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginTop: '0.5rem', marginBottom: '0.2rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Contract</div>
                    {['w2', 'c2c', 'c2h'].map(c => (
                      <button 
                        key={c} 
                        className={`cmd-filter-pill ${contractTypes[c] ? 'active' : ''}`}
                        onClick={() => handleContractTypeChange(c)}
                        style={{ width: '100%', textAlign: 'left', justifyContent: 'flex-start', textTransform: 'uppercase' }}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleAutoSearch(); }}
                placeholder="e.g. Senior Backend Engineer"
                className="cmd-select"
                style={{ minWidth: '220px' }}
                disabled={searching}
              />
              <button
                className="cmd-filter-pill"
                onClick={handleAutoSearch}
                disabled={searching || !searchQuery.trim()}
                style={{ padding: '0.5rem 1rem', opacity: searching || !searchQuery.trim() ? 0.6 : 1 }}
              >
                {searching ? 'Searching...' : 'Search Jobs'}
              </button>
            </div>
          </div>
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              className="cmd-bell"
              onClick={() => setNotifOpen(o => !o)}
              title={actionItemsTotal > 0 ? `${actionItemsTotal} item${actionItemsTotal !== 1 ? 's' : ''} need attention` : 'No items need attention right now'}
              aria-label="Notifications"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
              </svg>
              {actionItemsTotal > 0 && <span className="cmd-bell-badge">{actionItemsTotal > 99 ? '99+' : actionItemsTotal}</span>}
            </button>

            {notifOpen && (
              <div className="cmd-notif-popup">
                <div className="cmd-notif-popup-header">
                  <span>Notifications</span>
                  <button type="button" className="cmd-notif-popup-close" onClick={() => setNotifOpen(false)} aria-label="Close">&times;</button>
                </div>
                {notifItems.length === 0 ? (
                  <div className="cmd-notif-popup-empty">Nothing needs your attention right now.</div>
                ) : (
                  <div className="cmd-notif-popup-list">
                    {notifItems.map(item => (
                      <button
                        type="button"
                        key={notifItemKey(item)}
                        className="cmd-notif-popup-item"
                        onClick={() => openNotifItem(item)}
                      >
                        <span className="cmd-notif-popup-item-section">{item.sectionTitle}</span>
                        <span className="cmd-notif-popup-item-title">
                          {truncate(item.company, 28)}{item.title ? ` · ${truncate(item.title, 32)}` : ''}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="cmd-notif-popup-viewall"
                  onClick={() => {
                    setNotifOpen(false);
                    document.getElementById('cmd-action-queue')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                >
                  View all in Action Queue
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Context bar: active resume + last scan status */}
      <ContextBar
        selectedResumeName={selectedResumeName}
        onChangeResume={onChangeResume}
        lastScan={data.last_scan}
      />

      {/* Primary CTA row */}
      <div className="cmd-cta-row">
        <button className="cmd-cta cmd-cta-secondary" onClick={() => setAddJobOpen(true)}>
          <PlusIcon /> Add Job
        </button>
        <button
          className="cmd-cta cmd-cta-secondary"
          onClick={handleAutoSearch}
          disabled={searching || !searchQuery.trim()}
          style={{ opacity: searching || !searchQuery.trim() ? 0.6 : 1 }}
        >
          <SearchIcon /> {searching ? 'Scoring Jobs...' : 'Score Jobs'}
        </button>
        <button
          className="cmd-cta cmd-cta-primary"
          onClick={handleTailorBestMatch}
          disabled={!data.top_jobs || data.top_jobs.length === 0}
          style={{ opacity: !data.top_jobs || data.top_jobs.length === 0 ? 0.5 : 1 }}
        >
          <BoltIcon /> Tailor Best Match{data.top_jobs && data.top_jobs[0] ? ` — ${data.top_jobs[0].company}` : ''}
        </button>
      </div>

      {addJobOpen && (
        <AddJobModal
          onClose={() => setAddJobOpen(false)}
          onSaved={() => { setAddJobOpen(false); fetchDashboard(); }}
        />
      )}

      {/* Metrics Row */}
      <div className="cmd-metrics-grid">
        <MetricCard icon="briefcase" title="New jobs found" value={data.metrics.new_jobs} trend="" trendType="up" />
        <MetricCard icon="star" title="Strong matches" value={data.metrics.strong_matches} trend="" trendType="up" />
        <MetricCard icon="clock" title="Applications pending" value={data.metrics.apps_pending} trend="" trendType="neutral" />
        <MetricCard icon="calendar" title="Follow-ups due" value={data.metrics.follow_ups} trend="" trendType="up" />
      </div>

      {searchStatus && (
        <div
          className={searchStatus.type === 'error' ? 'error-banner' : 'cmd-search-status'}
          style={{
            marginTop: '1.5rem',
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            color: searchStatus.type === 'error' ? 'var(--danger)' : searchStatus.type === 'success' ? 'var(--success)' : 'var(--muted)',
          }}
        >
          {searchStatus.type === 'error' ? '! ' : ''}{searchStatus.message}
        </div>
      )}

      {/* Jobs Found */}
      {data.top_jobs && data.top_jobs.length > 0 ? (
        <div className="cmd-panel" style={{ marginTop: '2rem' }}>
          <div className="cmd-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>Latest Job Matches {searching && <span style={{ color: 'var(--gold)', fontSize: '0.9rem' }}>Searching...</span>}</h2>
            <button className="cmd-view-all-btn" onClick={() => onViewAllMatches && onViewAllMatches()}>
              View All Matches &rarr;
            </button>
          </div>
          <div className="cmd-jobs-list" style={{ display: 'flex', flexDirection: 'column' }}>
            {data.top_jobs.map((job, idx) => (
              <JobRow key={idx} index={idx + 1} job={job} onSendToTailor={onSendToTailor} onSaveToApplications={onSaveToApplications} onOpenDetail={(j) => setSelectedJobId(j.record_id)} />
            ))}
          </div>
        </div>
      ) : (
        <div className="cmd-empty-state">
          <div className="cmd-empty-title">Your pipeline is empty — let's fix that.</div>
          <div className="cmd-empty-hint">Pick whichever step you're on. Each one only takes a minute.</div>
          <div className="cmd-empty-actions">
            <button className="cmd-cta cmd-cta-secondary" onClick={handleAutoSearch} disabled={searching}>
              <SearchIcon /> Import your first job
            </button>
            <button className="cmd-cta cmd-cta-secondary" onClick={() => onChangeResume && onChangeResume()}>
              <ResumeIcon /> Upload / select resume
            </button>
            <button className="cmd-cta cmd-cta-secondary" onClick={handleAutoSearch} disabled={searching}>
              <StarIcon /> Score a job
            </button>
            <button className="cmd-cta cmd-cta-secondary" onClick={() => setAddJobOpen(true)}>
              <PlusIcon /> Track an application
            </button>
          </div>
        </div>
      )}

      {/* Pipeline Overview + Action Queue — side by side when there's room, stacked otherwise */}
      <div className="cmd-two-col-row" id="cmd-action-queue">
        {data.pipeline && <PipelineOverview pipeline={data.pipeline} />}
        {data.action_queue && (
          <ActionQueue
            actionQueue={data.action_queue}
            onOpenItem={(id) => setSelectedJobId(id)}
            onDismissInboxReply={handleDismissInboxReply}
            onCheckInboxNow={handleCheckInboxNow}
            checkingInbox={checkingInbox}
          />
        )}
      </div>

      {/* Automation status + Job source health + Career intel */}
      <div className="cmd-three-col-row">
        {data.automation && <AutomationStatus automation={data.automation} />}
        {data.job_source_health && <JobSourceHealth breakdown={data.job_source_health} />}
        {data.career_intel && <CareerIntel intel={data.career_intel} />}
      </div>

      <JobDetailWorkspace
        jobId={selectedJobId}
        onClose={() => setSelectedJobId(null)}
        onSendToTailor={onSendToTailor}
        onSaveToApplications={onSaveToApplications}
        onJobUpdated={fetchDashboard}
        selectedResumeName={selectedResumeName}
      />
    </div>
  );
}

function PlusIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2.5" fill="none"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>;
}
function SearchIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2.5" fill="none"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>;
}
function BoltIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2.5" fill="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>;
}
function ResumeIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2.5" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>;
}
function StarIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2.5" fill="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>;
}

function ContextBar({ selectedResumeName, onChangeResume, lastScan }) {
  const scanText = lastScan
    ? `Last job scan: ${formatRelativeTime(lastScan.timestamp)}`
    : 'Last job scan: never — run a search to get started';
  const sourcesText = lastScan && lastScan.platforms && lastScan.platforms.length > 0
    ? `Sources checked: ${lastScan.platforms.map(p => PLATFORM_LABELS[p] || p).join(', ')}`
    : null;

  return (
    <div className="cmd-context-bar">
      <div className="cmd-context-item">
        <ResumeIcon />
        <span className="cmd-context-label">Active resume:</span>
        <span className="cmd-context-value">{selectedResumeName || 'None selected'}</span>
        <button className="cmd-context-change" onClick={() => onChangeResume && onChangeResume()}>Change</button>
      </div>
      <div className="cmd-context-sep" />
      <div className="cmd-context-item">
        <ClockIcon />
        <span className="cmd-context-value">{scanText}</span>
        {sourcesText && <span className="cmd-context-sub"> &middot; {sourcesText}</span>}
      </div>
    </div>
  );
}

function ClockIcon() {
  return <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>;
}

const PLATFORM_LABELS = { linkedin: 'LinkedIn', dice: 'Dice', indeed: 'Indeed', ziprecruiter: 'ZipRecruiter' };

function formatRelativeTime(iso) {
  if (!iso) return 'never';
  const then = new Date(iso);
  const now = new Date();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const sameDay = then.toDateString() === now.toDateString();
  const timeStr = then.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (sameDay) return `Today ${timeStr}`;
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (then.toDateString() === yesterday.toDateString()) return `Yesterday ${timeStr}`;
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays < 7) return `${diffDays}d ago`;
  return then.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function AddJobModal({ onClose, onSaved }) {
  const [company, setCompany] = useState('');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const handleSave = async () => {
    if (!company.trim() || !title.trim()) { setErr('Company and title are required.'); return; }
    setSaving(true);
    setErr(null);
    try {
      const res = await fetch('http://localhost:8000/api/jobs/manual-add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: company.trim(), title: title.trim(), url: url.trim(), notes: notes.trim() }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || 'Failed to save job');
      }
      onSaved && onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cmd-modal-backdrop" onClick={onClose}>
      <div className="cmd-modal" onClick={e => e.stopPropagation()}>
        <div className="cmd-modal-header">
          <h3>Add Job</h3>
          <button className="cmd-modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="cmd-modal-body">
          <label className="cmd-modal-label">Company *</label>
          <input className="cmd-select" style={{ width: '100%' }} value={company} onChange={e => setCompany(e.target.value)} placeholder="e.g. Acme Corp" />
          <label className="cmd-modal-label">Job Title *</label>
          <input className="cmd-select" style={{ width: '100%' }} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Senior DevOps Engineer" />
          <label className="cmd-modal-label">Posting URL</label>
          <input className="cmd-select" style={{ width: '100%' }} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
          <label className="cmd-modal-label">Notes</label>
          <textarea className="cmd-select" style={{ width: '100%', minHeight: '70px', resize: 'vertical' }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes" />
          {err && <div className="cmd-modal-error">{err}</div>}
        </div>
        <div className="cmd-modal-footer">
          <button className="cmd-filter-pill" onClick={onClose}>Cancel</button>
          <button className="cmd-cta cmd-cta-primary" onClick={handleSave} disabled={saving} style={{ opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Saving...' : 'Save Job'}
          </button>
        </div>
      </div>
    </div>
  );
}

const PIPELINE_STAGES = [
  {
    key: 'Discovered', color: '#818cf8',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>,
  },
  {
    key: 'Matched', color: '#c89b3c',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="12" r="9"></circle><path d="M8.5 12.5l2.5 2.5 4.5-5"></path></svg>,
  },
  {
    key: 'Saved', color: '#38bdf8',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>,
  },
  {
    key: 'Applied', color: '#a78bfa',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>,
  },
  {
    key: 'Interview', color: '#2ebd73',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>,
  },
  {
    key: 'Offer', color: '#facc15',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="8" r="6"></circle><path d="M15.5 13.3L17 22l-5-3-5 3 1.5-8.7"></path></svg>,
  },
  {
    key: 'Rejected', color: '#d94f4f',
    icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="12" r="9"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>,
  },
];

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
}

function PipelineOverview({ pipeline }) {
  const total = PIPELINE_STAGES.reduce((sum, s) => sum + (pipeline[s.key] || 0), 0);
  return (
    <div className="cmd-panel cmd-pipeline-panel">
      <div className="cmd-panel-header" style={{ marginBottom: '1.25rem' }}>
        <h2 style={{ margin: 0 }}>Pipeline Overview</h2>
        <span className="cmd-pipeline-total">{total} tracked</span>
      </div>
      <div className="cmd-pipeline-row">
        {PIPELINE_STAGES.map((stage, i) => {
          const count = pipeline[stage.key] || 0;
          const pct = total ? Math.round((count / total) * 100) : 0;
          const rgb = hexToRgb(stage.color);
          return (
            <div
              key={stage.key}
              className="cmd-pipeline-stage"
              style={{ '--stage-color': stage.color, '--stage-rgb': rgb, animationDelay: `${i * 60}ms` }}
            >
              <div className="cmd-pipeline-icon">{stage.icon}</div>
              <div className="cmd-pipeline-count">{count}</div>
              <div className="cmd-pipeline-label">{stage.key}</div>
              <div className="cmd-pipeline-bar-track">
                <div className="cmd-pipeline-bar-fill" style={{ width: `${Math.max(count ? 6 : 0, pct)}%` }} />
              </div>
              <div className="cmd-pipeline-pct">{pct}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function truncate(str, maxLen) {
  if (!str) return '';
  const oneLine = str.replace(/\s+/g, ' ').trim();
  return oneLine.length > maxLen ? oneLine.slice(0, maxLen).trimEnd() + '…' : oneLine;
}

const ACTION_QUEUE_SECTIONS = [
  { key: 'needing_description', title: 'Jobs Needing Description', hint: 'Description too thin to tailor against — go pull the full posting.' },
  { key: 'ready_to_tailor', title: 'Ready to Tailor', hint: 'Saved with a full description — ready to generate a tailored resume.' },
  { key: 'cover_letters_waiting', title: 'Cover Letters Waiting', hint: 'A cover letter was generated — still not applied.' },
  { key: 'email_drafts_waiting', title: 'Email Drafts Waiting', hint: 'Follow-up/outreach drafts saved and waiting on your review.' },
  { key: 'tailored_not_applied', title: 'Tailored, Not Applied', hint: 'A tailored resume exists but the application was never sent.' },
  { key: 'follow_ups_due', title: 'Follow-ups Due', hint: 'Applied 7+ days ago with no update — time to check in.' },
  { key: 'inbox_replies', title: 'Inbox Replies', hint: 'A company you applied to just emailed you — click to open and follow up.' },
];

function ActionQueue({ actionQueue, onOpenItem, onDismissInboxReply, onCheckInboxNow, checkingInbox }) {
  return (
    <div className="cmd-panel">
      <div className="cmd-panel-header" style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Action Queue</h2>
      </div>
      <div className="cmd-action-queue-grid">
        {ACTION_QUEUE_SECTIONS.map(section => {
          const bucket = actionQueue[section.key] || { count: 0, items: [] };
          const isFollowUps = section.key === 'follow_ups_due';
          const isInboxReplies = section.key === 'inbox_replies';
          return (
            <div key={section.key} className="cmd-action-card">
              <div className="cmd-action-card-header">
                <span className="cmd-action-card-title">{section.title}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {isInboxReplies && onCheckInboxNow ? (
                    <button
                      className="cmd-action-card-refresh"
                      onClick={onCheckInboxNow}
                      disabled={checkingInbox}
                      title="Check inbox for new replies now"
                    >
                      {checkingInbox ? '…' : '↻'}
                    </button>
                  ) : null}
                  <span className="cmd-action-card-count">{bucket.count}</span>
                </span>
              </div>
              <div className="cmd-action-card-hint">{section.hint}</div>
              {bucket.items && bucket.items.length > 0 ? (
                <ul className="cmd-action-card-list">
                  {bucket.items.map(item => (
                    <li
                      key={isInboxReplies ? item.message_id : item.id}
                      title={`${item.company || ''}${item.title ? ' · ' + item.title : ''}`}
                      onClick={() => onOpenItem && onOpenItem(isInboxReplies ? item.record_id : item.id)}
                      style={onOpenItem ? { cursor: 'pointer' } : undefined}
                    >
                      <span className="cmd-action-item-company">{truncate(item.company, 24)}</span>
                      {isFollowUps ? (
                        <span className="cmd-action-item-title">
                          {' '}&middot; follow up {item.days_since != null ? `(${item.days_since}d)` : ''}
                          {item.has_draft ? <span className="cmd-action-item-badge">draft ready</span> : null}
                        </span>
                      ) : isInboxReplies ? (
                        <>
                          <span className="cmd-action-item-title"> &middot; {item.category_label}: {truncate(item.subject, 32)}</span>
                          {onDismissInboxReply && (
                            <button
                              className="cmd-action-item-dismiss"
                              onClick={(e) => { e.stopPropagation(); onDismissInboxReply(item.message_id); }}
                              title="Dismiss"
                            >
                              ×
                            </button>
                          )}
                        </>
                      ) : (
                        item.title ? <span className="cmd-action-item-title"> &middot; {truncate(item.title, 40)}</span> : null
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cmd-action-card-empty">Nothing here right now.</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatNextRun(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const dateStr = sameDay ? 'Today' : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  const timeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `${dateStr} ${timeStr}`;
}

function AutomationStatus({ automation }) {
  const dailySearchText = automation.daily_search_scheduled
    ? `Scheduled — ${automation.daily_search_time || ''}`
    : 'Not scheduled';
  const rows = [
    { label: 'Automation', on: automation.automation_enabled, onText: 'On', offText: 'Off' },
    { label: 'Daily search', on: automation.daily_search_scheduled, onText: dailySearchText, offText: 'Not scheduled' },
    { label: 'Telegram alerts', on: automation.telegram_connected, onText: 'Connected', offText: 'Not connected' },
  ];
  return (
    <div className="cmd-panel cmd-status-panel">
      <div className="cmd-panel-header" style={{ marginBottom: '0.85rem' }}>
        <h2 style={{ margin: 0 }}>Automation Status</h2>
      </div>
      <div className="cmd-status-list">
        {rows.map(r => (
          <div key={r.label} className="cmd-status-row">
            <span className="cmd-status-label">{r.label}</span>
            <span className={`cmd-status-pill ${r.on ? 'on' : 'off'}`}>
              <span className="cmd-status-dot" /> {r.on ? r.onText : r.offText}
            </span>
          </div>
        ))}
      </div>
      {automation.daily_search_scheduled && automation.daily_search_next_run && (
        <div className="cmd-status-footnote" style={{ fontStyle: 'normal' }}>
          Next run: {formatNextRun(automation.daily_search_next_run)}
          {automation.daily_search_last_run && ` · Last ran: ${formatNextRun(automation.daily_search_last_run)}`}
        </div>
      )}
    </div>
  );
}

function JobSourceHealth({ breakdown }) {
  const entries = Object.entries(breakdown || {});
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  return (
    <div className="cmd-panel cmd-status-panel">
      <div className="cmd-panel-header" style={{ marginBottom: '0.85rem' }}>
        <h2 style={{ margin: 0 }}>Job Source Health</h2>
      </div>
      {entries.length === 0 ? (
        <div className="cmd-action-card-empty">No jobs tracked yet.</div>
      ) : (
        <div className="cmd-source-list">
          {entries.map(([source, count]) => (
            <div key={source} className="cmd-source-row">
              <span className="cmd-source-label">{source}</span>
              <div className="cmd-source-bar-track">
                <div className="cmd-source-bar-fill" style={{ width: `${total ? Math.max(6, (count / total) * 100) : 0}%` }} />
              </div>
              <span className="cmd-source-count">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CareerIntel({ intel }) {
  return (
    <div className="cmd-panel cmd-status-panel">
      <div className="cmd-panel-header" style={{ marginBottom: '0.85rem' }}>
        <h2 style={{ margin: 0 }}>Career Intel</h2>
      </div>
      <div className="cmd-status-list">
        <div className="cmd-status-row">
          <span className="cmd-status-label">Avg match score</span>
          <span className="cmd-context-value">{intel.avg_score}%</span>
        </div>
        <div className="cmd-status-row">
          <span className="cmd-status-label">Best source</span>
          <span className="cmd-context-value">{intel.best_source ? `${intel.best_source} (${intel.source_pct}%)` : '—'}</span>
        </div>
      </div>
      {intel.top_skills && intel.top_skills.length > 0 && (
        <>
          <div className="cmd-status-footnote" style={{ fontStyle: 'normal', marginTop: '0.85rem', marginBottom: '0.5rem', borderTop: 'none', paddingTop: 0 }}>
            Most common in your results:
          </div>
          <div className="cmd-skill-tags">
            {intel.top_skills.map(skill => (
              <span key={skill} className="cmd-skill-tag">{skill}</span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ icon, title, value, trend, trendType }) {
  const getIcon = () => {
    switch (icon) {
      case 'briefcase': return <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>;
      case 'star': return <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>;
      case 'skip': return <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>;
      case 'clock': return <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>;
      case 'calendar': return <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>;
      default: return null;
    }
  };

  return (
    <div className="cmd-metric-card">
      <div className="cmd-metric-icon" data-type={icon}>{getIcon()}</div>
      <div className="cmd-metric-content">
        <div className="cmd-metric-title">{title}</div>
        <div className="cmd-metric-value">{value}</div>
        <div className={`cmd-metric-trend ${trendType}`}>{trend}</div>
      </div>
    </div>
  );
}







// Same detection the backend's search-time hard-reject rule uses (_check_c2c_c2h_only)
// — not a guess off AI tags — so this badge reflects exactly why a posting did or
// didn't get filtered.
const EMPLOYMENT_TYPE_COLORS = { c2c: '#2ebd73', c2h: '#2ebd73', w2: '#d94f4f', contract: '#c89b3c' };

export function JobRow({ index, job, onSendToTailor, onSaveToApplications, onOpenDetail }) {
  const empColor = EMPLOYMENT_TYPE_COLORS[job.employment_type];
  return (
    <div
      className="cmd-job-row"
      onClick={() => onOpenDetail && onOpenDetail(job)}
      style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem', borderBottom: '1px solid var(--border)', cursor: onOpenDetail ? 'pointer' : 'default' }}
    >
      <div className="cmd-job-index" style={{ fontWeight: 'bold', color: 'var(--gold)' }}>{index}</div>
      <div className="cmd-job-main" style={{ flex: 1 }}>
        <div className="cmd-job-title" style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>{job.title}</div>
        <div className="cmd-job-company" style={{ color: 'var(--cream)', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span>{job.company} &middot; {job.location}</span>
          {job.employment_type_label && (
            <span
              className="jdw-badge"
              style={
                empColor
                  ? { background: `${empColor}22`, color: empColor, borderColor: empColor }
                  : { background: 'var(--surface-alt)', color: 'var(--cream-dim)', borderColor: 'var(--border)' }
              }
            >
              {job.employment_type_label}
            </span>
          )}
        </div>
        {job.reasons && job.reasons[0] && (
          <div className="cmd-job-top-reason">{truncate(job.reasons[0], 90)}</div>
        )}
        {job.url && <a href={job.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} style={{ fontSize: '0.8rem', color: '#818cf8' }}>Apply Link</a>}
      </div>
      <div className="cmd-job-score-col" style={{ textAlign: 'center' }}>
        <div className="cmd-job-score-val" style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--gold)' }}>{job.score}</div>
        <div className="cmd-job-score-label" style={{ fontSize: '0.75rem', color: 'var(--cream)' }}>Match Score</div>
      </div>
      <div className="cmd-job-reasons" style={{ flex: 1, fontSize: '0.8rem', color: 'var(--cream)' }}>
        <ul style={{ margin: 0, paddingLeft: '1rem' }}>
          {job.reasons && job.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
        {job.next_action && (
          <div className="cmd-job-next-action">
            <span className="cmd-job-next-action-label">Next:</span> {job.next_action}
          </div>
        )}
      </div>
      <div className="cmd-job-actions" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <button onClick={(e) => { e.stopPropagation(); onSendToTailor && onSendToTailor(job.description || job.title); }} style={{
          background: '#818cf8', color: '#fff', border: 'none', padding: '0.3rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem'
        }}>Tailor</button>
        <button onClick={(e) => { e.stopPropagation(); onSaveToApplications && onSaveToApplications(job); }} style={{
          background: 'var(--surface-alt)', color: 'var(--cream)', border: '1px solid var(--border)', padding: '0.3rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem'
        }}>Save App</button>
      </div>
    </div>
  );
}

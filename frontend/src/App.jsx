import React, { useState, useEffect, useRef } from 'react';
import './index.css';

function ScoreRing({ score, label, accent }) {
  const [display, setDisplay] = useState(0);
  const raf = useRef(null);
  const circumference = 2 * Math.PI * 38;

  useEffect(() => {
    if (raf.current) cancelAnimationFrame(raf.current);
    const start = performance.now();
    const duration = 900;
    const animate = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - t) ** 3;
      setDisplay(Math.round(eased * score));
      if (t < 1) raf.current = requestAnimationFrame(animate);
    };
    raf.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf.current);
  }, [score]);

  const offset = circumference * (1 - display / 100);

  return (
    <div className="score-ring">
      <div className="ring-label">{label}</div>
      <div className="ring-visual">
        <svg viewBox="0 0 100 100" width="110" height="110">
          <circle cx="50" cy="50" r="38" className="ring-track" />
          <circle
            cx="50" cy="50" r="38"
            className="ring-progress"
            style={{ stroke: accent, strokeDasharray: circumference, strokeDashoffset: offset }}
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div className="ring-value" style={{ color: accent }}>
          <span className="ring-num">{display}</span>
          <span className="ring-pct">%</span>
        </div>
      </div>
    </div>
  );
}

function FilmIcon() {
  return (
    <svg className="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="5" width="20" height="14" rx="1" />
      <line x1="2" y1="9" x2="22" y2="9" />
      <line x1="2" y1="15" x2="22" y2="15" />
      <line x1="6" y1="5" x2="6" y2="9" />
      <line x1="10" y1="5" x2="10" y2="9" />
      <line x1="14" y1="5" x2="14" y2="9" />
      <line x1="18" y1="5" x2="18" y2="9" />
      <line x1="6" y1="15" x2="6" y2="19" />
      <line x1="10" y1="15" x2="10" y2="19" />
      <line x1="14" y1="15" x2="14" y2="19" />
      <line x1="18" y1="15" x2="18" y2="19" />
    </svg>
  );
}

function EmptyResultsIcon() {
  return (
    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
      <rect x="8" y="16" width="48" height="32" rx="1" strokeDasharray="5 3" />
      <line x1="8" y1="23" x2="56" y2="23" />
      <line x1="8" y1="41" x2="56" y2="41" />
      <circle cx="32" cy="32" r="6" />
      <circle cx="32" cy="32" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}

const HISTORY_PAGE_SIZE = 20;

export default function App() {
  const [jdText, setJdText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [coverLetter, setCoverLetter] = useState(null);
  const [coverLetterPath, setCoverLetterPath] = useState(null);
  const [generatingCL, setGeneratingCL] = useState(false);
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [storedResumes, setStoredResumes] = useState([]);
  const [selectedResumeName, setSelectedResumeName] = useState(() => localStorage.getItem('selectedResume') || null);
  const [uploadingResume, setUploadingResume] = useState(false);
  const [loadingCLId, setLoadingCLId] = useState(null);
  const [historyCLModal, setHistoryCLModal] = useState(null);
  const [batchMode, setBatchMode] = useState(false);
  const [batchText, setBatchText] = useState('');
  const [batchJobs, setBatchJobs] = useState([]);
  const [batchRunning, setBatchRunning] = useState(false);
  // History search / filter / pagination
  const [historySearch, setHistorySearch] = useState('');
  const [historyStatusFilter, setHistoryStatusFilter] = useState('');
  const [historyPage, setHistoryPage] = useState(1);
  const [expandedJdId, setExpandedJdId] = useState(null);
  // Mail draft — results panel
  const [mailDraft, setMailDraft] = useState(null);
  const [generatingMail, setGeneratingMail] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftPath, setDraftPath] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  // Mail draft — history modal
  const [historyMailModal, setHistoryMailModal] = useState(null);
  const [loadingMailId, setLoadingMailId] = useState(null);
  const [historyDraftSaving, setHistoryDraftSaving] = useState(false);
  const [historyDraftPath, setHistoryDraftPath] = useState(null);
  // Active record for panels 03 + 04
  const [activeRecordId, setActiveRecordId] = useState(null);
  const [activeCompanyName, setActiveCompanyName] = useState(null);
  // Personal profile
  const [profileText, setProfileText] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profileUploading, setProfileUploading] = useState(false);
  const [profileUploadMsg, setProfileUploadMsg] = useState(null);
  // API Usage
  const [usageStats, setUsageStats] = useState(null);
  const [usageOpen, setUsageOpen] = useState(false);
  // Gmail integration
  const [gmailConnected, setGmailConnected] = useState(false);
  const [gmailEmail, setGmailEmail] = useState('');
  const [savingToGmail, setSavingToGmail] = useState(false);
  const [gmailSaved, setGmailSaved] = useState(false);

  const fetchResumes = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/resumes');
      if (!res.ok) return;
      const data = await res.json();
      setStoredResumes(data);
      if (data.length > 0) {
        const stored = localStorage.getItem('selectedResume');
        if (!data.some(r => r.filename === stored)) {
          setSelectedResumeName(data[0].filename);
          localStorage.setItem('selectedResume', data[0].filename);
        }
      }
    } catch { /* ignore */ }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/history?limit=200');
      if (res.ok) setHistory(await res.json());
    } catch { /* ignore */ }
  };

  const checkGmailStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/gmail/status');
      if (res.ok) {
        const data = await res.json();
        setGmailConnected(data.connected);
        setGmailEmail(data.email || '');
      }
    } catch { /* ignore */ }
  };

  const fetchUsage = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/usage');
      if (res.ok) setUsageStats(await res.json());
    } catch { /* ignore */ }
  };

  const fetchProfile = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/profile');
      if (res.ok) {
        const data = await res.json();
        setProfileText(data.content || '');
        setProfileLoaded(data.exists);
      }
    } catch { /* ignore */ }
  };

  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    fetchHistory();
    fetchResumes();
    checkGmailStatus();
    fetchProfile();
    fetchUsage();

    const params = new URLSearchParams(window.location.search);
    if (params.get('gmail') === 'connected') {
      window.history.replaceState({}, '', window.location.pathname);
    }
  });

  // Derived history values — historyPage resets are computed, not effectful
  const filteredHistory = history
    .filter(item => !historySearch || (item.company_name || '').toLowerCase().includes(historySearch.toLowerCase()))
    .filter(item => !historyStatusFilter || item.status === historyStatusFilter);
  const totalPages = Math.ceil(filteredHistory.length / HISTORY_PAGE_SIZE) || 1;
  const computedPage = historyPage > totalPages ? 1 : historyPage;
  const pagedHistory = filteredHistory.slice((computedPage - 1) * HISTORY_PAGE_SIZE, computedPage * HISTORY_PAGE_SIZE);

  const handleSaveToGmail = async () => {
    if (!mailDraft || !activeRecordId) return;
    setSavingToGmail(true);
    setGmailSaved(false);
    try {
      const res = await fetch('http://localhost:8000/api/gmail/save-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to_emails: mailDraft.to_emails || [],
          subject: mailDraft.subject,
          body: mailDraft.body,
          record_id: activeRecordId,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Failed to save to Gmail'); return; }
      setGmailSaved(true);
      setTimeout(() => setGmailSaved(false), 5000);
    } catch {
      setError('Failed to save draft to Gmail');
    } finally {
      setSavingToGmail(false);
    }
  };

  const handleDisconnectGmail = async () => {
    try {
      await fetch('http://localhost:8000/api/gmail/disconnect', { method: 'POST' });
      setGmailConnected(false);
      setGmailEmail('');
    } catch { /* ignore */ }
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    try {
      const res = await fetch('http://localhost:8000/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: profileText }),
      });
      if (res.ok) setProfileLoaded(true);
    } catch { /* ignore */ }
    finally { setProfileSaving(false); }
  };

  const handleProfileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setProfileUploading(true);
    setProfileUploadMsg(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('http://localhost:8000/api/profile/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) { setProfileUploadMsg(data.detail || 'Upload failed'); return; }
      setProfileText(data.profile || '');
      setProfileLoaded(true);
      setProfileUploadMsg(data.message || 'Facts extracted and merged into profile.');
      setTimeout(() => setProfileUploadMsg(null), 5000);
    } catch {
      setProfileUploadMsg('Failed to process document.');
    } finally {
      setProfileUploading(false);
      e.target.value = '';
    }
  };

  const handleAddResume = async (file) => {
    if (!file) return;
    if (!file.name.endsWith('.docx')) { setError('Only .docx files are supported.'); return; }
    setUploadingResume(true);
    const formData = new FormData();
    formData.append('resume', file);
    try {
      const res = await fetch('http://localhost:8000/api/resumes', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Upload failed'); return; }
      await fetchResumes();
      setSelectedResumeName(data.filename);
      localStorage.setItem('selectedResume', data.filename);
    } catch {
      setError('Upload failed. Check your connection.');
    } finally {
      setUploadingResume(false);
    }
  };

  const handleResumeSelect = (filename) => {
    setSelectedResumeName(filename);
    localStorage.setItem('selectedResume', filename);
  };

  const handleResumeDelete = async (filename) => {
    try {
      const res = await fetch(`http://localhost:8000/api/resumes/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (res.ok) {
        const remaining = storedResumes.filter(r => r.filename !== filename);
        setStoredResumes(remaining);
        if (selectedResumeName === filename) {
          const next = remaining[0]?.filename || null;
          setSelectedResumeName(next);
          if (next) localStorage.setItem('selectedResume', next);
          else localStorage.removeItem('selectedResume');
        }
      }
    } catch (err) {
      console.error('Failed to delete resume:', err);
    }
  };

  const handleScan = async () => {
    setError(null);
    if (!jdText.trim()) { setError('Job Description is required.'); return; }
    if (!selectedResumeName && storedResumes.length === 0) { setError('Please add a base resume first.'); return; }
    setLoading(true);
    setResult(null);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    const formData = new FormData();
    formData.append('jd_text', jdText);
    if (selectedResumeName) formData.append('selected_resume', selectedResumeName);
    try {
      const res = await fetch('http://localhost:8000/api/scan', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) {
        setError(res.status === 429 ? 'Rate limit hit — wait a moment and try again.' : (data.detail || `Server error (${res.status}). Please try again.`));
        return;
      }
      setResult(data);
      setActiveRecordId(data.id);
      setActiveCompanyName(data.company_name);
      fetchHistory();
    } catch {
      setError('An error occurred. Check your connection or API limits.');
    } finally {
      setLoading(false); fetchUsage();
    }
  };

  const handleReset = () => {
    setJdText('');
    setResult(null);
    setError(null);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    setActiveRecordId(null);
    setActiveCompanyName(null);
  };

  const handleDeleteHistory = async (id) => {
    if (!window.confirm('Delete this record?')) return;
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}`, { method: 'DELETE' });
      if (res.ok) fetchHistory();
    } catch (err) {
      console.error('Failed to delete record:', err);
    }
  };

  const handleGenerateCL = async () => {
    if (!activeRecordId) { setError('Select a company first.'); return; }
    setGeneratingCL(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/cover-letter`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setCoverLetter(data.cover_letter);
      setCoverLetterPath(data.cl_path || null);
    } catch {
      setError('Failed to generate cover letter. The AI provider might be overloaded.');
    } finally {
      setGeneratingCL(false); fetchUsage();
    }
  };

  const handleHistoryCL = async (id, companyName) => {
    setLoadingCLId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/cover-letter`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || `Failed to generate cover letter (${res.status})`);
        return;
      }
      const data = await res.json();
      setHistoryCLModal({ cover_letter: data.cover_letter, cl_path: data.cl_path, company_name: companyName });
    } catch {
      setError('Failed to generate cover letter.');
    } finally {
      setLoadingCLId(null);
    }
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) fetchHistory();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const handleBatchRun = async () => {
    if (storedResumes.length === 0 || !selectedResumeName) {
      setError('Batch mode requires a stored base resume. Add one in Single Scan mode first.');
      return;
    }
    const jds = batchText.split(/\n[ \t]*---[ \t]*\n/).map(j => j.trim()).filter(j => j.length > 50);
    if (jds.length === 0) {
      setError('No valid JDs found. Separate multiple JDs with a line containing only ---');
      return;
    }
    setError(null);
    setBatchJobs(jds.map((jd, i) => ({ id: i, jd, status: 'pending', result: null, error: null })));
    setBatchRunning(true);
    for (let i = 0; i < jds.length; i++) {
      setBatchJobs(prev => prev.map((j, idx) => idx === i ? { ...j, status: 'processing' } : j));
      try {
        const formData = new FormData();
        formData.append('jd_text', jds[i]);
        if (selectedResumeName) formData.append('selected_resume', selectedResumeName);
        const res = await fetch('http://localhost:8000/api/scan', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) {
          setBatchJobs(prev => prev.map((j, idx) => idx === i ? { ...j, status: 'error', error: res.status === 429 ? 'Rate limit — wait and retry' : (data.detail || `Error ${res.status}`) } : j));
        } else {
          setBatchJobs(prev => prev.map((j, idx) => idx === i ? { ...j, status: 'done', result: data } : j));
        }
      } catch {
        setBatchJobs(prev => prev.map((j, idx) => idx === i ? { ...j, status: 'error', error: 'Network error' } : j));
      }
      if (i < jds.length - 1) await new Promise(r => setTimeout(r, 2000));
    }
    setBatchRunning(false);
    fetchHistory();
  };

  const handleBatchFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => setBatchText(ev.target.result || '');
    reader.readAsText(file);
  };

  const toggleJdExpand = (id) => setExpandedJdId(prev => prev === id ? null : id);

  const handleGenerateMail = async () => {
    if (!activeRecordId) { setError('Select a company first.'); return; }
    setGeneratingMail(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/mail-draft`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Mail draft error (${res.status})`); return; }
      setMailDraft(data);
      setDraftPath(null);
    } catch {
      setError('Failed to generate mail draft.');
    } finally {
      setGeneratingMail(false); fetchUsage();
    }
  };

  const handleSaveDraft = async () => {
    if (!activeRecordId || !mailDraft) return;
    setSavingDraft(true);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/mail-draft/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: mailDraft.subject, body: mailDraft.body }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Save failed'); return; }
      setDraftPath(data.draft_path);
    } catch {
      setError('Failed to save draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSelectRecord = async (item) => {
    setActiveRecordId(item.id);
    setActiveCompanyName(item.company_name);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${item.id}/content`);
      if (res.ok) {
        const data = await res.json();
        if (data.cover_letter) { setCoverLetter(data.cover_letter); setCoverLetterPath(data.cl_path); }
        if (data.mail_draft) { setMailDraft(data.mail_draft); setDraftPath(data.draft_path); }
      }
    } catch { /* ignore */ }
    document.getElementById('panels-cl-mail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleHistoryMail = async (id, companyName) => {
    setLoadingMailId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/mail-draft`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setHistoryMailModal({ ...data, company_name: companyName, record_id: id });
      setHistoryDraftPath(null);
    } catch {
      setError('Failed to generate mail draft.');
    } finally {
      setLoadingMailId(null);
    }
  };

  const handleSaveHistoryDraft = async () => {
    if (!historyMailModal) return;
    setHistoryDraftSaving(true);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${historyMailModal.record_id}/mail-draft/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: historyMailModal.subject, body: historyMailModal.body }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Save failed'); return; }
      setHistoryDraftPath(data.draft_path);
    } catch {
      setError('Failed to save draft.');
    } finally {
      setHistoryDraftSaving(false);
    }
  };

  const scoreAccent = (score) => {
    if (score >= 85) return '#2ebd73';
    if (score >= 60) return '#c89b3c';
    return '#d94f4f';
  };

  const deltaScore = result?.after_score != null ? result.after_score - result.score : 0;

  return (
    <div className="app">
      <div className="grain" aria-hidden="true" />

      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <FilmIcon />
            <h1>TRAILERD</h1>
          </div>
          <p className="site-tagline">AI Resume Tailoring Studio<br />Frame your story. Land the role.</p>
        </div>
        <div className="header-rule" />
      </header>

      <main className="main-content">
        <div className="mode-tabs">
          <button className={`mode-tab${!batchMode ? ' active' : ''}`} onClick={() => { setBatchMode(false); setError(null); }}>Single Scan</button>
          <button className={`mode-tab${batchMode ? ' active' : ''}`} onClick={() => { setBatchMode(true); setError(null); }}>⚡ Batch Mode</button>
          <button className={`mode-tab usage-tab${usageOpen ? ' active' : ''}`} onClick={() => { setUsageOpen(u => !u); fetchUsage(); }}>
            $ Usage {usageStats ? `($${usageStats.all_time?.cost?.toFixed(2) || '0.00'})` : ''}
          </button>
        </div>

        {usageOpen && usageStats && (
          <div className="usage-dashboard">
            <div className="usage-cards">
              <div className="usage-card">
                <div className="usage-card-label">Today</div>
                <div className="usage-card-cost">${usageStats.today?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.today?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">This Week</div>
                <div className="usage-card-cost">${usageStats.week?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.week?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">This Month</div>
                <div className="usage-card-cost">${usageStats.month?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.month?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">All Time</div>
                <div className="usage-card-cost">${usageStats.all_time?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.all_time?.calls || 0} calls</div>
              </div>
            </div>
            {usageStats.all_time?.by_model && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">By Model</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.all_time.by_model).map(([model, info]) => (
                    <div key={model} className="usage-row">
                      <span className="usage-row-model">{model}</span>
                      <span className="usage-row-calls">{info.calls} calls</span>
                      <span className="usage-row-cost">${info.cost?.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {usageStats.all_time?.by_operation && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">By Operation</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.all_time.by_operation).map(([op, count]) => (
                    <div key={op} className="usage-row">
                      <span className="usage-row-model">{op.replace(/_/g, ' ')}</span>
                      <span className="usage-row-calls">{count} calls</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {usageStats.daily_breakdown && Object.keys(usageStats.daily_breakdown).length > 0 && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">Daily (Last 7 Days)</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.daily_breakdown).sort((a, b) => b[0].localeCompare(a[0])).map(([day, info]) => (
                    <div key={day} className="usage-row">
                      <span className="usage-row-model">{day}</span>
                      <span className="usage-row-calls">{info.calls} calls</span>
                      <span className="usage-row-cost">${info.cost?.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="usage-projected">
              Projected monthly: <strong>${usageStats.projected_monthly?.toFixed(2) || '0.00'}</strong> (based on today's usage)
            </div>
          </div>
        )}

        <div className="workspace" style={{ display: batchMode ? 'none' : 'grid' }}>

          {/* ── Left: Input Panel ── */}
          <div className="panel panel-enter" style={{ animationDelay: '0ms' }}>
            <div className="panel-tag">
              <span className="panel-num">01</span>
              <span className="panel-title">Pre-Production</span>
            </div>

            {error && <div className="error-banner">⚠ {error}</div>}

            <div className="field">
              <label className="field-label">Job Description</label>
              <div className="textarea-wrap">
                <textarea
                  className="field-textarea"
                  placeholder="Paste the job description here… (Ctrl+Enter to scan)"
                  value={jdText}
                  onChange={e => setJdText(e.target.value)}
                  onKeyDown={e => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); handleScan(); } }}
                />
                {jdText.length > 0 && <span className="char-count">{jdText.length} chars</span>}
              </div>
            </div>

            <div className="field">
              <label className="field-label">Base Resume</label>
              <div
                className={`resume-manager${dragging ? ' dragging' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) handleAddResume(f); }}
              >
                {storedResumes.length === 0 && !uploadingResume && (
                  <p className="resume-empty">No resumes yet — add one below or drag a .docx here</p>
                )}
                {storedResumes.map(r => (
                  <div key={r.filename} className={`resume-item${selectedResumeName === r.filename ? ' selected' : ''}`} onClick={() => handleResumeSelect(r.filename)}>
                    <span className="resume-item-dot">{selectedResumeName === r.filename ? '●' : '○'}</span>
                    <span className="resume-item-name" title={r.filename}>{r.filename.replace(/\.docx$/i, '')}</span>
                    <button className="resume-item-del" onClick={e => { e.stopPropagation(); handleResumeDelete(r.filename); }} title="Remove">×</button>
                  </div>
                ))}
                {uploadingResume && (
                  <div className="resume-item">
                    <span className="resume-item-dot spin-icon" style={{ color: 'var(--gold)' }}>▶</span>
                    <span className="resume-item-name">Uploading…</span>
                  </div>
                )}
                <label className="resume-add-btn">
                  + Add Resume (.docx)
                  <input type="file" accept=".docx" onChange={e => { handleAddResume(e.target.files?.[0]); e.target.value = ''; }} />
                </label>
              </div>
            </div>

            <div className="field">
              <button className="profile-toggle" onClick={() => setProfileOpen(p => !p)}>
                {profileOpen ? '▾' : '▸'} Personal Profile {profileLoaded && <span className="profile-badge">●</span>}
              </button>
              {profileOpen && (
                <div className="profile-editor">
                  <div className="profile-hint">Upload personal docs (DL, GC, etc.) to auto-extract key facts, or type them manually. Raw files are never stored — only the extracted facts are saved.</div>
                  <div className="profile-upload-row">
                    <label className="profile-upload-btn">
                      {profileUploading ? '⏳ Extracting…' : '📄 Upload Document'}
                      <input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp" onChange={handleProfileUpload} disabled={profileUploading} hidden />
                    </label>
                    <span className="profile-upload-hint">PDF, DOCX, or Image</span>
                  </div>
                  {profileUploadMsg && <div className="profile-upload-msg">{profileUploadMsg}</div>}
                  <textarea
                    className="field-textarea profile-textarea"
                    placeholder={"Work Authorization: US Green Card holder\nLocation: Open to relocation\nAvailability: Immediate\nNotice Period: None\nWilling to Travel: Yes\nPreferred Work Mode: Hybrid or Remote"}
                    value={profileText}
                    onChange={e => setProfileText(e.target.value)}
                    rows={6}
                  />
                  <button className="profile-save-btn" onClick={handleSaveProfile} disabled={profileSaving}>
                    {profileSaving ? '…' : '💾 Save Profile'}
                  </button>
                </div>
              )}
            </div>

            <div className="btn-row">
              <button className={`action-btn${loading ? ' loading' : ''}`} onClick={handleScan} disabled={loading} style={{ flex: 2 }}>
                {loading ? <span className="btn-loading"><span className="spin-icon">▶</span> Processing…</span> : '▶ ACTION'}
              </button>
              {(result || jdText) && (
                <button className="action-btn reset-btn" onClick={handleReset} disabled={loading} style={{ flex: 1 }}>Reset</button>
              )}
            </div>
          </div>

          {/* ── Right: Results Panel ── */}
          <div className="panel panel-enter" style={{ animationDelay: '80ms' }}>
            <div className="panel-tag">
              <span className="panel-num">02</span>
              <span className="panel-title">Post-Production</span>
            </div>

            {loading ? (
              <div className="scanning">
                <div className="scan-line" />
                <EmptyResultsIcon />
                <p className="scan-label">Analyzing resume…</p>
              </div>
            ) : result ? (
              <div className="results">
                <div className="company-badge">
                  <span className="company-label">Company</span>
                  <span className="company-name">{result.company_name}</span>
                </div>

                <div className="score-row">
                  <ScoreRing key={`before-${result.score}`} score={result.score} label="Original" accent={scoreAccent(result.score)} />
                  {result.tailored && result.after_score != null && (
                    <>
                      <div className="score-arrow">→</div>
                      <ScoreRing key={`after-${result.after_score}`} score={result.after_score} label="Tailored" accent={scoreAccent(result.after_score)} />
                    </>
                  )}
                </div>

                <div className={`status-banner ${result.tailored ? 'status-tailored' : 'status-original'}`}>
                  {result.tailored && deltaScore > 0
                    ? `↑ +${deltaScore} pts — resume automatically tailored`
                    : result.tailored ? 'Resume tailored for this role'
                    : 'Score strong — no tailoring needed'}
                </div>

                {result.file_path && (
                  <div className="result-downloads">
                    <a href={`http://localhost:8000/api/download/${result.file_path.replace(/^trailerd\//, '')}`} className="download-btn" download>
                      ↓ Download Tailored Resume
                    </a>
                    <div className="file-dl-row">
                      <a href={`http://localhost:8000/api/download/${result.file_path.replace('tejamahesh_resume.docx', 'jd_info.txt').replace(/^trailerd\//, '')}`} className="file-dl-link" download>
                        ↓ jd_info.txt
                      </a>
                    </div>
                  </div>
                )}

                {result.contact_info && Object.values(result.contact_info).some(v => v) && (
                  <div className="contact-info-strip">
                    <div className="contact-info-label">Detected Contact Info</div>
                    <div className="contact-info-fields">
                      {result.contact_info.name && <span className="contact-field"><span className="contact-key">Name</span>{result.contact_info.name}</span>}
                      {result.contact_info.email && <span className="contact-field"><span className="contact-key">Email</span>{result.contact_info.email}</span>}
                      {result.contact_info.phone && <span className="contact-field"><span className="contact-key">Phone</span>{result.contact_info.phone}</span>}
                    </div>
                  </div>
                )}

                {result.missing_keywords?.length > 0 && (
                  <div className="keyword-gap">
                    <div className="keyword-gap-header">Missing Keywords</div>
                    <div className="keyword-chips">
                      {result.missing_keywords.map((kw, idx) => <span key={idx} className="keyword-chip">{kw}</span>)}
                    </div>
                  </div>
                )}

                {result.section_scores && Object.keys(result.section_scores).length > 0 && (
                  <div className="section-breakdown">
                    <div className="section-breakdown-header">Section Breakdown</div>
                    <div className="section-bars">
                      {Object.entries(result.section_scores).map(([section, sectionScore]) => (
                        <div key={section} className="section-bar-row">
                          <div className="section-bar-label">{section}</div>
                          <div className="section-bar-track">
                            <div className="section-bar-fill" style={{ width: `${sectionScore}%`, background: sectionScore >= 85 ? 'var(--success)' : sectionScore >= 60 ? 'var(--gold)' : 'var(--danger)' }} />
                          </div>
                          <div className="section-bar-value" style={{ color: sectionScore >= 85 ? 'var(--success)' : sectionScore >= 60 ? 'var(--gold)' : 'var(--danger)' }}>{sectionScore}%</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result.replacements?.length > 0 && (
                  <div className="diff-section">
                    <div className="diff-header">AI Changes — {result.replacements.length} edit{result.replacements.length !== 1 ? 's' : ''}</div>
                    <div className="diff-list">
                      {result.replacements.map((rep, idx) => (
                        <div key={idx} className="diff-item">
                          <div className="diff-removed">− {rep.original}</div>
                          <div className="diff-added">+ {rep.new}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="results-empty">
                <div className="empty-icon"><EmptyResultsIcon /></div>
                <p className="empty-label">Fill in Pre-Production<br />and hit ACTION to begin</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Cover Letter & Email Draft ── */}
        <div className="workspace" id="panels-cl-mail">
            {/* Panel 03 — Cover Letter */}
            <div className="panel panel-enter" style={{ animationDelay: '60ms' }}>
              <div className="panel-tag">
                <span className="panel-num">03</span>
                <span className="panel-title">Cover Letter</span>
                {activeCompanyName && <span className="panel-active-co">{activeCompanyName}</span>}
              </div>
              {!activeRecordId ? (
                <p className="panel-placeholder">Run a scan or click a company name in the Production Log.</p>
              ) : !coverLetter ? (
                <button className="action-btn" onClick={handleGenerateCL} disabled={generatingCL} style={{ marginTop: 0 }}>
                  {generatingCL ? <span className="btn-loading"><span className="spin-icon">▶</span> Generating…</span> : '▶ Generate Cover Letter'}
                </button>
              ) : (
                <div className="cover-letter-section">
                  <div className="cl-text">{coverLetter}</div>
                  <div className="cl-actions">
                    <button className="cl-copy-btn" onClick={() => { navigator.clipboard.writeText(coverLetter); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                      {copied ? '✓ Copied' : '↑ Copy'}
                    </button>
                    {coverLetterPath && (
                      <a href={`http://localhost:8000/api/download/${coverLetterPath.replace(/^trailerd\//, '')}`} className="cl-download-btn" download>↓ Download .docx</a>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Panel 04 — Email Draft */}
            <div className="panel panel-enter" style={{ animationDelay: '100ms' }}>
              <div className="panel-tag">
                <span className="panel-num">04</span>
                <span className="panel-title">Email Draft</span>
                <span className="mail-ollama-badge" style={{ marginLeft: '0.5rem' }}>via OpenAI</span>
                {activeCompanyName && <span className="panel-active-co">{activeCompanyName}</span>}
              </div>
              {!activeRecordId ? (
                <p className="panel-placeholder">Run a scan or click a company name in the Production Log.</p>
              ) : !mailDraft ? (
                <button className="action-btn" onClick={handleGenerateMail} disabled={generatingMail} style={{ marginTop: 0 }}>
                  {generatingMail ? <span className="btn-loading"><span className="spin-icon">▶</span> Generating…</span> : '✉ Generate Email Draft'}
                </button>
              ) : (
                <div className="mail-draft-section">
                  <div className="mail-draft-body">
                    {mailDraft.to_emails?.length > 0 && (
                      <div className="mail-field">
                        <span className="mail-field-label">To</span>
                        <div className="mail-to-chips">
                          {mailDraft.to_emails.map((email, i) => <span key={i} className="mail-to-chip">{email}</span>)}
                        </div>
                      </div>
                    )}
                    <div className="mail-field">
                      <div className="mail-subject-row">
                        <span className="mail-field-label">Subject</span>
                        <button className="mail-copy-small" onClick={() => { navigator.clipboard.writeText(mailDraft.subject); setCopiedField('subject'); setTimeout(() => setCopiedField(null), 2000); }}>
                          {copiedField === 'subject' ? '✓' : '↑ Copy'}
                        </button>
                      </div>
                      <div className="mail-subject-text">{mailDraft.subject}</div>
                    </div>
                    <div className="mail-field">
                      <span className="mail-field-label">Body</span>
                      <div className="mail-body-text">{mailDraft.body}</div>
                    </div>
                  </div>
                  <div className="mail-draft-actions">
                    <button className="mail-act-btn" onClick={() => { navigator.clipboard.writeText(mailDraft.body); setCopiedField('body'); setTimeout(() => setCopiedField(null), 2000); }}>
                      {copiedField === 'body' ? '✓ Copied' : '↑ Copy Body'}
                    </button>
                    {!draftPath ? (
                      <button className="mail-act-btn mail-save-btn" onClick={handleSaveDraft} disabled={savingDraft}>
                        {savingDraft ? '…' : '💾 Save to Folder'}
                      </button>
                    ) : (
                      <a href={`http://localhost:8000/api/download/${draftPath.replace(/^trailerd\//, '')}`} className="mail-act-btn mail-dl-btn" download>
                        ↓ Download .txt
                      </a>
                    )}
                    {gmailConnected ? (
                      <button className="mail-act-btn mail-gmail-btn" onClick={handleSaveToGmail} disabled={savingToGmail}>
                        {savingToGmail ? '…' : gmailSaved ? '✓ Saved to Gmail' : '✉ Save to Gmail Drafts'}
                      </button>
                    ) : (
                      <a href="http://localhost:8000/api/gmail/auth" className="mail-act-btn mail-gmail-connect-btn">
                        ✉ Connect Gmail
                      </a>
                    )}
                  </div>
                  {gmailConnected && (
                    <div className="gmail-status">
                      <span className="gmail-status-dot">●</span> Connected: {gmailEmail}
                      <button className="gmail-disconnect-btn" onClick={handleDisconnectGmail}>Disconnect</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

        {/* ── Batch Mode ── */}
        {batchMode && (
          <div className="panel panel-wide panel-enter">
            <div className="panel-tag">
              <span className="panel-num">04</span>
              <span className="panel-title">Batch Production</span>
            </div>
            {error && <div className="error-banner">⚠ {error}</div>}
            {(storedResumes.length === 0 || !selectedResumeName) && (
              <div className="error-banner">⚠ No resume selected — add one in Single Scan mode first.</div>
            )}
            <div className="batch-workspace">
              <div className="batch-input-col">
                <label className="field-label">Job Descriptions</label>
                <p className="batch-hint">Separate multiple JDs with a line containing only <span className="batch-sep">---</span></p>
                <div className="textarea-wrap">
                  <textarea
                    className="field-textarea batch-textarea"
                    placeholder={"Paste first JD here...\n\n---\n\nPaste second JD here...\n\n---\n\nAnd so on..."}
                    value={batchText}
                    onChange={e => setBatchText(e.target.value)}
                    disabled={batchRunning}
                  />
                  {batchText.trim().length > 0 && (
                    <span className="char-count">{batchText.split(/\n[ \t]*---[ \t]*\n/).filter(j => j.trim().length > 50).length} JDs detected</span>
                  )}
                </div>
                <div className="batch-btn-row">
                  <label className="batch-upload-label">
                    ↑ Upload .txt
                    <input type="file" accept=".txt,.text" onChange={handleBatchFileUpload} disabled={batchRunning} />
                  </label>
                  <button className={`action-btn${batchRunning ? ' loading' : ''}`} onClick={handleBatchRun} disabled={batchRunning || !batchText.trim() || !selectedResumeName} style={{ flex: 2 }}>
                    {batchRunning ? <span className="btn-loading"><span className="spin-icon">▶</span> Processing…</span> : '▶ Run Batch'}
                  </button>
                </div>
              </div>
              {batchJobs.length > 0 && (
                <div className="batch-results-col">
                  <div className="batch-results-header">
                    <span className="field-label" style={{ margin: 0 }}>Progress</span>
                    <span className="batch-summary">{batchJobs.filter(j => j.status === 'done').length} / {batchJobs.length} complete</span>
                  </div>
                  <div className="batch-job-list">
                    {batchJobs.map((job, idx) => (
                      <div key={idx} className={`batch-job batch-job-${job.status}`}>
                        <span className="batch-job-num">{String(idx + 1).padStart(2, '0')}</span>
                        <div className="batch-job-body">
                          <span className="batch-job-company">{job.result?.company_name || `JD #${idx + 1}`}</span>
                          {job.status === 'error' && <span className="batch-job-err">{job.error}</span>}
                        </div>
                        <div className="batch-job-meta">
                          {job.status === 'done' && <span className="batch-job-score" style={{ color: scoreAccent(job.result.score) }}>{job.result.score}%</span>}
                          {job.status === 'done' && job.result?.file_path && (
                            <>
                              <a href={`http://localhost:8000/api/download/${job.result.file_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Resume">↓</a>
                              <a href={`http://localhost:8000/api/download/${job.result.file_path.replace('tejamahesh_resume.docx', 'jd_info.txt').replace(/^trailerd\//, '')}`} className="dl-link" download title="JD Info">JD</a>
                            </>
                          )}
                        </div>
                        <span className="batch-status-icon">
                          {job.status === 'pending' && <span className="batch-dot pending">○</span>}
                          {job.status === 'processing' && <span className="batch-dot processing spin-icon">▶</span>}
                          {job.status === 'done' && <span className="batch-dot done">✓</span>}
                          {job.status === 'error' && <span className="batch-dot error">✕</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Production Log ── */}
        <div className="panel panel-wide panel-enter" style={{ animationDelay: '160ms' }}>
          <div className="panel-top-row">
            <div className="panel-tag inline">
              <span className="panel-num">05</span>
              <span className="panel-title">Production Log</span>
            </div>
            {history.length > 0 && (
              <a href="http://localhost:8000/api/history/csv" className="csv-btn" download>↓ CSV Export</a>
            )}
          </div>

          {history.length > 0 && (
            <div className="history-filters">
              <input
                type="text"
                className="history-search"
                placeholder="Search company…"
                value={historySearch}
                onChange={e => setHistorySearch(e.target.value)}
              />
              <select
                className="history-filter-select"
                value={historyStatusFilter}
                onChange={e => setHistoryStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="Scanned">Scanned</option>
                <option value="Applied">Applied</option>
                <option value="Phone Screen">Phone Screen</option>
                <option value="Interview">Interview</option>
                <option value="Offer">Offer</option>
                <option value="Rejected">Rejected</option>
              </select>
              {(historySearch || historyStatusFilter) && (
                <button className="filter-clear-btn" onClick={() => { setHistorySearch(''); setHistoryStatusFilter(''); }}>✕ Clear</button>
              )}
              <span className="history-count">{filteredHistory.length} record{filteredHistory.length !== 1 ? 's' : ''}</span>
            </div>
          )}

          {filteredHistory.length > 0 ? (
            <>
              <table className="history-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Company</th>
                    <th>Date</th>
                    <th>Score</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {pagedHistory.map((item, idx) => (
                    <React.Fragment key={item.id}>
                      <tr className={`history-row${expandedJdId === item.id ? ' jd-open' : ''}`}>
                        <td className="scene-num">{String((historyPage - 1) * HISTORY_PAGE_SIZE + idx + 1).padStart(2, '0')}</td>
                        <td className="company-col">
                          <button className="jd-toggle-btn" onClick={() => toggleJdExpand(item.id)} title={expandedJdId === item.id ? 'Hide JD' : 'Preview JD'}>
                            {expandedJdId === item.id ? '▾' : '▸'}
                          </button>
                          <button
                            className={`company-name-btn${activeRecordId === item.id ? ' active' : ''}`}
                            onClick={() => handleSelectRecord(item)}
                            title="Load cover letter &amp; email draft"
                          >
                            {item.company_name}
                          </button>
                        </td>
                        <td className="date-col">
                          {item.created_at ? new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                        </td>
                        <td className="score-col">
                          <span className="score-badge" style={{ color: scoreAccent(item.score) }}>{item.score}%</span>
                        </td>
                        <td>
                          <select
                            value={item.status || 'Scanned'}
                            onChange={e => handleStatusChange(item.id, e.target.value)}
                            className={`status-dropdown status-${(item.status || 'Scanned').toLowerCase().replace(' ', '-')}`}
                          >
                            <option value="Scanned">Scanned</option>
                            <option value="Applied">Applied</option>
                            <option value="Phone Screen">Phone Screen</option>
                            <option value="Interview">Interview</option>
                            <option value="Offer">Offer</option>
                            <option value="Rejected">Rejected</option>
                          </select>
                        </td>
                        <td className="actions-col">
                          {item.file_path && (
                            <a href={`http://localhost:8000/api/download/${item.file_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Download resume">↓</a>
                          )}
                          {item.file_path && (
                            <a href={`http://localhost:8000/api/download/${item.file_path.replace('tejamahesh_resume.docx', 'jd_info.txt').replace(/^trailerd\//, '')}`} className="dl-link" download title="Download JD info">JD</a>
                          )}
                          <button className="cl-hist-btn" onClick={() => handleHistoryCL(item.id, item.company_name)} disabled={loadingCLId === item.id} title="Generate cover letter">
                            {loadingCLId === item.id ? '…' : 'CL'}
                          </button>
                          <button className="mail-hist-btn" onClick={() => handleHistoryMail(item.id, item.company_name)} disabled={loadingMailId === item.id} title="Generate email draft">
                            {loadingMailId === item.id ? '…' : '✉'}
                          </button>
                          <button className="del-btn" onClick={() => handleDeleteHistory(item.id)} title="Delete record">×</button>
                        </td>
                      </tr>
                      {expandedJdId === item.id && (
                        <tr className="jd-preview-row">
                          <td colSpan="6">
                            <div className="jd-preview-content">
                              <div className="jd-preview-label">Job Description</div>
                              <div className="jd-preview-text">{item.jd_text}</div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div className="history-pagination">
                  <button className="page-btn" onClick={() => setHistoryPage(p => Math.max(1, p - 1))} disabled={historyPage === 1}>← Prev</button>
                  <span className="page-info">{historyPage} / {totalPages}</span>
                  <button className="page-btn" onClick={() => setHistoryPage(p => Math.min(totalPages, p + 1))} disabled={historyPage === totalPages}>Next →</button>
                </div>
              )}
            </>
          ) : history.length === 0 ? (
            <p className="empty-log">No productions yet — run your first scan to begin.</p>
          ) : (
            <p className="empty-log">No records match your filter.</p>
          )}
        </div>
      </main>

      {/* ── Cover Letter Modal ── */}
      {historyCLModal && (
        <div className="cl-modal-overlay" onClick={() => { setHistoryCLModal(null); setCopied(false); }}>
          <div className="cl-modal" onClick={e => e.stopPropagation()}>
            <div className="cl-modal-header">
              <span>Cover Letter — {historyCLModal.company_name}</span>
              <button className="cl-modal-close" onClick={() => { setHistoryCLModal(null); setCopied(false); }}>×</button>
            </div>
            <div className="cl-text">{historyCLModal.cover_letter}</div>
            <div className="cl-actions">
              <button className="cl-copy-btn" onClick={() => { navigator.clipboard.writeText(historyCLModal.cover_letter); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                {copied ? '✓ Copied' : '↑ Copy'}
              </button>
              {historyCLModal.cl_path && (
                <a href={`http://localhost:8000/api/download/${historyCLModal.cl_path.replace(/^trailerd\//, '')}`} className="cl-download-btn" download>↓ Download .docx</a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Mail Draft Modal ── */}
      {historyMailModal && (
        <div className="cl-modal-overlay" onClick={() => { setHistoryMailModal(null); setCopiedField(null); setHistoryDraftPath(null); }}>
          <div className="cl-modal mail-modal" onClick={e => e.stopPropagation()}>
            <div className="cl-modal-header">
              <div className="mail-modal-title">
                <span>Email Draft</span>
                <span className="mail-ollama-badge">via OpenAI</span>
              </div>
              <button className="cl-modal-close" onClick={() => { setHistoryMailModal(null); setCopiedField(null); setHistoryDraftPath(null); }}>×</button>
            </div>
            <div className="mail-modal-scroll">
              <div className="mail-modal-company">{historyMailModal.company_name}</div>
              {historyMailModal.to_emails?.length > 0 && (
                <div className="mail-modal-field">
                  <span className="mail-field-label">To</span>
                  <div className="mail-to-chips">
                    {historyMailModal.to_emails.map((email, i) => <span key={i} className="mail-to-chip">{email}</span>)}
                  </div>
                </div>
              )}
              <div className="mail-modal-field">
                <div className="mail-subject-row">
                  <span className="mail-field-label">Subject</span>
                  <button className="mail-copy-small" onClick={() => { navigator.clipboard.writeText(historyMailModal.subject); setCopiedField('ms'); setTimeout(() => setCopiedField(null), 2000); }}>
                    {copiedField === 'ms' ? '✓' : '↑ Copy'}
                  </button>
                </div>
                <div className="mail-subject-text">{historyMailModal.subject}</div>
              </div>
              <div className="mail-modal-field">
                <span className="mail-field-label">Body</span>
                <div className="mail-body-text mail-body-tall">{historyMailModal.body}</div>
              </div>
            </div>
            <div className="mail-modal-actions">
              <button className="mail-act-btn" onClick={() => { navigator.clipboard.writeText(historyMailModal.body); setCopiedField('mb'); setTimeout(() => setCopiedField(null), 2000); }}>
                {copiedField === 'mb' ? '✓ Copied' : '↑ Copy Body'}
              </button>
              {!historyDraftPath ? (
                <button className="mail-act-btn mail-save-btn" onClick={handleSaveHistoryDraft} disabled={historyDraftSaving}>
                  {historyDraftSaving ? '…Saving' : '💾 Save to Folder'}
                </button>
              ) : (
                <a href={`http://localhost:8000/api/download/${historyDraftPath.replace(/^trailerd\//, '')}`} className="mail-act-btn mail-dl-btn" download>
                  ↓ Download .txt
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

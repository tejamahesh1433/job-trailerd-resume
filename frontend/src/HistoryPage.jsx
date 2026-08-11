import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';
const PAGE_SIZE = 20;
const FETCH_LIMIT = 1000;

const STATUS_OPTIONS = ['Scanned', 'Matched', 'Submitted Profile', 'Applied', 'Phone Screen', 'Interview', 'Offer', 'Rejected'];

function scoreAccent(score) {
  if (score >= 85) return '#2ebd73';
  if (score >= 60) return '#c89b3c';
  return '#d94f4f';
}

function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Rejected/pre-screen records (e.g. Command Center C2C/C2H filtering) never go through
// resume scoring, so score=0/match_percentage=null there means "not scored", not "0%".
function formatScore(item) {
  if (item.match_percentage != null) return { text: `${item.match_percentage}%`, value: item.match_percentage };
  const after = item.scan_result?.after_score;
  if (after != null && after !== item.score) return { text: `${item.score}% → ${after}%`, value: after };
  if (item.score) return { text: `${item.score}%`, value: item.score };
  return { text: '—', value: null };
}

export default function HistoryPage({ onStatusChange, onRefreshHistory }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [page, setPage] = useState(1);
  const [vendorEdit, setVendorEdit] = useState({ vendor_company_name: '', vendor_contact_name: '', vendor_contact_email: '', vendor_contact_phone: '' });
  const [notesEdit, setNotesEdit] = useState('');
  const [savingId, setSavingId] = useState(null);
  const [researchingId, setResearchingId] = useState(null);
  const [researchError, setResearchError] = useState('');
  const [addOpen, setAddOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/history?limit=${FETCH_LIMIT}`);
      if (res.ok) {
        const data = await res.json();
        // Command Center's pre-screen rejects (no C2C/C2H terms, W2-only, etc.) are automatic
        // filtering noise, not real applications — keep them out of the History page entirely.
        setHistory(data.filter(item => !(item.source === 'command-center' && item.status === 'Rejected')));
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const refresh = () => { fetchAll(); onRefreshHistory?.(); };

  const sources = [...new Set(history.map(item => item.source || 'dashboard'))].sort();

  const q = search.trim().toLowerCase();
  const filtered = history.filter(item => {
    const matchesQuery = !q ||
      (item.company_name || '').toLowerCase().includes(q) ||
      (item.vendor_company_name || '').toLowerCase().includes(q);
    const matchesStatus = !statusFilter || (item.status || 'Scanned') === statusFilter;
    const matchesSource = !sourceFilter || (item.source || 'dashboard') === sourceFilter;
    return matchesQuery && matchesStatus && matchesSource;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const computedPage = Math.min(page, totalPages);
  const paged = filtered.slice((computedPage - 1) * PAGE_SIZE, computedPage * PAGE_SIZE);

  const toggleExpand = (item) => {
    setExpandedId(prev => {
      const next = prev === item.id ? null : item.id;
      if (next) {
        setVendorEdit({
          vendor_company_name: item.vendor_company_name || '',
          vendor_contact_name: item.vendor_contact_name || '',
          vendor_contact_email: item.vendor_contact_email || '',
          vendor_contact_phone: item.vendor_contact_phone || '',
        });
        setNotesEdit(item.user_notes || '');
      }
      return next;
    });
  };

  const handleVerifyVendor = async (id) => {
    setResearchingId(id);
    setResearchError('');
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}/vendor/research`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setVendorEdit(v => ({
          vendor_company_name: data.vendor_company_name || v.vendor_company_name,
          vendor_contact_name: data.vendor_contact_name || v.vendor_contact_name,
          vendor_contact_email: data.vendor_contact_email || v.vendor_contact_email,
          vendor_contact_phone: data.vendor_contact_phone || v.vendor_contact_phone,
        }));
      } else {
        const err = await res.json().catch(() => ({}));
        setResearchError(err.detail || 'Could not research vendor details.');
      }
    } catch {
      setResearchError('Could not research vendor details.');
    } finally {
      setResearchingId(null);
    }
  };

  const handleSaveVendor = async (id) => {
    setSavingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}/vendor`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vendorEdit),
      });
      if (res.ok) refresh();
    } catch { /* ignore */ }
    finally { setSavingId(null); }
  };

  const handleSaveNotes = async (id) => {
    setSavingId(id);
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}/notes`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notesEdit }),
      });
      if (res.ok) refresh();
    } catch { /* ignore */ }
    finally { setSavingId(null); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this record?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}`, { method: 'DELETE' });
      if (res.ok) refresh();
    } catch { /* ignore */ }
  };

  const handleStatusChange = async (id, newStatus) => {
    if (onStatusChange) {
      await onStatusChange(id, newStatus);
      fetchAll();
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/history/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) refresh();
    } catch { /* ignore */ }
  };

  return (
    <div className="app">
      <div className="grain" aria-hidden="true" />
      <main className="main-content">
        <div className="exp-page" style={{ maxWidth: '1400px' }}>
          <div className="exp-header">
            <h2 className="exp-title">History</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span className="exp-count">{filtered.length} of {history.length}</span>
              <button className="csv-btn" onClick={() => setAddOpen(true)}>+ Add Record</button>
              {history.length > 0 && (
                <a href={`${API_BASE}/api/history/csv?t=${Date.now()}`} className="csv-btn" download>↓ CSV Export</a>
              )}
            </div>
          </div>

          {addOpen && (
            <AddHistoryModal
              onClose={() => setAddOpen(false)}
              onSaved={() => { setAddOpen(false); refresh(); }}
            />
          )}

          {history.length > 0 && (
            <div className="history-filters">
              <input
                type="text"
                className="history-search"
                placeholder="Search client or vendor…"
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(1); }}
              />
              <select
                className="history-filter-select"
                value={statusFilter}
                onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
              >
                <option value="">All Statuses</option>
                {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <select
                className="history-filter-select"
                value={sourceFilter}
                onChange={e => { setSourceFilter(e.target.value); setPage(1); }}
              >
                <option value="">All Sources</option>
                {sources.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              {(search || statusFilter || sourceFilter) && (
                <button className="filter-clear-btn" onClick={() => { setSearch(''); setStatusFilter(''); setSourceFilter(''); }}>✕ Clear</button>
              )}
              <span className="history-count">{filtered.length} record{filtered.length !== 1 ? 's' : ''}</span>
            </div>
          )}

          {loading ? (
            <p className="empty-log">Loading history…</p>
          ) : paged.length === 0 ? (
            <p className="empty-log">{history.length === 0 ? 'No productions yet — run your first scan to begin.' : 'No records match your filter.'}</p>
          ) : (
            <>
              <table className="history-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Client</th>
                    <th>Vendor Company</th>
                    <th>Date</th>
                    <th>Score</th>
                    <th>Status</th>
                    <th>Source</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map((item, idx) => {
                    const score = formatScore(item);
                    return (
                    <React.Fragment key={item.id}>
                      <tr className={`history-row${expandedId === item.id ? ' jd-open' : ''}`}>
                        <td className="scene-num">{String((computedPage - 1) * PAGE_SIZE + idx + 1).padStart(2, '0')}</td>
                        <td className="company-col">
                          <button className="jd-toggle-btn" onClick={() => toggleExpand(item)} title={expandedId === item.id ? 'Hide details' : 'Edit details'}>
                            {expandedId === item.id ? '▾' : '▸'}
                          </button>
                          {item.company_name || 'Unknown'}
                          {item.rejection_reason && <span className="reject-reason" title={item.rejection_reason}>{item.rejection_reason}</span>}
                        </td>
                        <td className="vendor-col">{item.vendor_company_name || '—'}</td>
                        <td className="date-col">{formatDate(item.created_at)}</td>
                        <td className="score-col">
                          <span className="score-badge" style={{ color: score.value != null ? scoreAccent(score.value) : 'var(--muted)' }}>{score.text}</span>
                        </td>
                        <td>
                          <select
                            value={item.status || 'Scanned'}
                            onChange={e => handleStatusChange(item.id, e.target.value)}
                            className={`status-dropdown status-${(item.status || 'Scanned').toLowerCase().replace(' ', '-')}`}
                          >
                            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                          </select>
                          {item.status_updated_at && (
                            <div className="status-date">{formatDate(item.status_updated_at)}</div>
                          )}
                        </td>
                        <td className="date-col">{item.source || 'dashboard'}</td>
                        <td className="actions-col">
                          {item.file_path && (
                            <a href={`${API_BASE}/api/download/${item.file_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Download resume">↓</a>
                          )}
                          <button className="del-btn" onClick={() => handleDelete(item.id)} title="Delete record">×</button>
                        </td>
                      </tr>
                      {expandedId === item.id && (
                        <tr className="jd-preview-row">
                          <td colSpan="8">
                            <div className="jd-preview-content">
                              <div className="jd-preview-label">Vendor Details</div>
                              <div className="vendor-edit-grid">
                                <input
                                  type="text"
                                  placeholder="Vendor company name"
                                  value={vendorEdit.vendor_company_name}
                                  onChange={e => setVendorEdit(v => ({ ...v, vendor_company_name: e.target.value }))}
                                />
                                <input
                                  type="text"
                                  placeholder="Vendor contact name"
                                  value={vendorEdit.vendor_contact_name}
                                  onChange={e => setVendorEdit(v => ({ ...v, vendor_contact_name: e.target.value }))}
                                />
                                <input
                                  type="email"
                                  placeholder="Vendor contact email"
                                  value={vendorEdit.vendor_contact_email}
                                  onChange={e => setVendorEdit(v => ({ ...v, vendor_contact_email: e.target.value }))}
                                />
                                <input
                                  type="text"
                                  placeholder="Vendor contact phone"
                                  value={vendorEdit.vendor_contact_phone}
                                  onChange={e => setVendorEdit(v => ({ ...v, vendor_contact_phone: e.target.value }))}
                                />
                                <button className="vendor-save-btn" onClick={() => handleSaveVendor(item.id)} disabled={savingId === item.id}>
                                  {savingId === item.id ? 'Saving…' : 'Save Vendor'}
                                </button>
                                <button
                                  className="vendor-save-btn"
                                  onClick={() => handleVerifyVendor(item.id)}
                                  disabled={researchingId === item.id}
                                  title="Re-scan this job's description to fill in vendor details"
                                >
                                  {researchingId === item.id ? 'Researching…' : 'Verify Vendor Details'}
                                </button>
                              </div>
                              {researchError && researchingId === null && expandedId === item.id && (
                                <div style={{ color: '#d94f4f', fontSize: '0.85rem', marginTop: '-0.25rem', marginBottom: '0.5rem' }}>{researchError}</div>
                              )}

                              <div className="jd-preview-label">Notes</div>
                              <textarea
                                className="exp-search"
                                style={{ width: '100%', minHeight: '90px', marginBottom: '0.5rem' }}
                                placeholder="Add notes about this job…"
                                value={notesEdit}
                                onChange={e => setNotesEdit(e.target.value)}
                              />
                              <button className="vendor-save-btn" onClick={() => handleSaveNotes(item.id)} disabled={savingId === item.id}>
                                {savingId === item.id ? 'Saving…' : 'Save Notes'}
                              </button>

                              <div className="jd-preview-label" style={{ marginTop: '1rem' }}>Job Description</div>
                              <div className="jd-preview-text">{item.jd_text}</div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );})}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div className="history-pagination">
                  <button className="page-btn" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={computedPage === 1}>← Prev</button>
                  <span className="page-info">{computedPage} / {totalPages}</span>
                  <button className="page-btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={computedPage === totalPages}>Next →</button>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function AddHistoryModal({ onClose, onSaved }) {
  const [companyName, setCompanyName] = useState('');
  const [status, setStatus] = useState('Scanned');
  const [jdText, setJdText] = useState('');
  const [vendorCompanyName, setVendorCompanyName] = useState('');
  const [vendorContactName, setVendorContactName] = useState('');
  const [vendorContactEmail, setVendorContactEmail] = useState('');
  const [vendorContactPhone, setVendorContactPhone] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const handleSave = async () => {
    if (!companyName.trim()) { setErr('Client / company name is required.'); return; }
    setSaving(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/history`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: companyName.trim(),
          status,
          jd_text: jdText.trim(),
          vendor_company_name: vendorCompanyName.trim(),
          vendor_contact_name: vendorContactName.trim(),
          vendor_contact_email: vendorContactEmail.trim(),
          vendor_contact_phone: vendorContactPhone.trim(),
          user_notes: notes.trim(),
        }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || 'Failed to add record');
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
          <h3>Add Record</h3>
          <button className="cmd-modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="cmd-modal-body">
          <label className="cmd-modal-label">Client / Company *</label>
          <input className="cmd-select" style={{ width: '100%' }} value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="e.g. Acme Corp" />
          <label className="cmd-modal-label">Status</label>
          <select className="cmd-select" style={{ width: '100%' }} value={status} onChange={e => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="cmd-modal-label">Vendor Company</label>
          <input className="cmd-select" style={{ width: '100%' }} value={vendorCompanyName} onChange={e => setVendorCompanyName(e.target.value)} placeholder="e.g. Staffing Partners LLC" />
          <label className="cmd-modal-label">Vendor Contact Name</label>
          <input className="cmd-select" style={{ width: '100%' }} value={vendorContactName} onChange={e => setVendorContactName(e.target.value)} />
          <label className="cmd-modal-label">Vendor Contact Email</label>
          <input className="cmd-select" style={{ width: '100%' }} type="email" value={vendorContactEmail} onChange={e => setVendorContactEmail(e.target.value)} />
          <label className="cmd-modal-label">Vendor Contact Phone</label>
          <input className="cmd-select" style={{ width: '100%' }} value={vendorContactPhone} onChange={e => setVendorContactPhone(e.target.value)} />
          <label className="cmd-modal-label">Job Description</label>
          <textarea className="cmd-select" style={{ width: '100%', minHeight: '90px', resize: 'vertical' }} value={jdText} onChange={e => setJdText(e.target.value)} placeholder="Optional" />
          <label className="cmd-modal-label">Notes</label>
          <textarea className="cmd-select" style={{ width: '100%', minHeight: '70px', resize: 'vertical' }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional" />
          {err && <div className="cmd-modal-error">{err}</div>}
        </div>
        <div className="cmd-modal-footer">
          <button className="cmd-filter-pill" onClick={onClose}>Cancel</button>
          <button className="cmd-cta cmd-cta-primary" onClick={handleSave} disabled={saving} style={{ opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Saving…' : 'Save Record'}
          </button>
        </div>
      </div>
    </div>
  );
}

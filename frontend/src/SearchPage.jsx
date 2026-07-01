import React, { useState } from 'react';

export default function SearchPage({ onSelectRecord }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [editingAddressId, setEditingAddressId] = useState(null);
  const [addressDraft, setAddressDraft] = useState('');
  const [savingAddressId, setSavingAddressId] = useState(null);
  const [editingNotesId, setEditingNotesId] = useState(null);
  const [notesDraft, setNotesDraft] = useState('');
  const [savingNotesId, setSavingNotesId] = useState(null);

  const handleSearch = async () => {
    if (query.trim().length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/search?q=${encodeURIComponent(query.trim())}&limit=50`);
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Search failed'); setResults([]); return; }
      setResults(data.results || []);
      setSearched(true);
    } catch {
      setError('Failed to connect to server.');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAddress = async (recordId) => {
    setSavingAddressId(recordId);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${recordId}/address`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: addressDraft }),
      });
      if (res.ok) {
        setResults(prev => prev.map(r => r.id === recordId ? { ...r, user_address: addressDraft } : r));
        setEditingAddressId(null);
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to save address');
      }
    } catch {
      setError('Failed to save address.');
    } finally {
      setSavingAddressId(null);
    }
  };

  const startEditAddress = (record) => {
    setEditingAddressId(record.id);
    setAddressDraft(record.user_address || '');
  };

  const handleSaveNotes = async (recordId) => {
    setSavingNotesId(recordId);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${recordId}/notes`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notesDraft }),
      });
      if (res.ok) {
        setResults(prev => prev.map(r => r.id === recordId ? { ...r, user_notes: notesDraft } : r));
        setEditingNotesId(null);
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to save notes');
      }
    } catch {
      setError('Failed to save notes.');
    } finally {
      setSavingNotesId(null);
    }
  };

  const startEditNotes = (record) => {
    setEditingNotesId(record.id);
    setNotesDraft(record.user_notes || '');
  };

  const scoreColor = (score) => {
    if (score >= 85) return 'var(--success)';
    if (score >= 60) return 'var(--gold)';
    return 'var(--danger)';
  };

  return (
    <div className="app">
      <div className="grain" aria-hidden="true" />
      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <svg className="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" />
              <line x1="16.5" y1="16.5" x2="21" y2="21" />
            </svg>
            <h1>SEARCH</h1>
          </div>
          <p className="site-tagline">Find JD Records<br />Search by name, email, or position</p>
        </div>
        <div className="header-rule" />
      </header>

      <main className="main-content">
        <div className="panel panel-wide panel-enter">
          <div className="panel-tag">
            <span className="panel-num">01</span>
            <span className="panel-title">Search Records</span>
          </div>

          <div className="search-bar-row">
            <input
              type="text"
              className="search-input"
              placeholder="Search by company, email, position, location..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSearch(); }}
            />
            <button className="action-btn search-go-btn" onClick={handleSearch} disabled={loading || query.trim().length < 2}>
              {loading ? '...' : 'Search'}
            </button>
          </div>

          {error && <div className="error-banner" style={{ marginTop: '1rem' }}>! {error}</div>}

          {searched && results.length === 0 && !loading && (
            <div className="search-empty">No records found for "{query}"</div>
          )}

          {results.length > 0 && (
            <div className="search-results-count">{results.length} result{results.length !== 1 ? 's' : ''} found</div>
          )}

          <div className="search-results">
            {results.map(r => (
              <div key={r.id} className="search-card">
                <div className="search-card-header">
                  <div className="search-card-company">{r.company_name}</div>
                  <div className="search-card-badges">
                    {r.local_required && <span className="search-badge local">LOCAL ONLY</span>}
                    <span className="search-badge" style={{ color: scoreColor(r.score || r.match_percentage || 0), borderColor: scoreColor(r.score || r.match_percentage || 0) }}>
                      {r.source === 'job-finder' ? `${r.match_percentage || 0}% fit` : `${r.score || 0}% ATS`}
                    </span>
                    <span className={`search-badge status-${(r.status || 'Scanned').toLowerCase().replace(' ', '-')}`}>
                      {r.status || 'Scanned'}
                    </span>
                  </div>
                </div>

                <div className="search-card-grid">
                  <div className="search-info-item">
                    <span className="search-info-label">Position</span>
                    <span className="search-info-value">{r.position || 'Not specified'}</span>
                  </div>
                  <div className="search-info-item">
                    <span className="search-info-label">Location</span>
                    <span className="search-info-value">{r.location || 'Not specified'}</span>
                  </div>
                  <div className="search-info-item">
                    <span className="search-info-label">Local Required</span>
                    <span className="search-info-value" style={r.local_required ? { color: 'var(--danger)', fontWeight: 600 } : {}}>
                      {r.local_required ? 'Yes' : 'No'}
                    </span>
                  </div>
                  <div className="search-info-item">
                    <span className="search-info-label">Date</span>
                    <span className="search-info-value">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '-'}
                    </span>
                  </div>
                </div>

                {r.emails.length > 0 && (
                  <div className="search-emails">
                    <span className="search-info-label">Emails Found</span>
                    <div className="search-email-chips">
                      {r.emails.map((email, i) => (
                        <span key={i} className="search-email-chip" onClick={() => navigator.clipboard.writeText(email)} title="Click to copy">
                          {email}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {r.recruiter_name && (
                  <div className="search-recruiter">
                    <span className="search-info-label">Recruiter</span>
                    <span className="search-info-value">{r.recruiter_name}</span>
                  </div>
                )}

                {/* My Address — editable per JD */}
                <div className="search-address">
                  <span className="search-info-label">My Address</span>
                  {editingAddressId === r.id ? (
                    <div className="search-address-edit">
                      <textarea
                        className="search-address-input"
                        placeholder="Enter your address for this JD..."
                        value={addressDraft}
                        onChange={e => setAddressDraft(e.target.value)}
                        rows={2}
                      />
                      <div className="search-address-btns">
                        <button
                          className="search-address-save"
                          onClick={() => handleSaveAddress(r.id)}
                          disabled={savingAddressId === r.id}
                        >
                          {savingAddressId === r.id ? '...' : 'Save'}
                        </button>
                        <button
                          className="search-address-cancel"
                          onClick={() => setEditingAddressId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="search-address-display" onClick={() => startEditAddress(r)}>
                      {r.user_address ? (
                        <span className="search-address-text">{r.user_address}</span>
                      ) : (
                        <span className="search-address-placeholder">+ Add address</span>
                      )}
                      <span className="search-address-edit-icon" title="Edit address">&#9998;</span>
                    </div>
                  )}
                </div>

                {/* Notes — editable per JD */}
                <div className="search-notes">
                  <span className="search-info-label">Notes</span>
                  {editingNotesId === r.id ? (
                    <div className="search-notes-edit">
                      <textarea
                        className="search-notes-input"
                        placeholder="Add notes for this application..."
                        value={notesDraft}
                        onChange={e => setNotesDraft(e.target.value)}
                        rows={2}
                      />
                      <div className="search-notes-btns">
                        <button
                          className="search-notes-save"
                          onClick={() => handleSaveNotes(r.id)}
                          disabled={savingNotesId === r.id}
                        >
                          {savingNotesId === r.id ? '...' : 'Save'}
                        </button>
                        <button
                          className="search-notes-cancel"
                          onClick={() => setEditingNotesId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="search-notes-display" onClick={() => startEditNotes(r)}>
                      {r.user_notes ? (
                        <span className="search-notes-text">{r.user_notes}</span>
                      ) : (
                        <span className="search-notes-placeholder">+ Add notes</span>
                      )}
                      <span className="search-notes-edit-icon" title="Edit notes">&#9998;</span>
                    </div>
                  )}
                </div>

                <div className="search-card-actions">
                  <button className="search-expand-btn" onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}>
                    {expandedId === r.id ? 'Hide JD Preview' : 'Show JD Preview'}
                  </button>
                  {onSelectRecord && (
                    <button className="search-open-btn" onClick={() => onSelectRecord(r)}>
                      Open in Dashboard
                    </button>
                  )}
                </div>

                {expandedId === r.id && r.jd_preview && (
                  <div className="search-jd-preview">
                    {r.jd_preview}...
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

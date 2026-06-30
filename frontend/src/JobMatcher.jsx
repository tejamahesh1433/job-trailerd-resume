import React, { useState } from 'react';

export default function JobMatcher({ onApply }) {
  const [jdText, setJdText] = useState('');
  const [jdUrl, setJdUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);

  const handleFetchUrl = async () => {
    if (!jdUrl.trim()) return;
    setFetchingUrl(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/job-matcher/fetch-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `url=${encodeURIComponent(jdUrl.trim())}`
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || 'Failed to fetch URL');
        return;
      }
      setJdText(data.jd_text);
    } catch (err) {
      if (err instanceof TypeError && err.message === 'Failed to fetch') {
        setError('Cannot reach the backend server. Make sure the backend is running (docker compose up or uvicorn).');
      } else {
        setError(err.message || 'Failed to fetch URL');
      }
    } finally {
      setFetchingUrl(false);
    }
  };

  const handleScan = async () => {
    if (!jdText.trim()) {
      setError('Please paste a job description or fetch from URL');
      return;
    }

    setLoading(true);
    setError(null);
    setAnalysis(null);

    try {
      let body = `jd_text=${encodeURIComponent(jdText)}`;
      if (jdUrl.trim()) {
        body += `&source_url=${encodeURIComponent(jdUrl.trim())}`;
      }
      const response = await fetch('http://localhost:8000/api/job-matcher/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body
      });

      const data = await response.json();

      if (!response.ok) {
        setError(data.detail || 'Failed to analyze job');
        return;
      }

      setAnalysis(data);
    } catch (err) {
      setError(err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setJdText('');
    setJdUrl('');
    setAnalysis(null);
    setError(null);
  };

  const handleApply = () => {
    if (onApply) {
      onApply(jdText);
    }
  };

  // Hard reject screen
  if (analysis && !analysis.can_apply && analysis.hard_reject) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h2 style={styles.headerTitle}>Job Finder</h2>
        </div>

        <div style={styles.rejectionCard}>
          <div style={styles.rejectionIcon}>&times;</div>
          <h3 style={styles.rejectionTitle}>Not a Good Fit</h3>
          {analysis.company_name && <div style={styles.rejectionCompany}>{analysis.company_name}</div>}
          <p style={styles.rejectionMessage}>{analysis.error}</p>
          <div style={styles.savedBadge}>Saved to history</div>

          <button style={styles.backButton} onClick={() => setAnalysis(null)}>
            Try Another Job
          </button>
        </div>
      </div>
    );
  }

  // Success screen with analysis
  if (analysis && analysis.can_apply) {
    const category = analysis.job_category || {};
    const subCategories = category.sub_categories || [];
    const missingSkills = subCategories.filter(s => s.confidence < 0.6);
    const scoreColor = analysis.match_percentage >= 85 ? 'var(--success)' : analysis.match_percentage >= 60 ? 'var(--gold)' : 'var(--danger)';

    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h2 style={styles.headerTitle}>Job Finder — Analysis</h2>
        </div>

        <div style={styles.analysisCard}>
          {/* Match Score */}
          <div style={styles.scoreSection}>
            <div style={{ ...styles.scoreCircle, borderColor: scoreColor }}>
              <div style={{ ...styles.scoreNumber, color: scoreColor }}>{analysis.match_percentage}%</div>
              <div style={styles.scoreLabel}>Match</div>
            </div>
          </div>

          {/* Company & Role */}
          <div style={styles.section}>
            <h3 style={styles.sectionTitle}>Job Profile</h3>
            <div style={styles.jobInfo}>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Company</span>
                <span style={styles.jobInfoVal}>{analysis.company_name}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Location</span>
                <span style={styles.jobInfoVal}>{analysis.location || 'Not specified'}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Role Type</span>
                <span style={styles.jobInfoVal}>{category.name || 'Unknown'}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Employment</span>
                <span style={styles.jobInfoVal}>{(analysis.employment_type || 'Unknown').toUpperCase()}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Experience</span>
                <span style={styles.jobInfoVal}>{analysis.experience_years}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Salary</span>
                <span style={styles.jobInfoVal}>{analysis.salary_range || 'Not specified'}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Visa / Auth</span>
                <span style={styles.jobInfoVal}>{analysis.visa_requirements || 'Not specified'}</span>
              </div>
              <div style={styles.jobInfoRow}>
                <span style={styles.jobInfoKey}>Clearance</span>
                <span style={styles.jobInfoVal}>{analysis.clearance_level || 'Not specified'}</span>
              </div>
            </div>
          </div>

          {/* Warnings */}
          {analysis.warnings && analysis.warnings.length > 0 && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Considerations</h3>
              {analysis.warnings.map((warning, idx) => (
                <div key={idx} style={styles.warningItem}>
                  <p style={{ margin: 0 }}>{warning}</p>
                </div>
              ))}
            </div>
          )}

          {/* Job Category Breakdown */}
          {subCategories.length > 0 && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Skills Breakdown</h3>
              <div style={styles.skillsList}>
                {subCategories.map((skill, idx) => (
                  <div key={idx} style={styles.skillItem}>
                    <div style={styles.skillItemHeader}>
                      <span>{skill.name}</span>
                      <span style={{ color: skill.confidence > 0.7 ? 'var(--success)' : 'var(--gold)', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', fontWeight: 700 }}>
                        {Math.round(skill.confidence * 100)}%
                      </span>
                    </div>
                    <div style={styles.skillBar}>
                      <div
                        style={{
                          ...styles.skillFill,
                          width: `${skill.confidence * 100}%`,
                          backgroundColor: skill.confidence > 0.7 ? 'var(--success)' : 'var(--gold)'
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Missing Skills */}
          {missingSkills.length > 0 && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Skills to Highlight</h3>
              <div style={styles.missingSkills}>
                {missingSkills.map((skill, idx) => (
                  <span key={idx} style={styles.skillTag}>
                    {skill.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Extracted Keywords */}
          {analysis.extracted_keywords && Object.values(analysis.extracted_keywords).some(kws => kws.length > 0) && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Detected Keywords</h3>
              <div style={styles.keywordGroups}>
                {Object.entries(analysis.extracted_keywords).map(([cat, kws]) =>
                  kws.length > 0 && (
                    <div key={cat} style={styles.keywordGroup}>
                      <span style={styles.keywordGroupLabel}>{cat}</span>
                      <div style={styles.keywordChips}>
                        {kws.map((kw, i) => (
                          <span key={i} style={styles.keywordChip}>{kw}</span>
                        ))}
                      </div>
                    </div>
                  )
                )}
              </div>
            </div>
          )}

          {/* Source URL */}
          {analysis.source_url && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Source</h3>
              <a href={analysis.source_url} target="_blank" rel="noopener noreferrer" style={styles.sourceLink}>{analysis.source_url}</a>
            </div>
          )}

          <div style={styles.savedBadge}>Saved to history</div>

          {/* Action Buttons */}
          <div style={styles.actionButtons}>
            <button style={styles.applyButton} onClick={handleApply}>
              Apply — Tailor Resume
            </button>
            <button style={styles.backButton} onClick={() => setAnalysis(null)}>
              Try Another
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Initial input screen
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.headerTitle}>Job Finder</h2>
        <p style={styles.subheader}>
          Check if a job matches your profile before tailoring your resume
        </p>
      </div>

      {error && (
        <div style={styles.errorBox}>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      <div style={styles.inputSection}>
        <div style={styles.panelTag}>
          <span style={styles.panelNum}>01</span>
          <span style={styles.panelTitle}>Scan</span>
        </div>

        {/* URL Input */}
        <label style={styles.label}>Job Posting URL <span style={{ fontWeight: 400, opacity: 0.5 }}>(optional)</span></label>
        <div style={styles.urlRow}>
          <input
            type="url"
            value={jdUrl}
            onChange={(e) => setJdUrl(e.target.value)}
            placeholder="https://linkedin.com/jobs/... or any job board URL"
            style={styles.urlInput}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleFetchUrl(); } }}
          />
          <button
            style={{ ...styles.fetchButton, ...(fetchingUrl ? styles.fetchButtonLoading : {}) }}
            onClick={handleFetchUrl}
            disabled={fetchingUrl || !jdUrl.trim()}
          >
            {fetchingUrl ? 'Fetching...' : 'Fetch JD'}
          </button>
        </div>
        {jdUrl.trim() && <div style={styles.urlHint}>Press Enter or click Fetch to extract JD text from URL</div>}

        <div style={styles.dividerRow}>
          <div style={styles.dividerLine} />
          <span style={styles.dividerText}>or paste directly</span>
          <div style={styles.dividerLine} />
        </div>

        {/* JD Text Input */}
        <label style={styles.label}>Job Description</label>
        <textarea
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          placeholder="Paste the complete job description here..."
          style={styles.textarea}
          rows={12}
          onKeyDown={e => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); handleScan(); } }}
        />
        {jdText.length > 0 && <div style={styles.charCount}>{jdText.length} chars</div>}

        <div style={styles.buttonGroup}>
          <button
            style={{ ...styles.scanButton, ...(loading ? styles.scanButtonLoading : {}) }}
            onClick={handleScan}
            disabled={loading || !jdText.trim()}
          >
            {loading ? 'Analyzing...' : 'SCAN JD'}
          </button>
          <button
            style={styles.clearButton}
            onClick={handleClear}
            disabled={!jdText.trim() && !jdUrl.trim() && !analysis}
          >
            Clear
          </button>
        </div>
      </div>

      {/* How it works */}
      <div style={styles.tipsSection}>
        <h3 style={styles.sectionTitle}>How It Works</h3>
        <div style={styles.tipsList}>
          <div style={styles.tipItem}><span style={styles.tipBullet}>01</span> Checks if role is lead/management (auto-skips)</div>
          <div style={styles.tipItem}><span style={styles.tipBullet}>02</span> Verifies visa/green card eligibility</div>
          <div style={styles.tipItem}><span style={styles.tipBullet}>03</span> Checks employment type (C2C/C2H preferred)</div>
          <div style={styles.tipItem}><span style={styles.tipBullet}>04</span> AI-powered job categorization and skill matching</div>
          <div style={styles.tipItem}><span style={styles.tipBullet}>05</span> Calculates overall match percentage</div>
          <div style={styles.tipItem}><span style={styles.tipBullet}>06</span> One-click apply sends JD to resume tailor</div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    minHeight: '100vh',
    padding: '3.5rem 3rem',
    backgroundColor: 'var(--ink)',
    color: 'var(--cream)',
    maxWidth: '900px',
    margin: '0 auto',
  },
  header: {
    marginBottom: '2.5rem',
  },
  headerTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: '2.8rem',
    fontWeight: 700,
    color: 'var(--cream)',
    letterSpacing: '0.1em',
    marginBottom: '0.5rem',
    lineHeight: 1,
  },
  subheader: {
    fontFamily: 'var(--font-mono)',
    color: 'var(--muted)',
    fontSize: '0.68rem',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginTop: '0.75rem',
    lineHeight: 1.8,
  },
  panelTag: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '0.9rem',
    marginBottom: '2.25rem',
  },
  panelNum: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.65rem',
    fontWeight: 700,
    color: 'var(--gold)',
    letterSpacing: '0.06em',
  },
  panelTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: '1.5rem',
    fontWeight: 600,
    color: 'var(--cream)',
    letterSpacing: '0.04em',
  },
  inputSection: {
    margin: '0 0 2.5rem',
    backgroundColor: 'var(--panel)',
    border: '1px solid var(--border)',
    borderTop: '2px solid var(--gold)',
    padding: '2.5rem',
    position: 'relative',
  },
  label: {
    display: 'block',
    marginBottom: '0.6rem',
    fontFamily: 'var(--font-mono)',
    fontWeight: 700,
    fontSize: '0.62rem',
    letterSpacing: '0.14em',
    color: 'var(--muted)',
    textTransform: 'uppercase',
  },
  textarea: {
    width: '100%',
    minHeight: '220px',
    padding: '1rem 1.25rem',
    paddingBottom: '2rem',
    backgroundColor: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '1px',
    fontFamily: 'var(--font-body)',
    fontSize: '0.88rem',
    lineHeight: '1.65',
    color: 'var(--cream)',
    resize: 'vertical',
    boxSizing: 'border-box',
    outline: 'none',
  },
  charCount: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6rem',
    color: 'var(--muted)',
    textAlign: 'right',
    marginTop: '0.3rem',
  },
  buttonGroup: {
    display: 'flex',
    gap: '0.75rem',
    marginTop: '1.25rem',
  },
  scanButton: {
    flex: 2,
    padding: '1.1rem 2rem',
    backgroundColor: 'var(--gold)',
    color: 'var(--ink)',
    border: 'none',
    borderRadius: '1px',
    cursor: 'pointer',
    fontFamily: 'var(--font-display)',
    fontWeight: 700,
    fontSize: '1.3rem',
    letterSpacing: '0.18em',
    transition: 'background 0.18s',
  },
  scanButtonLoading: {
    backgroundColor: 'var(--surface-alt)',
    color: 'var(--gold)',
    border: '1px solid var(--gold)',
  },
  clearButton: {
    flex: 1,
    padding: '1.1rem 2rem',
    backgroundColor: 'var(--surface-alt)',
    color: 'var(--muted)',
    border: '1px solid var(--border)',
    borderRadius: '1px',
    cursor: 'pointer',
    fontFamily: 'var(--font-display)',
    fontWeight: 700,
    fontSize: '1rem',
    letterSpacing: '0.1em',
    transition: 'background 0.15s, color 0.15s, border-color 0.15s',
  },
  errorBox: {
    margin: '0 0 1.5rem',
    padding: '0.75rem 1rem',
    backgroundColor: 'rgba(217, 79, 79, 0.08)',
    color: 'var(--danger)',
    borderRadius: '1px',
    borderLeft: '3px solid var(--danger)',
    border: '1px solid rgba(217, 79, 79, 0.4)',
    fontSize: '0.85rem',
    fontWeight: 500,
  },
  analysisCard: {
    margin: '0 0 2.5rem',
    backgroundColor: 'var(--panel)',
    border: '1px solid var(--border)',
    borderTop: '2px solid var(--gold)',
    padding: '2.5rem',
  },
  scoreSection: {
    textAlign: 'center',
    marginBottom: '2.5rem',
    paddingBottom: '2rem',
    borderBottom: '1px solid var(--border)',
  },
  scoreCircle: {
    width: '130px',
    height: '130px',
    margin: '0 auto',
    borderRadius: '50%',
    backgroundColor: 'var(--surface)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    border: '3px solid var(--gold)',
  },
  scoreNumber: {
    fontFamily: 'var(--font-mono)',
    fontSize: '2.5rem',
    fontWeight: 700,
    color: 'var(--gold)',
    lineHeight: 1,
  },
  scoreLabel: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6rem',
    fontWeight: 700,
    color: 'var(--muted)',
    marginTop: '6px',
    textTransform: 'uppercase',
    letterSpacing: '0.14em',
  },
  section: {
    marginBottom: '2rem',
    paddingBottom: '2rem',
    borderBottom: '1px solid var(--border)',
  },
  sectionTitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.62rem',
    fontWeight: 700,
    letterSpacing: '0.12em',
    color: 'var(--muted)',
    textTransform: 'uppercase',
    marginBottom: '1rem',
  },
  jobInfo: {
    backgroundColor: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '1px',
    overflow: 'hidden',
  },
  jobInfoRow: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '1rem',
    padding: '0.6rem 1.25rem',
    borderBottom: '1px solid var(--border)',
  },
  jobInfoKey: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.58rem',
    fontWeight: 700,
    letterSpacing: '0.1em',
    color: 'var(--muted)',
    textTransform: 'uppercase',
    flexShrink: 0,
    width: '90px',
  },
  jobInfoVal: {
    fontSize: '0.85rem',
    color: 'var(--cream)',
    fontWeight: 500,
  },
  warningItem: {
    padding: '0.75rem 1rem',
    backgroundColor: 'rgba(200, 155, 60, 0.08)',
    borderLeft: '3px solid var(--gold)',
    border: '1px solid rgba(200, 155, 60, 0.25)',
    borderRadius: '1px',
    marginBottom: '0.5rem',
    fontSize: '0.83rem',
    color: 'var(--cream-dim)',
  },
  skillsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.85rem',
  },
  skillItem: {
    fontSize: '0.82rem',
    color: 'var(--cream-dim)',
  },
  skillItemHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '4px',
  },
  skillBar: {
    height: '4px',
    backgroundColor: 'var(--border)',
    borderRadius: '2px',
    overflow: 'hidden',
  },
  skillFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  missingSkills: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.5rem',
  },
  skillTag: {
    display: 'inline-block',
    backgroundColor: 'rgba(217, 79, 79, 0.08)',
    border: '1px solid rgba(217, 79, 79, 0.3)',
    color: 'var(--danger)',
    padding: '0.25rem 0.65rem',
    borderRadius: '1px',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.68rem',
    fontWeight: 500,
    letterSpacing: '0.04em',
  },
  keywordGroups: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.85rem',
  },
  keywordGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  keywordGroupLabel: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.58rem',
    fontWeight: 700,
    color: 'var(--muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  keywordChips: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.4rem',
  },
  keywordChip: {
    display: 'inline-block',
    backgroundColor: 'rgba(46, 189, 115, 0.08)',
    border: '1px solid rgba(46, 189, 115, 0.3)',
    color: 'var(--success)',
    padding: '0.2rem 0.55rem',
    borderRadius: '1px',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.65rem',
    fontWeight: 500,
    letterSpacing: '0.04em',
  },
  actionButtons: {
    display: 'flex',
    gap: '0.75rem',
    marginTop: '0.5rem',
  },
  applyButton: {
    flex: 2,
    padding: '1.1rem',
    backgroundColor: 'var(--gold)',
    color: 'var(--ink)',
    border: 'none',
    borderRadius: '1px',
    cursor: 'pointer',
    fontFamily: 'var(--font-display)',
    fontWeight: 700,
    fontSize: '1.2rem',
    letterSpacing: '0.14em',
    transition: 'background 0.18s',
  },
  backButton: {
    flex: 1,
    padding: '1.1rem 1.5rem',
    backgroundColor: 'var(--surface-alt)',
    color: 'var(--muted)',
    border: '1px solid var(--border)',
    borderRadius: '1px',
    cursor: 'pointer',
    fontFamily: 'var(--font-display)',
    fontWeight: 700,
    fontSize: '1rem',
    letterSpacing: '0.1em',
    transition: 'background 0.15s, color 0.15s, border-color 0.15s',
  },
  rejectionCard: {
    maxWidth: '500px',
    margin: '3rem auto',
    backgroundColor: 'var(--panel)',
    border: '1px solid var(--border)',
    borderTop: '2px solid var(--danger)',
    padding: '3rem',
    textAlign: 'center',
  },
  rejectionIcon: {
    fontFamily: 'var(--font-mono)',
    fontSize: '3rem',
    lineHeight: 1,
    color: 'var(--danger)',
    fontWeight: 700,
  },
  rejectionTitle: {
    marginTop: '1rem',
    color: 'var(--danger)',
    fontFamily: 'var(--font-display)',
    fontSize: '1.5rem',
    letterSpacing: '0.04em',
  },
  rejectionMessage: {
    color: 'var(--cream-dim)',
    fontSize: '0.88rem',
    marginBottom: '2rem',
    marginTop: '1rem',
    lineHeight: '1.75',
  },
  tipsSection: {
    margin: '0 0 2.5rem',
    backgroundColor: 'var(--panel)',
    border: '1px solid var(--border)',
    borderLeft: '2px solid var(--gold)',
    padding: '2rem 2.5rem',
    borderRadius: '1px',
  },
  tipsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  tipItem: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '0.75rem',
    fontSize: '0.82rem',
    color: 'var(--cream-dim)',
    lineHeight: 1.6,
  },
  tipBullet: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6rem',
    fontWeight: 700,
    color: 'var(--gold)',
    letterSpacing: '0.06em',
    flexShrink: 0,
  },
  urlRow: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '0.5rem',
  },
  urlInput: {
    flex: 1,
    padding: '0.75rem 1rem',
    backgroundColor: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '1px',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.82rem',
    color: 'var(--cream)',
    outline: 'none',
    boxSizing: 'border-box',
  },
  urlHint: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.58rem',
    color: 'var(--muted)',
    letterSpacing: '0.06em',
    marginBottom: '0.5rem',
  },
  fetchButton: {
    padding: '0.75rem 1.5rem',
    backgroundColor: 'var(--surface-alt)',
    color: 'var(--gold)',
    border: '1px solid var(--border-warm)',
    borderRadius: '1px',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.68rem',
    fontWeight: 700,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s, border-color 0.15s',
  },
  fetchButtonLoading: {
    color: 'var(--muted)',
    borderColor: 'var(--border)',
  },
  dividerRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    margin: '1.25rem 0',
  },
  dividerLine: {
    flex: 1,
    height: '1px',
    backgroundColor: 'var(--border)',
  },
  dividerText: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.58rem',
    fontWeight: 700,
    color: 'var(--muted)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    flexShrink: 0,
  },
  savedBadge: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6rem',
    fontWeight: 700,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: 'var(--success)',
    backgroundColor: 'rgba(46, 189, 115, 0.08)',
    border: '1px solid rgba(46, 189, 115, 0.3)',
    padding: '0.4rem 0.75rem',
    borderRadius: '1px',
    textAlign: 'center',
    marginTop: '0.5rem',
    marginBottom: '0.5rem',
  },
  rejectionCompany: {
    fontFamily: 'var(--font-display)',
    fontSize: '1.2rem',
    fontWeight: 600,
    color: 'var(--cream)',
    letterSpacing: '0.03em',
    marginTop: '0.75rem',
  },
  sourceLink: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.75rem',
    color: 'var(--gold)',
    textDecoration: 'underline',
    textDecorationColor: 'var(--border-warm)',
    textUnderlineOffset: '3px',
    wordBreak: 'break-all',
  },
};

import { useState, useEffect } from 'react';
import { JobRow } from './CommandCenter';
import JobDetailWorkspace from './JobDetailWorkspace';
import './index.css';

const PAGE_SIZE = 20;

export default function JobMatches({ onBack, onSendToTailor, onSaveToApplications, selectedResumeName }) {
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedJobId, setSelectedJobId] = useState(null);

  useEffect(() => {
    fetchPage(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const fetchPage = async (p) => {
    try {
      setLoading(true);
      const res = await fetch(`http://localhost:8000/api/jobs/matches?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`);
      if (!res.ok) throw new Error('Failed to load matches');
      const json = await res.json();
      setJobs(json.jobs || []);
      setTotal(json.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="cmd-container">
      <div className="cmd-header">
        <div>
          <button className="cmd-back-btn" onClick={() => onBack && onBack()}>&larr; Back to Command Center</button>
          <h1 className="cmd-title" style={{ marginTop: '0.5rem' }}>All Job Matches</h1>
          <p className="cmd-subtitle">{total} match{total !== 1 ? 'es' : ''} found, best score first</p>
        </div>
      </div>

      {error && <div className="error-banner" style={{ marginTop: '1.5rem' }}>{error}</div>}

      {loading ? (
        <div className="cmd-loading">Loading matches...</div>
      ) : jobs.length === 0 ? (
        <div className="cmd-panel" style={{ marginTop: '2rem', textAlign: 'center', color: 'var(--muted)', padding: '2rem' }}>
          No matches yet. Go back and run a search from the Command Center.
        </div>
      ) : (
        <>
          <div className="cmd-panel" style={{ marginTop: '2rem' }}>
            <div className="cmd-jobs-list" style={{ display: 'flex', flexDirection: 'column' }}>
              {jobs.map((job, idx) => (
                <JobRow
                  key={job.record_id || idx}
                  index={page * PAGE_SIZE + idx + 1}
                  job={job}
                  onSendToTailor={onSendToTailor}
                  onSaveToApplications={onSaveToApplications}
                  onOpenDetail={(j) => setSelectedJobId(j.record_id)}
                />
              ))}
            </div>
          </div>

          <div className="cmd-pagination">
            <button
              className="cmd-filter-pill"
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              style={{ opacity: page === 0 ? 0.5 : 1 }}
            >
              &larr; Prev
            </button>
            <span className="cmd-pagination-label">Page {page + 1} of {totalPages}</span>
            <button
              className="cmd-filter-pill"
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              style={{ opacity: page >= totalPages - 1 ? 0.5 : 1 }}
            >
              Next &rarr;
            </button>
          </div>
        </>
      )}

      <JobDetailWorkspace
        jobId={selectedJobId}
        onClose={() => setSelectedJobId(null)}
        onSendToTailor={onSendToTailor}
        onSaveToApplications={onSaveToApplications}
        onJobUpdated={() => fetchPage(page)}
        selectedResumeName={selectedResumeName}
      />
    </div>
  );
}

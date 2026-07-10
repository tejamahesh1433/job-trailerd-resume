import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import JobDetailWorkspace from './JobDetailWorkspace';

function baseJob(overrides = {}) {
  return {
    record_id: 7,
    title: 'Platform Engineer',
    company: 'Globex',
    location: 'Austin, TX',
    score: 82,
    tags: ['Remote', 'C2C'],
    reasons: ['Strong AWS/Kubernetes overlap'],
    next_action: 'Apply now — strong match',
    description: 'A'.repeat(200),
    url: 'https://example.com/job/7',
    status: 'Found',
    status_updated_at: null,
    created_at: '2026-01-01T00:00:00',
    source: 'command-center',
    user_notes: '',
    rejection_reason: null,
    file_path: null,
    cover_letter_generated: false,
    drafts: {},
    contact: null,
    ...overrides,
  };
}

function mockFetchSequence(job) {
  globalThis.fetch = vi.fn((url, opts) => {
    const method = (opts && opts.method) || 'GET';
    if (url.endsWith('/api/jobs/7') && method === 'GET') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(job) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

describe('JobDetailWorkspace', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders title, company, score, and a recommendation badge once loaded', async () => {
    mockFetchSequence(baseJob());
    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Platform Engineer')).toBeInTheDocument());
    expect(screen.getByText(/Globex/)).toBeInTheDocument();
    expect(screen.getByText('82')).toBeInTheDocument();
    // score 82 >= 80 -> "Strong Apply" recommendation badge
    expect(screen.getByText('Strong Apply')).toBeInTheDocument();
  });

  it('shows the "no contact found" empty state with a Find Contact action when contact is missing', async () => {
    mockFetchSequence(baseJob({ contact: null }));
    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Platform Engineer')).toBeInTheDocument());
    expect(screen.getByText(/No contact found yet/i)).toBeInTheDocument();
    expect(screen.getByText('Find contact with AI')).toBeInTheDocument();
  });

  it('renders the required AI action buttons', async () => {
    mockFetchSequence(baseJob());
    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('Platform Engineer')).toBeInTheDocument());

    const expectedLabels = [
      'Generate Cover Letter', 'Generate Recruiter Email', 'Generate Follow-up Email',
      'Generate LinkedIn Message', 'Find Contact', 'Save to Applications',
      'Mark Applied', 'Mark Interview', 'Mark Rejected', 'Skip Job',
    ];
    for (const label of expectedLabels) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('renders the generated draft content in an editable field', async () => {
    mockFetchSequence(baseJob({
      drafts: { linkedin_message: { subject: '', body: 'Hi, I would love to connect about the Platform Engineer role.' } },
    }));
    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('Platform Engineer')).toBeInTheDocument());

    expect(screen.getByDisplayValue(/love to connect about the Platform Engineer role/)).toBeInTheDocument();
  });

  it('updates displayed status after clicking a pipeline status button (Mark Applied)', async () => {
    const job = baseJob({ status: 'Shortlisted' });
    globalThis.fetch = vi.fn((url, opts) => {
      const method = (opts && opts.method) || 'GET';
      if (url.endsWith('/api/jobs/7') && method === 'GET') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(job) });
      }
      if (url.endsWith('/api/jobs/7/status') && method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...job, status: 'Applied', status_updated_at: '2026-01-02T00:00:00' }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('Platform Engineer')).toBeInTheDocument());

    const tracker = screen.getByText('Application Tracker').closest('.jdw-section');
    // Before: "Saved" chip active (status === Shortlisted)
    expect(within(tracker).getByText('Saved')).toHaveClass('active');

    fireEvent.click(screen.getAllByText('Mark Applied')[0]);

    await waitFor(() => {
      expect(within(tracker).getByText('Applied')).toHaveClass('active');
    });
  });
});

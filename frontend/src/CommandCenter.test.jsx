import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CommandCenter from './CommandCenter';

const job = {
  record_id: 5,
  title: 'Cloud Infrastructure Engineer',
  company: 'Initech',
  location: 'Remote',
  score: 91,
  tags: ['Remote'],
  reasons: ['Great Terraform overlap'],
  description: 'B'.repeat(200),
  url: 'https://example.com/job/5',
};

const dashboardPayload = {
  metrics: { new_jobs: 1, strong_matches: 1, jobs_skip: 0, apps_pending: 0, follow_ups: 0 },
  pipeline: { Discovered: 0, Matched: 1, Saved: 0, Applied: 0, Interview: 0, Offer: 0, Rejected: 0 },
  top_jobs: [job],
  action_queue: {
    needing_description: { count: 0, items: [] },
    ready_to_tailor: { count: 0, items: [] },
    cover_letters_waiting: { count: 0, items: [] },
    email_drafts_waiting: { count: 0, items: [] },
    tailored_not_applied: { count: 0, items: [] },
    follow_ups_due: { count: 0, items: [] },
  },
  skipped_jobs: [],
  job_source_health: {},
  last_scan: null,
  automation: { automation_enabled: false, daily_search_scheduled: false, telegram_connected: false },
  career_intel: { avg_score: 0, top_skills: [], best_source: null, source_pct: 0 },
};

const jobDetail = {
  ...job,
  status: 'Found', status_updated_at: null, created_at: '2026-01-01T00:00:00',
  source: 'command-center', user_notes: '', rejection_reason: null, file_path: null,
  cover_letter_generated: false, drafts: {}, contact: null, next_action: '',
};

describe('CommandCenter — job detail workspace integration', () => {
  it('opens the Job Detail Workspace when a job card is clicked', async () => {
    globalThis.fetch = vi.fn((url) => {
      if (url.endsWith('/api/command-center/dashboard')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(dashboardPayload) });
      }
      if (url.endsWith('/api/jobs/5')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(jobDetail) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<CommandCenter />);

    // Command Center's own dashboard loads first
    await waitFor(() => expect(screen.getByText('Cloud Infrastructure Engineer')).toBeInTheDocument());

    // Workspace should not be open yet
    expect(screen.queryByText('AI Match Explanation')).not.toBeInTheDocument();

    screen.getByText('Cloud Infrastructure Engineer').click();

    // Workspace fetches job detail and renders its sections
    await waitFor(() => expect(screen.getByText('AI Match Explanation')).toBeInTheDocument());
    expect(screen.getByText('Application Tracker')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import JobMatcher from './JobMatcher';

describe('JobMatcher — failed fetch / error states', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('surfaces the backend detail message when fetch-url returns a scraper failure (e.g. 404)', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: 'This job posting could not be found (404) — it may have expired.' }) })
    );

    render(<JobMatcher />);
    fireEvent.change(screen.getByPlaceholderText(/linkedin.com\/jobs/), { target: { value: 'https://example.com/jobs/expired' } });
    fireEvent.click(screen.getByText('Fetch JD'));

    await waitFor(() =>
      expect(screen.getByText('This job posting could not be found (404) — it may have expired.')).toBeInTheDocument()
    );
  });

  it('shows a friendly message when the backend is unreachable', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')));

    render(<JobMatcher />);
    fireEvent.change(screen.getByPlaceholderText(/linkedin.com\/jobs/), { target: { value: 'https://example.com/jobs/1' } });
    fireEvent.click(screen.getByText('Fetch JD'));

    await waitFor(() =>
      expect(screen.getByText(/Cannot reach the backend server/)).toBeInTheDocument()
    );
  });

  it('surfaces the backend detail message when analyze fails', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: 'Job description is too short to analyze.' }) })
    );

    render(<JobMatcher />);
    fireEvent.change(screen.getByPlaceholderText(/Paste the complete job description/), {
      target: { value: 'too short' },
    });
    fireEvent.click(screen.getByText('SCAN JD'));

    await waitFor(() => expect(screen.getByText('Job description is too short to analyze.')).toBeInTheDocument());
  });
});

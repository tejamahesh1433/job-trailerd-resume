import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CommandCenter from './CommandCenter';
import JobDetailWorkspace from './JobDetailWorkspace';

describe('CommandCenter — failed fetch / error states', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows an error banner when the dashboard fetch responds non-ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByText('Error: Failed to load dashboard')).toBeInTheDocument());
  });

  it('shows an error banner when the dashboard fetch rejects (network error)', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')));

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByText('Error: Failed to fetch')).toBeInTheDocument());
  });
});

describe('JobDetailWorkspace — failed fetch / error states', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows an error banner when the job fetch responds non-ok', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));

    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Failed to load job')).toBeInTheDocument());
    // No job content should render when the fetch failed
    expect(screen.queryByText('AI Match Explanation')).not.toBeInTheDocument();
  });

  it('shows an error banner when the job fetch rejects (network error)', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')));

    render(<JobDetailWorkspace jobId={7} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Failed to fetch')).toBeInTheDocument());
  });
});

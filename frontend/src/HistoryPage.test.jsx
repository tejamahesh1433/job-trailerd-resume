import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import HistoryPage from './HistoryPage';

afterEach(() => vi.unstubAllGlobals());

describe('History CSV import', () => {
  it('uploads the file, reports results, and refreshes history', async () => {
    const refresh = vi.fn();
    const fetch = vi.fn(async (_url, options) => ({
      ok: true,
      json: async () => options?.method === 'POST'
        ? { imported: 1, skipped: 2, failed: 1, errors: [{ row: 5, message: 'Company is required' }] }
        : [],
    }));
    vi.stubGlobal('fetch', fetch);
    render(<HistoryPage onRefreshHistory={refresh} />);
    fireEvent.click(screen.getByRole('button', { name: '↑ Import CSV' }));
    const file = new File(['Company\nAcme'], 'applications.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Import CSV', exact: true }));
    expect(await screen.findByText('1 imported · 2 duplicates skipped · 1 invalid rows')).toBeInTheDocument();
    expect(screen.getByText('Row 5: Company is required')).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledOnce();
    const upload = fetch.mock.calls.find(([, options]) => options?.method === 'POST');
    expect(upload[0]).toBe('http://localhost:8000/api/history/import');
    expect(upload[1].body.get('file')).toBe(file);
  });

  it('shows upload errors and allows retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => ({
      ok: !options,
      json: async () => options ? { detail: 'CSV must have a Company column' } : [],
    })));
    render(<HistoryPage />);
    fireEvent.click(screen.getByRole('button', { name: '↑ Import CSV' }));
    fireEvent.change(screen.getByLabelText('CSV file'), { target: { files: [new File(['Role'], 'bad.csv')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Import CSV', exact: true }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('CSV must have a Company column'));
    expect(screen.getByRole('button', { name: 'Import CSV', exact: true })).toBeEnabled();
  });
});

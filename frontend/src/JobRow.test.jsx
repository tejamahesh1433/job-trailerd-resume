import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobRow } from './CommandCenter';

const sampleJob = {
  record_id: 42,
  title: 'Senior DevOps Engineer',
  company: 'Acme Corp',
  location: 'Remote',
  score: 88,
  tags: ['Remote', 'Full-time'],
  reasons: ['Strong Kubernetes match'],
  description: 'Full JD text here',
  url: 'https://example.com/job/42',
};

describe('JobRow', () => {
  it('calls onOpenDetail when the card is clicked', () => {
    const onOpenDetail = vi.fn();
    render(<JobRow index={1} job={sampleJob} onOpenDetail={onOpenDetail} />);
    fireEvent.click(screen.getByText('Senior DevOps Engineer'));
    expect(onOpenDetail).toHaveBeenCalledWith(sampleJob);
  });

  it('Save to Applications (Save App) button calls onSaveToApplications with the job, not onOpenDetail', () => {
    const onSaveToApplications = vi.fn();
    const onOpenDetail = vi.fn();
    render(<JobRow index={1} job={sampleJob} onSaveToApplications={onSaveToApplications} onOpenDetail={onOpenDetail} />);
    fireEvent.click(screen.getByText('Save App'));
    expect(onSaveToApplications).toHaveBeenCalledWith(sampleJob);
    expect(onOpenDetail).not.toHaveBeenCalled();
  });

  it('Send to Resume Tailor (Tailor) button routes to onSendToTailor with the job description', () => {
    const onSendToTailor = vi.fn();
    const onOpenDetail = vi.fn();
    render(<JobRow index={1} job={sampleJob} onSendToTailor={onSendToTailor} onOpenDetail={onOpenDetail} />);
    fireEvent.click(screen.getByText('Tailor'));
    expect(onSendToTailor).toHaveBeenCalledWith(sampleJob.description);
    expect(onOpenDetail).not.toHaveBeenCalled();
  });
});

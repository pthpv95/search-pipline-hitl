import type { ReviewDecisionInput, RunDetailDto, RunSummaryDto } from './types';

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      // Ignore JSON parse failure and keep the fallback message.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function listRuns(): Promise<RunSummaryDto[]> {
  return request<RunSummaryDto[]>('/api/runs');
}

export function getRunDetail(runId: string): Promise<RunDetailDto> {
  return request<RunDetailDto>(`/api/runs/${runId}`);
}

export function createRun(input: {
  topic: string;
  mode: 'dev' | 'live' | 'eval';
  report_format: 'deep_dive' | 'executive_brief';
  max_loops: number;
}): Promise<{ run_id: string; stream_url: string; detail_url: string }> {
  return request('/api/runs', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function submitReview(runId: string, input: ReviewDecisionInput): Promise<{ accepted: boolean; summary: RunSummaryDto }> {
  return request(`/api/runs/${runId}/review`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

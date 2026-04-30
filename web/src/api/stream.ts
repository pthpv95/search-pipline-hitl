import type { SseEventDto } from './types';

const EVENT_TYPES: SseEventDto['type'][] = [
  'run.created',
  'run.phase_changed',
  'node.started',
  'node.completed',
  'review.required',
  'review.resolved',
  'run.completed',
  'run.failed',
  'heartbeat',
];

export function subscribeToRun(
  runId: string,
  onEvent: (event: SseEventDto) => void,
  onError?: (error: Event) => void,
): () => void {
  const source = new EventSource(`/api/runs/${runId}/events`);
  for (const eventType of EVENT_TYPES) {
    source.addEventListener(eventType, (message) => {
      const payload = JSON.parse((message as MessageEvent).data) as SseEventDto;
      onEvent(payload);
    });
  }
  source.onerror = (error) => {
    onError?.(error);
  };
  return () => source.close();
}

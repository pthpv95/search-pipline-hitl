import { Label } from './primitives';
import type { RunDetailDto } from '../api/types';

export function LogTab({ detail }: { detail: RunDetailDto | null }) {
  if (!detail) return null;

  return (
    <div
      style={{
        background: 'var(--term-bg)',
        border: '1px solid #221F19',
        borderRadius: 2,
        padding: '18px 20px',
      }}
    >
      <Label style={{ marginBottom: 12, color: 'var(--term-mute)' }}>Operational Log</Label>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 420, overflowY: 'auto' }}>
        {detail.log.entries.map((entry) => (
          <div key={entry.id} className="mono" style={{ fontSize: 11.5, color: toneColor(entry.level), lineHeight: 1.6 }}>
            <span style={{ color: 'var(--term-mute)' }}>{formatTime(entry.t)}</span>
            {'  '}
            <span>{(entry.node || 'system').padEnd(16, ' ')}</span>
            {'  '}
            <span>{entry.level.toUpperCase().padEnd(5, ' ')}</span>
            {'  '}
            <span style={{ color: 'var(--term-fg)' }}>{entry.msg}</span>
          </div>
        ))}
        {detail.log.entries.length === 0 && (
          <div className="mono" style={{ fontSize: 11.5, color: 'var(--term-mute)' }}>
            no log entries yet
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString();
}

function toneColor(level: string): string {
  if (level === 'err') return '#E98A7B';
  if (level === 'warn' || level === 'halt') return '#DDB26E';
  if (level === 'ok') return '#8CCB8D';
  return 'var(--term-fg)';
}

import { Pill } from './primitives';
import type { RunDetailDto, UiPhase } from '../api/types';

function phaseLabel(phase: UiPhase): string {
  if (phase === 'paused_interrupt') return 'HITL · AWAITING REVIEW';
  if (phase === 'writing_report') return 'WRITING REPORT';
  if (phase === 'done') return 'RUN COMPLETE';
  if (phase === 'rejected') return 'REJECTED';
  if (phase === 'failed') return 'FAILED';
  return phase.replace('_', ' ').toUpperCase();
}

function phaseTone(phase: UiPhase): 'red' | 'green' | 'ink' {
  if (phase === 'paused_interrupt' || phase === 'rejected' || phase === 'failed') return 'red';
  if (phase === 'done') return 'green';
  return 'ink';
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function TopBar({
  detail,
  onRefresh,
  onNewRun,
}: {
  detail: RunDetailDto | null;
  onRefresh: () => void;
  onNewRun: () => void;
}) {
  return (
    <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 24 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
          <div
            className="mono"
            style={{
              fontSize: 10,
              letterSpacing: '0.24em',
              color: 'var(--ink-3)',
              border: '1px solid var(--hair-2)',
              padding: '3px 8px',
              borderRadius: 2,
            }}
          >
            RESEARCH CONSOLE · v1.0
          </div>
          <Pill tone={detail ? phaseTone(detail.summary.phase) : 'ink'}>{detail ? phaseLabel(detail.summary.phase) : 'NO RUN SELECTED'}</Pill>
        </div>
        <h1 className="serif" style={{ fontSize: 46, margin: 0, lineHeight: 1.05, letterSpacing: '-0.015em' }}>
          {detail?.summary.topic || 'Research Console'}
        </h1>
        <div style={{ display: 'flex', gap: 18, marginTop: 10, fontSize: 12, color: 'var(--ink-3)', flexWrap: 'wrap' }}>
          <span className="mono">mode: <span style={{ color: 'var(--ink-2)' }}>{detail?.summary.mode || '—'}</span></span>
          <span className="mono">format: <span style={{ color: 'var(--ink-2)' }}>{detail?.summary.report_format || '—'}</span></span>
          <span className="mono">max_loops: <span style={{ color: 'var(--ink-2)' }}>{detail?.summary.max_loops ?? '—'}</span></span>
          <span className="mono">model: <span style={{ color: 'var(--ink-2)' }}>{detail?.evaluation.model_name || '—'}</span></span>
          <span className="mono">run_id: <span style={{ color: 'var(--ink-2)' }}>{detail?.summary.id || '—'}</span></span>
          <span className="mono">updated: <span style={{ color: 'var(--ink-2)' }}>{fmtDate(detail?.summary.updated_at)}</span></span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        <button
          onClick={onRefresh}
          className="mono"
          style={{
            padding: '8px 14px',
            fontSize: 11,
            letterSpacing: '0.08em',
            border: '1px solid var(--hair-2)',
            borderRadius: 2,
            color: 'var(--ink-2)',
          }}
        >
          ↻ REFRESH
        </button>
        <button
          onClick={onNewRun}
          className="mono"
          style={{
            padding: '8px 14px',
            fontSize: 11,
            letterSpacing: '0.08em',
            background: 'var(--ink)',
            color: 'var(--paper)',
            borderRadius: 2,
          }}
        >
          + NEW TOPIC
        </button>
      </div>
    </header>
  );
}

import { Label, Pill, Rule, ScoreDial } from './primitives';
import type { RunSummaryDto } from '../api/types';

function fmtDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function Sidebar({
  runs,
  activeRunId,
  onPickRun,
}: {
  runs: RunSummaryDto[];
  activeRunId: string | null;
  onPickRun: (run: RunSummaryDto) => void;
}) {
  const totalTokens = runs.reduce((sum, run) => sum + run.token_total, 0);
  const totalCost = runs.reduce((sum, run) => sum + run.cost_usd, 0);

  return (
    <aside
      style={{
        background: 'var(--card)',
        border: '1px solid var(--hair)',
        borderRadius: 2,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--hair)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Label>Runs</Label>
        <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)' }}>
          {runs.length}
        </span>
      </div>

      <div style={{ maxHeight: 420, overflowY: 'auto' }}>
        {runs.map((run) => {
          const active = activeRunId === run.id;
          return (
            <button
              key={run.id}
              onClick={() => onPickRun(run)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '12px 16px',
                background: active ? '#FBF5EE' : 'transparent',
                borderBottom: '1px solid var(--hair)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4, gap: 8 }}>
                <span className="mono" style={{ fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em' }}>
                  {fmtDate(run.updated_at)}
                </span>
                <StatusBadge run={run} />
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: active ? 'var(--ink)' : 'var(--ink-2)',
                  lineHeight: 1.4,
                  fontWeight: active ? 500 : 400,
                }}
              >
                {run.topic}
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                {run.overall_score != null ? <ScoreDial value={run.overall_score} /> : <Pill tone="ink">PENDING</Pill>}
                <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)' }}>
                  {(run.token_total / 1000).toFixed(1)}k · ${run.cost_usd.toFixed(3)}
                </span>
                {run.is_active_session && !['done', 'rejected', 'failed'].includes(run.phase) && (
                  <span className="mono" style={{ fontSize: 10, color: 'var(--red)', letterSpacing: '0.08em' }}>
                    LIVE
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div style={{ padding: '14px 16px', borderTop: '1px solid var(--hair)', background: 'var(--paper-2)' }}>
        <Label style={{ marginBottom: 10 }}>History Totals</Label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ flex: 1, fontSize: 11.5, color: 'var(--ink-2)' }}>runs loaded</span>
            <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>
              {runs.length}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ flex: 1, fontSize: 11.5, color: 'var(--ink-2)' }}>tokens</span>
            <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>
              {totalTokens.toLocaleString()}
            </span>
          </div>
          <Rule dashed style={{ margin: '4px 0' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ flex: 1, fontSize: 11.5, fontWeight: 600 }}>estimated cost</span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--red)' }}>
              ${totalCost.toFixed(4)}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function StatusBadge({ run }: { run: RunSummaryDto }) {
  const map: Record<RunSummaryDto['phase'], { tone: 'ink' | 'red' | 'green'; label: string }> = {
    initializing: { tone: 'ink', label: 'INIT' },
    searching: { tone: 'ink', label: 'SEARCH' },
    synthesizing: { tone: 'ink', label: 'SYNTH' },
    paused_interrupt: { tone: 'red', label: 'REVIEW' },
    resuming: { tone: 'ink', label: 'RESUME' },
    writing_report: { tone: 'ink', label: 'REPORT' },
    done: { tone: 'green', label: 'DONE' },
    rejected: { tone: 'red', label: 'REJECT' },
    failed: { tone: 'red', label: 'FAIL' },
  };
  const badge = map[run.phase];
  return (
    <Pill tone={badge.tone} style={{ fontSize: 9.5, padding: '1px 6px' }}>
      {badge.label}
    </Pill>
  );
}

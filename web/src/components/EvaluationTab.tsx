import type { CSSProperties } from 'react';
import { Label, Rule, ScoreDial } from './primitives';
import type { RunDetailDto } from '../api/types';

const SCORE_LABELS: Record<string, string> = {
  citation_integrity: 'Citation integrity',
  source_validity: 'Source validity',
  topical_coverage: 'Topical coverage',
  unsupported_claim_rate: 'Supported claims',
  loop_discipline: 'Loop discipline',
};

export function EvaluationTab({ detail }: { detail: RunDetailDto | null }) {
  if (!detail) return null;

  const evaluation = detail.evaluation;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: 22, alignItems: 'flex-start' }}>
      <section style={panelStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <Label>Evaluation</Label>
          {evaluation.overall != null ? <ScoreDial value={evaluation.overall} /> : null}
        </div>
        {evaluation.ready ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
            {Object.entries(evaluation.scores).map(([key, value]) => (
              <div key={key} style={{ border: '1px solid var(--hair)', padding: '12px 14px', background: 'var(--paper)' }}>
                <Label style={{ marginBottom: 8 }}>{SCORE_LABELS[key] || key}</Label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <ScoreDial value={value} />
                  <span className="mono" style={{ fontSize: 12 }}>{(value * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 13.5, color: 'var(--ink-3)' }}>
            Final evaluation will appear once the run is completed and persisted.
          </div>
        )}

        <Rule style={{ margin: '18px 0' }} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {evaluation.notes.map((note) => (
            <div key={note} style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{note}</div>
          ))}
        </div>
      </section>

      <section style={panelStyle}>
        <Label style={{ marginBottom: 12 }}>Metrics</Label>
        <MetricRow label="Mode" value={evaluation.mode} />
        <MetricRow label="Model" value={evaluation.model_name} />
        <MetricRow label="Search" value={evaluation.search_provider} />
        <MetricRow label="Input tokens" value={evaluation.token_usage.total_input?.toLocaleString?.() ?? String(evaluation.token_usage.total_input ?? 0)} />
        <MetricRow label="Output tokens" value={evaluation.token_usage.total_output?.toLocaleString?.() ?? String(evaluation.token_usage.total_output ?? 0)} />
        <MetricRow label="Total cost" value={`$${(evaluation.costs.total || 0).toFixed(4)}`} />

        <Rule style={{ margin: '16px 0' }} />

        {['search_agent', 'synthesis_agent', 'report_agent'].map((node) => (
          <div key={node} style={{ padding: '10px 0', borderBottom: '1px solid var(--hair)' }}>
            <Label style={{ marginBottom: 6 }}>{node}</Label>
            <MetricRow label="Tokens" value={(evaluation.token_usage[node] || 0).toLocaleString()} />
            <MetricRow label="Seconds" value={`${(evaluation.node_timings[node] || 0).toFixed(2)}s`} />
            <MetricRow label="Cost" value={`$${(evaluation.costs[node] || 0).toFixed(4)}`} />
          </div>
        ))}

        <Rule style={{ margin: '16px 0' }} />

        <Label style={{ marginBottom: 8 }}>Errors</Label>
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
          {evaluation.errors.length ? evaluation.errors.join(' · ') : 'No errors recorded.'}
        </div>
      </section>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12.5, padding: '4px 0' }}>
      <span style={{ color: 'var(--ink-3)' }}>{label}</span>
      <span className="mono" style={{ color: 'var(--ink)' }}>{value}</span>
    </div>
  );
}

const panelStyle: CSSProperties = {
  background: 'var(--card)',
  border: '1px solid var(--hair)',
  borderRadius: 2,
  padding: '20px 22px',
};

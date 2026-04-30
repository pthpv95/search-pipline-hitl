import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { Corner, Dot, Label, Pill } from './primitives';
import type { ReviewDecisionInput, RunDetailDto } from '../api/types';

type Mode = 'idle' | 'approve' | 'queries' | 'edit' | 'reject';
type Tone = 'green' | 'blue' | 'amber' | 'red';

export function ReviewPanel({
  detail,
  submitting,
  onDecision,
}: {
  detail: RunDetailDto | null;
  submitting: boolean;
  onDecision: (decision: ReviewDecisionInput) => Promise<void>;
}) {
  const payload = detail?.review.payload ?? null;
  const isPaused = detail?.review.is_pending ?? false;
  const [mode, setMode] = useState<Mode>('idle');
  const [queries, setQueries] = useState<string[]>(payload?.unresolved_gaps.slice(0, 2) ?? []);
  const [newQuery, setNewQuery] = useState('');
  const [reason, setReason] = useState('');
  const [editDraft, setEditDraft] = useState(payload?.draft ?? detail?.draft.text ?? '');

  useEffect(() => {
    setMode('idle');
    setQueries(payload?.unresolved_gaps.slice(0, 2) ?? []);
    setReason('');
    setEditDraft(payload?.draft ?? detail?.draft.text ?? '');
  }, [detail?.summary.id, payload?.draft]);

  async function submit() {
    if (!detail) return;
    if (mode === 'approve') await onDecision({ action: 'approve' });
    if (mode === 'queries') await onDecision({ action: 'approve', additional_queries: queries });
    if (mode === 'edit') await onDecision({ action: 'edit', edited_draft: editDraft });
    if (mode === 'reject') await onDecision({ action: 'reject', rejection_reason: reason });
    setMode('idle');
  }

  return (
    <div
      style={{
        background: isPaused ? '#FBF5EE' : 'var(--card)',
        border: `1px solid ${isPaused ? 'var(--red)' : 'var(--hair)'}`,
        borderRadius: 2,
        position: 'relative',
        transition: 'border-color 300ms ease, background 300ms ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          background: isPaused ? 'repeating-linear-gradient(-45deg, #F6E3DE 0 10px, #F1E2DD 10px 20px)' : 'transparent',
          borderBottom: `1px solid ${isPaused ? '#B43A2A30' : 'var(--hair)'}`,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Corner style={{ color: isPaused ? 'var(--red)' : 'var(--ink-3)' }} />
          <div>
            <div className="serif" style={{ fontSize: 22, lineHeight: 1, color: isPaused ? 'var(--red)' : 'var(--ink)' }}>
              Human review
            </div>
            <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 4, letterSpacing: '0.08em' }}>
              agents/human_review.py · interrupt() · reviewer-controlled
            </div>
          </div>
        </div>
        {isPaused ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Pill tone="red">
              <Dot color="var(--red)" size={5} /> PAUSED
            </Pill>
          </div>
        ) : (
          <Pill tone={detail?.review.last_decision?.rejected ? 'red' : 'green'}>
            {detail?.review.last_decision ? 'RESOLVED' : 'IDLE'}
          </Pill>
        )}
      </div>

      <div style={{ padding: '18px 20px 22px' }}>
        <div style={{ fontSize: 13.5, color: 'var(--ink-2)', maxWidth: 700, lineHeight: 1.55 }}>
          {payload
            ? (
              <>
                Synthesis produced a draft at confidence <strong>{Math.round(payload.confidence * 100)}%</strong> with{' '}
                <strong>{payload.sources.length}</strong> sources and <strong>{payload.unresolved_gaps.length}</strong> unresolved gaps.
              </>
            )
            : 'Review controls unlock when a live run pauses at human_review. Completed runs remain visible here for inspection.'}
        </div>

        {payload && (
          <div style={{ display: 'flex', gap: 18, marginTop: 14, flexWrap: 'wrap' }}>
            <MetaStat label="Loop" value={`${payload.loop_count}/${payload.max_loops}`} />
            <MetaStat label="Findings" value={String(payload.findings.length)} />
            <MetaStat label="Sources" value={String(payload.sources.length)} />
            <MetaStat label="Limitations" value={String(payload.limitations.length)} />
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginTop: 18 }}>
          <DecisionCard selected={mode === 'approve'} onClick={() => isPaused && setMode('approve')} disabled={!isPaused || submitting} keyLabel="A" title="Approve" desc="Proceed to report_agent with the draft as-is." tone="green" />
          <DecisionCard selected={mode === 'queries'} onClick={() => isPaused && setMode('queries')} disabled={!isPaused || submitting} keyLabel="Q" title="Approve + queries" desc="Loop back to search_agent with reviewer queries." tone="blue" />
          <DecisionCard selected={mode === 'edit'} onClick={() => isPaused && setMode('edit')} disabled={!isPaused || submitting} keyLabel="E" title="Edit draft" desc="Modify directly. Edits persist across later loops." tone="amber" />
          <DecisionCard selected={mode === 'reject'} onClick={() => isPaused && setMode('reject')} disabled={!isPaused || submitting} keyLabel="R" title="Reject" desc="Terminate the run with a reviewer rejection." tone="red" />
        </div>

        <div style={{ marginTop: 18 }}>
          {mode === 'idle' && (
            <div className="mono" style={{ fontSize: 11, color: 'var(--ink-4)', letterSpacing: '0.08em' }}>
              {isPaused ? '// choose a review action to resume the pipeline' : '// no pending human review'}
            </div>
          )}

          {mode === 'approve' && (
            <ConfirmBar
              label="Approve and continue to report_agent"
              cta={submitting ? 'Submitting…' : 'Resume pipeline'}
              tone="green"
              onSubmit={submit}
              onCancel={() => setMode('idle')}
              disabled={submitting}
            />
          )}

          {mode === 'queries' && (
            <div>
              <Label style={{ marginBottom: 8 }}>Reviewer queries — fed into search_agent</Label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {queries.map((query, index) => (
                  <div
                    key={`${query}-${index}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '8px 12px',
                      background: '#fff',
                      border: '1px solid var(--hair-2)',
                      borderRadius: 2,
                    }}
                  >
                    <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)' }}>
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span style={{ flex: 1, fontSize: 13 }}>{query}</span>
                    <button onClick={() => setQueries(queries.filter((_, queryIndex) => queryIndex !== index))} className="mono" style={{ fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.08em' }}>
                      REMOVE
                    </button>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <input
                  value={newQuery}
                  onChange={(event) => setNewQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && newQuery.trim()) {
                      setQueries([...queries, newQuery.trim()]);
                      setNewQuery('');
                    }
                  }}
                  placeholder="add query and press ⏎"
                  style={inputStyle}
                />
                <ConfirmBar
                  inline
                  cta={submitting ? 'Submitting…' : `Loop with ${queries.length} ${queries.length === 1 ? 'query' : 'queries'}`}
                  tone="blue"
                  onSubmit={submit}
                  onCancel={() => setMode('idle')}
                  disabled={queries.length === 0 || submitting}
                />
              </div>
              {payload && payload.unresolved_gaps.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <Label style={{ marginBottom: 6 }}>Suggested gaps (click to add)</Label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {payload.unresolved_gaps.map((gap) => {
                      const already = queries.includes(gap);
                      return (
                        <button
                          key={gap}
                          onClick={() => !already && setQueries([...queries, gap])}
                          className="mono"
                          style={{
                            padding: '4px 8px',
                            fontSize: 11,
                            border: '1px solid var(--hair-2)',
                            borderRadius: 2,
                            background: 'transparent',
                            color: 'var(--ink-3)',
                            opacity: already ? 0.35 : 1,
                          }}
                        >
                          + {gap}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {mode === 'edit' && (
            <div>
              <Label style={{ marginBottom: 8 }}>Inline edit — changes persist across loops</Label>
              <textarea value={editDraft} onChange={(event) => setEditDraft(event.target.value)} style={{ ...inputStyle, minHeight: 220, resize: 'vertical', fontFamily: 'Instrument Serif, serif', lineHeight: 1.6 }} />
              <ConfirmBar
                label="Save edit and resume with report_agent"
                cta={submitting ? 'Submitting…' : 'Save & resume'}
                tone="amber"
                onSubmit={submit}
                onCancel={() => setMode('idle')}
                disabled={!editDraft.trim() || submitting}
              />
            </div>
          )}

          {mode === 'reject' && (
            <div>
              <Label style={{ marginBottom: 8 }}>Reason (optional) — recorded in the run artifact</Label>
              <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="e.g. off-topic — wrong framing of the question" style={inputStyle} />
              <ConfirmBar
                label="Terminate the pipeline — no final report will be generated"
                cta={submitting ? 'Submitting…' : 'Reject & end run'}
                tone="red"
                onSubmit={submit}
                onCancel={() => setMode('idle')}
                disabled={submitting}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetaStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Label style={{ marginBottom: 4 }}>{label}</Label>
      <div className="mono" style={{ fontSize: 12, color: 'var(--ink-2)' }}>{value}</div>
    </div>
  );
}

function DecisionCard({
  selected,
  onClick,
  title,
  desc,
  tone,
  keyLabel,
  disabled,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  desc: string;
  tone: Tone;
  keyLabel: string;
  disabled: boolean;
}) {
  const palette: Record<Tone, { fg: string; bd: string }> = {
    green: { fg: 'var(--green)', bd: '#3E6B4A' },
    blue: { fg: 'var(--blue)', bd: '#3A5E86' },
    amber: { fg: 'var(--amber)', bd: '#B88326' },
    red: { fg: 'var(--red)', bd: 'var(--red)' },
  };
  const color = palette[tone];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        border: `1px solid ${selected ? color.bd : 'var(--hair-2)'}`,
        borderRadius: 2,
        padding: '12px 14px',
        textAlign: 'left',
        background: selected ? `${color.fg}10` : 'transparent',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      <div className="mono" style={{ fontSize: 10.5, color: color.fg, letterSpacing: '0.08em' }}>
        [{keyLabel}]
      </div>
      <div className="serif" style={{ fontSize: 24, marginTop: 8 }}>
        {title}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5, marginTop: 6 }}>
        {desc}
      </div>
    </button>
  );
}

function ConfirmBar({
  label,
  cta,
  tone,
  onSubmit,
  onCancel,
  inline,
  disabled,
}: {
  label?: string;
  cta: string;
  tone: Tone;
  onSubmit: () => void;
  onCancel: () => void;
  inline?: boolean;
  disabled?: boolean;
}) {
  const palette: Record<Tone, string> = {
    green: 'var(--green)',
    blue: 'var(--blue)',
    amber: 'var(--amber)',
    red: 'var(--red)',
  };
  return (
    <div style={{ display: 'flex', gap: 8, marginTop: inline ? 0 : 10, alignItems: 'center', flexWrap: 'wrap' }}>
      {label && <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginRight: 'auto' }}>{label}</div>}
      <button onClick={onCancel} className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)', letterSpacing: '0.08em' }}>
        CANCEL
      </button>
      <button
        onClick={onSubmit}
        disabled={disabled}
        className="mono"
        style={{
          background: palette[tone],
          color: 'var(--paper)',
          padding: '8px 12px',
          borderRadius: 2,
          fontSize: 10.5,
          letterSpacing: '0.08em',
          opacity: disabled ? 0.5 : 1,
        }}
      >
        {cta}
      </button>
    </div>
  );
}

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid var(--hair-2)',
  borderRadius: 2,
  background: '#fff',
  fontSize: 13,
  outline: 'none',
  color: 'var(--ink)',
};

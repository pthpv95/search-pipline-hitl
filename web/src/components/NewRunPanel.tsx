import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { Label } from './primitives';

export function NewRunPanel({
  open,
  creating,
  onClose,
  onCreate,
}: {
  open: boolean;
  creating: boolean;
  onClose: () => void;
  onCreate: (input: {
    topic: string;
    mode: 'dev' | 'live' | 'eval';
    report_format: 'deep_dive' | 'executive_brief';
    max_loops: number;
  }) => Promise<void>;
}) {
  const [topic, setTopic] = useState('');
  const [mode, setMode] = useState<'dev' | 'live' | 'eval'>('dev');
  const [reportFormat, setReportFormat] = useState<'deep_dive' | 'executive_brief'>('deep_dive');
  const [maxLoops, setMaxLoops] = useState(2);

  useEffect(() => {
    if (!open) return;
    setTopic('');
    setMode('dev');
    setReportFormat('deep_dive');
    setMaxLoops(2);
  }, [open]);

  if (!open) return null;

  return (
    <div style={overlayStyle}>
      <div style={panelStyle}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 16 }}>
          <div>
            <Label style={{ marginBottom: 8 }}>Start New Run</Label>
            <div className="serif" style={{ fontSize: 32, lineHeight: 1 }}>Launch a topic into the pipeline</div>
          </div>
          <button onClick={onClose} className="mono" style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--ink-4)' }}>
            CLOSE
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <Label style={{ marginBottom: 6 }}>Topic</Label>
            <textarea
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. Compare LangGraph, CrewAI, and AutoGen for production multi-agent orchestration"
              style={{ ...fieldStyle, minHeight: 110, resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <SelectField
              label="Mode"
              value={mode}
              onChange={(value) => setMode(value as 'dev' | 'live' | 'eval')}
              options={[
                { value: 'dev', label: 'dev' },
                { value: 'live', label: 'live' },
                { value: 'eval', label: 'eval' },
              ]}
            />
            <SelectField
              label="Report format"
              value={reportFormat}
              onChange={(value) => setReportFormat(value as 'deep_dive' | 'executive_brief')}
              options={[
                { value: 'deep_dive', label: 'deep_dive' },
                { value: 'executive_brief', label: 'executive_brief' },
              ]}
            />
            <SelectField
              label="Max loops"
              value={String(maxLoops)}
              onChange={(value) => setMaxLoops(Number(value))}
              options={[
                { value: '1', label: '1' },
                { value: '2', label: '2' },
                { value: '3', label: '3' },
              ]}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <button onClick={onClose} className="mono" style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--ink-4)' }}>
            CANCEL
          </button>
          <button
            onClick={() => onCreate({ topic, mode, report_format: reportFormat, max_loops: maxLoops })}
            disabled={!topic.trim() || creating}
            className="mono"
            style={{
              background: 'var(--ink)',
              color: 'var(--paper)',
              padding: '10px 14px',
              borderRadius: 2,
              fontSize: 11,
              letterSpacing: '0.08em',
              opacity: !topic.trim() || creating ? 0.5 : 1,
            }}
          >
            {creating ? 'STARTING…' : 'START RUN'}
          </button>
        </div>
      </div>
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div>
      <Label style={{ marginBottom: 6 }}>{label}</Label>
      <select value={value} onChange={(event) => onChange(event.target.value)} style={fieldStyle}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(24, 23, 15, 0.36)',
  display: 'flex',
  justifyContent: 'flex-end',
  zIndex: 10,
};

const panelStyle: CSSProperties = {
  width: 'min(520px, 100%)',
  height: '100%',
  background: 'var(--card)',
  borderLeft: '1px solid var(--hair)',
  padding: '28px 24px',
  boxShadow: '-12px 0 40px rgba(24, 23, 15, 0.16)',
};

const fieldStyle: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid var(--hair-2)',
  borderRadius: 2,
  background: '#fff',
  color: 'var(--ink)',
  fontSize: 13,
};

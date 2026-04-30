import { type CSSProperties, type ReactNode, useRef, useState } from 'react';
import { Label, Pill } from './primitives';
import type { RunDetailDto } from '../api/types';

const citationRx = /\[(\d+)\]/g;

function renderDraft(text: string, onCite: (index: number) => void): ReactNode[] {
  const elements: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = citationRx.exec(text)) !== null) {
    if (match.index > last) {
      elements.push(text.slice(last, match.index));
    }
    const num = parseInt(match[1], 10);
    elements.push(
      <span
        key={match.index}
        onClick={() => onCite(num - 1)}
        className="mono"
        style={citationStyle}
        title={`Jump to source ${num}`}
      >
        [{num}]
      </span>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    elements.push(text.slice(last));
  }

  return elements;
}

export function DraftSourcesTab({ detail }: { detail: RunDetailDto | null }) {
  if (!detail) return null;

  const draft = detail.draft;
  const [activeSourceIndex, setActiveSourceIndex] = useState<number | null>(null);
  const sourceRefs = useRef<(HTMLElement | null)[]>([]);

  function handleCitationClick(index: number) {
    if (index < 0 || index >= draft.sources.length) return;
    setActiveSourceIndex(index);
    const el = sourceRefs.current[index];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    setTimeout(() => setActiveSourceIndex(null), 2000);
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 22, alignItems: 'flex-start' }}>
      <section style={panelStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <div>
            <Label style={{ marginBottom: 6 }}>Draft / Report</Label>
            <div className="serif" style={{ fontSize: 28, lineHeight: 1.05 }}>{draft.title}</div>
          </div>
          <Pill tone="ink">{draft.source_kind.replace('_', ' ')}</Pill>
        </div>
        {draft.executive_summary && (
          <div style={{ marginBottom: 16, padding: '12px 14px', background: 'var(--paper)', border: '1px solid var(--hair)' }}>
            <Label style={{ marginBottom: 6 }}>Executive Summary</Label>
            <div style={{ fontSize: 14, lineHeight: 1.6 }}>{draft.executive_summary}</div>
          </div>
        )}
        <div
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: 14,
            lineHeight: 1.75,
            color: 'var(--ink-2)',
            minHeight: 260,
          }}
        >
          {draft.text ? renderDraft(draft.text, handleCitationClick) : 'No draft available yet.'}
        </div>
      </section>

      <section style={panelStyle}>
        <Label style={{ marginBottom: 12 }}>Sources & Limits</Label>
        {draft.limitations.length > 0 && (
          <div style={{ marginBottom: 18 }}>
            <Label style={{ marginBottom: 8 }}>Recorded Limitations</Label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {draft.limitations.map((item) => (
                <div key={item} style={{ padding: '10px 12px', border: '1px solid var(--hair)', background: 'var(--paper)' }}>
                  {item}
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {draft.sources.map((source, index) => (
            <a
              key={source.id}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              ref={(el) => { sourceRefs.current[index] = el; }}
              id={`src-${index}`}
              style={{
                display: 'block',
                textDecoration: 'none',
                color: 'inherit',
                border: activeSourceIndex === index ? '1px solid var(--blue)' : '1px solid var(--hair)',
                padding: '12px 14px',
                background: activeSourceIndex === index ? 'var(--card)' : '#fff',
                transition: 'border 0.15s, background 0.15s',
              }}
            >
              <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)', marginBottom: 6 }}>
                [{index + 1}] {source.domain}
              </div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{source.title}</div>
              <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.5 }}>{source.snippet}</div>
            </a>
          ))}
          {draft.sources.length === 0 && (
            <div style={{ fontSize: 12.5, color: 'var(--ink-4)' }}>No sources available yet.</div>
          )}
        </div>
      </section>
    </div>
  );
}

const panelStyle: CSSProperties = {
  background: 'var(--card)',
  border: '1px solid var(--hair)',
  borderRadius: 2,
  padding: '20px 22px',
};

const citationStyle: CSSProperties = {
  cursor: 'pointer',
  color: 'var(--blue)',
  fontWeight: 600,
};

import type { CSSProperties, ReactNode } from 'react';

type Tone = 'ink' | 'red' | 'green' | 'amber' | 'blue';

export function Dot({ color = 'var(--ink-3)', size = 6, style }: { color?: string; size?: number; style?: CSSProperties }) {
  return <span style={{ display: 'inline-block', width: size, height: size, borderRadius: 999, background: color, ...style }} />;
}

const PILL_PALETTE: Record<Tone, { bg: string; fg: string; bd: string }> = {
  ink: { bg: '#18171008', fg: 'var(--ink-2)', bd: 'var(--hair-2)' },
  red: { bg: 'var(--red-soft)', fg: 'var(--red)', bd: '#B43A2A30' },
  green: { bg: '#3E6B4A15', fg: 'var(--green)', bd: '#3E6B4A30' },
  amber: { bg: '#B8832615', fg: 'var(--amber)', bd: '#B8832640' },
  blue: { bg: '#3A5E8615', fg: 'var(--blue)', bd: '#3A5E8640' },
};

export function Pill({ children, tone = 'ink', style }: { children: ReactNode; tone?: Tone; style?: CSSProperties }) {
  const p = PILL_PALETTE[tone];
  return (
    <span
      className="mono"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 8px',
        borderRadius: 2,
        fontSize: 10.5,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        fontWeight: 500,
        background: p.bg,
        color: p.fg,
        border: `1px solid ${p.bd}`,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: 10.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--ink-4)',
        fontWeight: 500,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Corner({ size = 10, style }: { size?: number; style?: CSSProperties }) {
  return (
    <svg width={size} height={size} style={style} viewBox={`0 0 ${size} ${size}`}>
      <path d={`M0 ${size / 2} H${size} M${size / 2} 0 V${size}`} stroke="currentColor" strokeWidth="1" />
      <circle cx={size / 2} cy={size / 2} r={size / 3.2} fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

export function Rule({ style, dashed }: { style?: CSSProperties; dashed?: boolean }) {
  return (
    <div
      style={{
        height: 1,
        background: dashed ? 'transparent' : 'var(--hair)',
        backgroundImage: dashed ? 'repeating-linear-gradient(90deg, var(--hair-2) 0 4px, transparent 4px 8px)' : 'none',
        ...style,
      }}
    />
  );
}

export function ScoreDial({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const r = 7;
  const c = 2 * Math.PI * r;
  const color = value >= 0.9 ? 'var(--green)' : value >= 0.8 ? 'var(--amber)' : 'var(--red)';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <svg width="18" height="18">
        <circle cx="9" cy="9" r={r} fill="none" stroke="var(--hair-2)" strokeWidth="1.5" />
        <circle
          cx="9"
          cy="9"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeDasharray={`${c * value} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 9 9)"
        />
      </svg>
      <span className="mono" style={{ fontSize: 10.5, color, fontWeight: 500 }}>
        {pct}
      </span>
    </span>
  );
}

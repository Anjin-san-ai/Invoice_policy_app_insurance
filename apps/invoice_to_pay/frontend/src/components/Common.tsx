import { AlertTriangle, CheckCircle2, CircleDot } from 'lucide-react';
import { ReactNode } from 'react';

/** Status chip. Carries an icon as well as colour so meaning never depends on colour alone. */
export function StatusChip({ status }: { status: string }) {
  const icon = status === 'Paid' || status === 'Approved' ? <CheckCircle2 size={12} /> : status === 'Queried' ? <AlertTriangle size={12} /> : <CircleDot size={12} />;
  return (
    <span className={`chip ${status.replace(/\s+/g, '')}`}>
      {icon}
      {status}
    </span>
  );
}

/** Tolerance outcome chip, also icon-plus-label for colour-blind safety (spec 17.3). */
export function ToleranceChip({ outcome }: { outcome: string }) {
  return (
    <span className={`chip ${outcome}`}>
      {outcome === 'outside' ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
      {outcome}
    </span>
  );
}

/** Confidence meter: visual bar plus the numeric value, never a bare number (spec 13.4). */
export function ConfidenceMeter({ value, threshold = 0.82 }: { value: number; threshold?: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="confidence" title={`${pct}% confidence`}>
      <span className="track">
        <span className={`fill${value < threshold ? ' low' : ''}`} style={{ width: `${pct}%` }} />
      </span>
      <em>{pct}%</em>
    </span>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="grid" style={{ gap: 10 }}>
      {Array.from({ length: rows }).map((_, index) => (
        <div className="skeleton" key={index} />
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function KeyValues({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <dl className="kvList">
      {items.map(([key, value]) => (
        <div key={key} style={{ display: 'contents' }}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

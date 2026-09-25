import { AlertTriangle, ArrowUpRight, CheckCircle2, CircleDot } from 'lucide-react';
import { MouseEvent, ReactNode } from 'react';

/**
 * A card that drills into a screen when clicked.
 *
 * The card is a div rather than a button because its content often contains its own interactive
 * elements — charts with clickable segments, links, toggles. Those would be invalid nested inside
 * a button and would also fire the card's own handler, so anything interactive is wrapped in
 * `DrillCardBody`, which stops the click propagating.
 */
export function DrillCard({
  title,
  note,
  drillLabel,
  onDrill,
  children,
  className = '',
}: {
  title: string;
  note?: string;
  drillLabel: string;
  onDrill: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <article
      className={`card drillCard ${className}`.trim()}
      onClick={onDrill}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onDrill();
        }
      }}
      role="link"
      tabIndex={0}
    >
      <div className="drillCardHead">
        <h2>{title}</h2>
        <span className="drillCardGo">
          {drillLabel} <ArrowUpRight size={13} />
        </span>
      </div>
      {note ? <p className="cardNote">{note}</p> : null}
      {children}
    </article>
  );
}

/** Wrap interactive content inside a DrillCard so its clicks do not trigger the card's drill. */
export function DrillCardBody({ children }: { children: ReactNode }) {
  return (
    <div
      onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      {children}
    </div>
  );
}

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

/** A stat chip that drills somewhere. Same look as StatChip, but it is a real control. */
export function DrillChip({
  label,
  value,
  tone,
  onDrill,
}: {
  label: string;
  value: ReactNode;
  tone?: 'ok' | 'warn' | 'bad';
  onDrill: () => void;
}) {
  return (
    <button className={`statChip drillChip${tone ? ` ${tone}` : ''}`} onClick={onDrill} type="button">
      <span>{label}</span>
      <b>{value}</b>
    </button>
  );
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

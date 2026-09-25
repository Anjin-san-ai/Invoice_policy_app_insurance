import { motion, useMotionValue, useTransform, animate } from 'framer-motion';
import { ReactNode, useEffect, useMemo, useState } from 'react';
import { useChartTokens } from '../theme/useTheme';
import { gbp } from '../types';

/* Series hues come from the active theme via useChartTokens, so they follow light/dark. */

/* ------------------------------------------------------------------ radial gauge */

/** Animated arc gauge. Used for rates where a target matters more than the raw number. */
export function RadialGauge({
  value,
  max = 1,
  target,
  label,
  caption,
  size = 168,
  format,
}: {
  value: number;
  max?: number;
  target?: number;
  label: string;
  caption?: string;
  size?: number;
  format?: (value: number) => string;
}) {
  const stroke = 13;
  const radius = (size - stroke) / 2;
  // A 270 degree sweep reads better than a full circle: the gap anchors the eye at the bottom.
  const sweep = 0.75;
  const circumference = 2 * Math.PI * radius;
  const arc = circumference * sweep;
  const ratio = Math.max(0, Math.min(1, value / max));
  const progress = useMotionValue(0);
  const dashOffset = useTransform(progress, (latest) => arc - arc * latest);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const controls = animate(progress, ratio, { duration: 1.1, ease: [0.16, 1, 0.3, 1] });
    const counter = animate(0, value, { duration: 1.1, ease: [0.16, 1, 0.3, 1], onUpdate: setShown });
    return () => {
      controls.stop();
      counter.stop();
    };
  }, [ratio, value, progress]);

  const met = target === undefined ? true : value >= target;
  const colour = met ? 'var(--primary)' : 'var(--warning)';
  const formatter = format ?? ((input: number) => `${Math.round(input * 100)}%`);

  return (
    <div className="gauge">
      <svg height={size} role="img" viewBox={`0 0 ${size} ${size}`} width={size}>
        <title>{`${label}: ${formatter(value)}`}</title>
        <g transform={`rotate(135 ${size / 2} ${size / 2})`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            fill="none"
            r={radius}
            stroke="var(--border-light)"
            strokeDasharray={`${arc} ${circumference}`}
            strokeLinecap="round"
            strokeWidth={stroke}
          />
          {target !== undefined ? (
            <circle
              cx={size / 2}
              cy={size / 2}
              fill="none"
              r={radius}
              stroke="var(--text-muted)"
              strokeDasharray={`2 ${circumference}`}
              strokeDashoffset={-arc * (target / max)}
              strokeLinecap="round"
              strokeWidth={stroke + 6}
            />
          ) : null}
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            fill="none"
            r={radius}
            stroke={colour}
            strokeDasharray={`${arc} ${circumference}`}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            strokeWidth={stroke}
          />
        </g>
        <text className="gaugeValue" dominantBaseline="middle" textAnchor="middle" x={size / 2} y={size / 2 - 4}>
          {formatter(shown)}
        </text>
        <text className="gaugeUnit" dominantBaseline="middle" textAnchor="middle" x={size / 2} y={size / 2 + 20}>
          {label}
        </text>
      </svg>
      {caption ? <p className="gaugeCaption">{caption}</p> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ sparkline */

/** Inline trend line for table cells. Draws itself on with a stroke animation. */
export function Sparkline({ points, width = 84, height = 26, colour }: { points: number[]; width?: number; height?: number; colour?: string }) {
  const path = useMemo(() => {
    if (points.length < 2) return '';
    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;
    return points
      .map((point, index) => {
        const x = (index / (points.length - 1)) * width;
        const y = height - ((point - min) / span) * (height - 4) - 2;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(' ');
  }, [points, width, height]);

  if (!path) return <span className="mono" style={{ color: 'var(--text-muted)' }}>—</span>;
  const trendUp = points[points.length - 1] >= points[0];
  const line = colour ?? (trendUp ? 'var(--danger)' : 'var(--success)');

  return (
    <svg className="sparkline" height={height} viewBox={`0 0 ${width} ${height}`} width={width}>
      <motion.path
        animate={{ pathLength: 1 }}
        d={path}
        fill="none"
        initial={{ pathLength: 0 }}
        stroke={line}
        strokeLinecap="round"
        strokeWidth={1.8}
        transition={{ duration: 0.8, ease: 'easeOut' }}
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ heat map */

export type MatrixRow = { supplier_id: string; supplier_name: string; supplier_type: string; values: Record<string, number>; total_gbp: number };

/** Supplier by service-type variance grid. Intensity plus a printed value, never colour alone. */
export function VarianceHeatMap({
  columns,
  rows,
  peak,
  onSelect,
}: {
  columns: string[];
  rows: MatrixRow[];
  peak: number;
  onSelect?: (supplierId: string) => void;
}) {
  const [hover, setHover] = useState<string>('');
  const tokens = useChartTokens();
  if (!rows.length) return <p className="empty">No variance recorded yet.</p>;

  return (
    <div className="heatWrap">
      <div className="heatGrid" style={{ gridTemplateColumns: `minmax(150px, 1.4fr) repeat(${columns.length}, minmax(64px, 1fr)) 92px` }}>
        <div className="heatHead" />
        {columns.map((column) => (
          <div className="heatHead" key={column}>{column}</div>
        ))}
        <div className="heatHead" style={{ textAlign: 'right' }}>total</div>

        {rows.map((row, rowIndex) => (
          <div key={row.supplier_id} style={{ display: 'contents' }}>
            <motion.button
              animate={{ opacity: 1, x: 0 }}
              className="heatLabel"
              initial={{ opacity: 0, x: -8 }}
              onClick={() => onSelect?.(row.supplier_id)}
              onMouseEnter={() => setHover(row.supplier_id)}
              onMouseLeave={() => setHover('')}
              transition={{ delay: rowIndex * 0.03 }}
              type="button"
            >
              {row.supplier_name}
              <small>{row.supplier_type}</small>
            </motion.button>
            {columns.map((column, columnIndex) => {
              const value = row.values[column] ?? 0;
              const intensity = peak > 0 ? value / peak : 0;
              return (
                <motion.div
                  animate={{ opacity: 1, scale: 1 }}
                  className={`heatCell${hover === row.supplier_id ? ' rowHover' : ''}`}
                  initial={{ opacity: 0, scale: 0.86 }}
                  key={column}
                  onMouseEnter={() => setHover(row.supplier_id)}
                  onMouseLeave={() => setHover('')}
                  style={{
                    background:
                      intensity > 0
                        ? `rgba(${tokens.heatBase}, ${0.08 + intensity * 0.72})`
                        : 'var(--surface-2)',
                    // Past roughly half intensity the fill is dark enough (light theme) or bright
                    // enough (dark theme) that the label has to flip to the contrasting ink.
                    color: intensity > 0.45 ? tokens.heatInk : 'var(--text)',
                  }}
                  title={`${row.supplier_name} · ${column} · ${gbp(value)}`}
                  transition={{ delay: rowIndex * 0.03 + columnIndex * 0.02, duration: 0.25 }}
                >
                  {value > 0 ? gbp(value) : '·'}
                </motion.div>
              );
            })}
            <div className="heatTotal">{gbp(row.total_gbp)}</div>
          </div>
        ))}
      </div>
      <div className="heatLegend">
        <span>lower variance</span>
        <i />
        <span>higher variance</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ flow pipeline */

export type FlowStage = { label: string; count: number; status?: string };

/** Processing pipeline with packets that travel between stages while the view is open. */
export function FlowPipeline({ stages, onSelect }: { stages: FlowStage[]; onSelect?: (stage: FlowStage) => void }) {
  const peak = Math.max(...stages.map((stage) => stage.count), 1);

  return (
    <div className="flow">
      {stages.map((stage, index) => (
        <div className="flowItem" key={stage.label}>
          <motion.button
            animate={{ opacity: 1, y: 0 }}
            className="flowNode"
            initial={{ opacity: 0, y: 14 }}
            onClick={() => onSelect?.(stage)}
            transition={{ delay: index * 0.07, type: 'spring', stiffness: 220, damping: 22 }}
            type="button"
            whileHover={{ y: -4 }}
          >
            <span className="flowLabel">{stage.label}</span>
            <b className="flowCount">{stage.count.toLocaleString('en-GB')}</b>
            <span className="flowBar">
              <motion.i
                animate={{ width: `${(stage.count / peak) * 100}%` }}
                initial={{ width: 0 }}
                transition={{ delay: 0.2 + index * 0.07, duration: 0.7, ease: 'easeOut' }}
              />
            </span>
          </motion.button>
          {index < stages.length - 1 ? (
            <svg className="flowLink" height="14" viewBox="0 0 60 14" width="60">
              <line stroke="var(--border)" strokeDasharray="3 3" strokeWidth="2" x1="0" x2="60" y1="7" y2="7" />
              <circle fill="var(--accent)" r="3.4">
                <animate attributeName="cx" dur="2.4s" begin={`${index * 0.3}s`} from="0" repeatCount="indefinite" to="60" />
                <animate attributeName="opacity" dur="2.4s" begin={`${index * 0.3}s`} repeatCount="indefinite" values="0;1;1;0" />
              </circle>
            </svg>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ stat strip */

/** Compact labelled figure used in dense rows where a full KPI card is too heavy. */
export function StatChip({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' | 'bad' }) {
  return (
    <motion.div animate={{ opacity: 1, y: 0 }} className={`statChip${tone ? ` ${tone}` : ''}`} initial={{ opacity: 0, y: 8 }}>
      <span>{label}</span>
      <b>{value}</b>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ progress ring row */

/** Horizontal stacked bar for a small set of named parts, with a legend underneath. */
export function StackedShare({ parts, format }: { parts: Array<{ label: string; value: number }>; format?: (value: number) => string }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  const formatter = format ?? ((value: number) => value.toLocaleString('en-GB'));
  const { series } = useChartTokens();

  return (
    <div>
      <div className="stackBar">
        {parts.map((part, index) => (
          <motion.span
            animate={{ width: `${(part.value / total) * 100}%` }}
            initial={{ width: 0 }}
            key={part.label}
            style={{ background: series[index % series.length] }}
            title={`${part.label}: ${formatter(part.value)}`}
            transition={{ delay: index * 0.08, duration: 0.6, ease: 'easeOut' }}
          />
        ))}
      </div>
      <div className="stackLegend">
        {parts.map((part, index) => (
          <span key={part.label}>
            <i style={{ background: series[index % series.length] }} />
            {part.label} <b>{formatter(part.value)}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

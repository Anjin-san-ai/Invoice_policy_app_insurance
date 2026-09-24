import { motion, useMotionValue, useTransform, animate } from 'framer-motion';
import { useEffect, useState } from 'react';

/** Animated counter used by every KPI card, so numbers count up rather than snapping in. */
function Counter({ to, format }: { to: number; format: (value: number) => string }) {
  const value = useMotionValue(0);
  const rounded = useTransform(value, (latest) => format(latest));
  const [text, setText] = useState(format(0));

  useEffect(() => {
    const controls = animate(value, to, { duration: 0.7, ease: 'easeOut' });
    const unsubscribe = rounded.on('change', setText);
    return () => {
      controls.stop();
      unsubscribe();
    };
  }, [to, value, rounded]);

  return <>{text}</>;
}

export function KpiCard({
  label,
  value,
  detail,
  format,
  onDrill,
  drillLabel,
}: {
  label: string;
  value: number;
  detail: string;
  format?: (value: number) => string;
  onDrill?: () => void;
  drillLabel?: string;
}) {
  const formatter = format ?? ((input: number) => Math.round(input).toLocaleString('en-GB'));

  return (
    <motion.button
      className="kpi"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      disabled={!onDrill}
      onClick={onDrill}
      type="button"
    >
      <span>{label}</span>
      <strong>
        <Counter format={formatter} to={value} />
      </strong>
      <small>{detail}</small>
      {onDrill ? <span className="drill">{drillLabel ?? 'View invoices'} &rarr;</span> : null}
    </motion.button>
  );
}

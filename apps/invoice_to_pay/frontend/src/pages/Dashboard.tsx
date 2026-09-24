import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { WS_BASE } from '../api/client';
import { useApi } from '../api/useApi';
import { ExceptionDonut, LeakageByCategory } from '../charts/Charts';
import { FlowPipeline, RadialGauge, StackedShare, StatChip } from '../charts/Visuals';
import { Empty, Loading } from '../components/Common';
import { KpiCard } from '../components/KpiCard';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { CycleTime, Kpis, Leakage, gbp } from '../types';

/* The pipeline maps onto the statuses an invoice can actually be filtered by. Extracted, Redacted
   and Matched are stages every processed invoice has passed, so they filter on the whole set. */
const STAGES = [
  { label: 'Received', status: 'Received' },
  { label: 'Extracted', status: '' },
  { label: 'Redacted', status: '' },
  { label: 'Matched', status: '' },
  { label: 'Validated', status: 'Queried' },
  { label: 'Approved', status: 'Approved' },
  { label: 'Paid', status: 'Paid' },
] as const;

export function Dashboard() {
  const kpis = useApi<Kpis>('/api/analytics/kpis');
  const leakage = useApi<Leakage>('/api/analytics/leakage');
  const cycle = useApi<CycleTime>('/api/analytics/cycle-time');
  const [stream, setStream] = useState<Array<{ invoice_id: string; status: string; gross_gbp: number }>>([]);

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE}/ws/invoice-stream`);
    socket.onmessage = (event) => setStream((items) => [JSON.parse(event.data), ...items].slice(0, 7));
    return () => socket.close();
  }, []);

  if (kpis.loading) return <Loading rows={5} />;
  if (kpis.error) return <Empty>Could not load KPIs: {kpis.error}</Empty>;
  if (!kpis.data) return <Empty>No KPI data.</Empty>;

  const data = kpis.data;
  const distribution = cycle.data?.distribution ?? {};
  // Value sitting on invoices that have not been released yet, derived from the status mix.
  const withheld = Math.max(
    0,
    Math.round((data.payments_released_gbp / Math.max(1, data.payments_released_count)) * data.queried_or_awaiting_information),
  );

  return (
    <>
      <PageHead
        eyebrow="Claims finance"
        title="Automated invoice and outlay validation"
        sub="Audit-ready capture, redaction, claim matching, re-rating, exception routing, payment and ICE write-back across the seeded demo estate."
        actions={<button className="btn" onClick={() => navigate('/queue')} type="button">Open work queue</button>}
      />

      <section className="grid kpis section">
        <KpiCard detail="Seeded six-month estate" label="Invoices received" onDrill={() => navigate('/queue')} value={data.invoices_received} />
        <KpiCard
          detail={`${data.straight_through_count.toLocaleString('en-GB')} paid with no human touch`}
          drillLabel="View paid"
          format={(value) => `${value.toFixed(1)}%`}
          label="Straight-through rate"
          onDrill={() => navigate('/queue', { status: 'Paid' })}
          value={data.straight_through_pct}
        />
        <KpiCard detail="Across the five-reason taxonomy" drillLabel="Triage" label="Exceptions open" onDrill={() => navigate('/exceptions')} value={data.exceptions_open} />
        <KpiCard detail="Queried or awaiting information" drillLabel="View queried" label="In supplier dispute" onDrill={() => navigate('/queue', { status: 'Queried' })} value={data.queried_or_awaiting_information} />
        <KpiCard
          detail={`${data.payments_released_count.toLocaleString('en-GB')} invoices released`}
          format={gbp}
          label="Payments released"
          onDrill={() => navigate('/approvals')}
          value={data.payments_released_gbp}
        />
        <KpiCard detail="Line-level variance stopped before payment" drillLabel="Analyse" format={gbp} label="Leakage prevented" onDrill={() => navigate('/analytics')} value={data.leakage_prevented_gbp} />
        <KpiCard
          detail={`p90 ${cycle.data?.p90_days ?? '-'} days`}
          format={(value) => `${value.toFixed(1)} d`}
          label="Median cycle time"
          onDrill={() => navigate('/analytics')}
          value={cycle.data?.median_days ?? data.median_invoice_to_payment_cycle_time_days}
        />
        <KpiCard
          detail="Lines within contracted tolerance"
          format={(value) => `${(value * 100).toFixed(1)}%`}
          label="Rate card compliance"
          onDrill={() => navigate('/rate-cards')}
          value={data.rate_card_compliance_rate}
        />
      </section>

      <section className="grid two section">
        <article className="card">
          <h2>Straight-through processing</h2>
          <p className="cardNote">Share of invoices settled with no human involvement. Dashed marker is the 70% target.</p>
          <div className="gaugeRow">
            <RadialGauge
              caption={`${data.straight_through_count.toLocaleString('en-GB')} of ${data.invoices_received.toLocaleString('en-GB')} invoices`}
              label="straight through"
              max={1}
              target={0.7}
              value={data.straight_through_pct / 100}
            />
            <RadialGauge
              caption="Lines within contracted tolerance"
              label="rate compliance"
              max={1}
              target={0.9}
              value={data.rate_card_compliance_rate}
            />
          </div>
        </article>
        <article className="card">
          <h2>Where the money sits</h2>
          <p className="cardNote">Released, still withheld pending a query, and stopped before it went out.</p>
          <StackedShare
            format={gbp}
            parts={[
              { label: 'Released', value: data.payments_released_gbp },
              { label: 'Withheld', value: withheld },
              { label: 'Stopped', value: data.leakage_prevented_gbp },
            ]}
          />
          <div className="chipRow" style={{ marginTop: 16 }}>
            <StatChip label="Median cycle" value={`${cycle.data?.median_days ?? '—'} d`} />
            <StatChip label="p90 cycle" value={`${cycle.data?.p90_days ?? '—'} d`} />
            <StatChip label="Open exceptions" tone={data.exceptions_open ? 'warn' : 'ok'} value={data.exceptions_open} />
            <StatChip label="In dispute" tone="warn" value={data.queried_or_awaiting_information} />
          </div>
        </article>
      </section>

      <article className="card section">
        <h2>Processing pipeline</h2>
        <p className="cardNote">Every stage drills into the matching invoices. Counts reflect current invoice status.</p>
        <FlowPipeline
          onSelect={(stage) => {
            const match = STAGES.find((item) => item.label === stage.label);
            navigate('/queue', match?.status ? { status: match.status } : {});
          }}
          stages={STAGES.map((stage) => ({
            label: stage.label,
            count: stage.status ? distribution[stage.status] ?? 0 : data.invoices_received,
          }))}
        />
      </article>

      <section className="grid two section">
        <article className="card">
          <h2>Exception mix</h2>
          <p className="cardNote">Click a segment to triage that reason.</p>
          <ExceptionDonut data={data.exceptions_by_reason} onSelect={(reason) => navigate('/exceptions', { reason })} />
        </article>
        <article className="card">
          <h2>Leakage prevented by service type</h2>
          <p className="cardNote">Absolute line-level variance on lines outside tolerance.</p>
          <LeakageByCategory data={leakage.data?.by_service_type ?? {}} label="Variance" />
        </article>
      </section>

      <article className="card">
        <h2>Live invoice stream</h2>
        <p className="cardNote">WebSocket feed from /ws/invoice-stream.</p>
        {stream.length === 0 ? (
          <Empty>Waiting for stream events.</Empty>
        ) : (
          stream.map((item, index) => (
            <motion.button
              animate={{ opacity: 1 }}
              className="stream"
              initial={{ opacity: 0 }}
              key={`${item.invoice_id}-${index}`}
              onClick={() => navigate(`/invoice/${item.invoice_id}`)}
              style={{ width: '100%', border: 0, textAlign: 'left', cursor: 'pointer' }}
              type="button"
            >
              <strong className="mono">{item.invoice_id}</strong>
              <span>{item.status}</span>
              <small>{gbp(item.gross_gbp)}</small>
              <ChevronRight size={14} />
            </motion.button>
          ))
        )}
      </article>
    </>
  );
}

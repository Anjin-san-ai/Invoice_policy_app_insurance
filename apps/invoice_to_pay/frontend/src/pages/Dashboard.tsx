import { motion } from 'framer-motion';
import { ChevronRight, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { WS_BASE } from '../api/client';
import { useApi } from '../api/useApi';
import { ExceptionDonut, LeakageByCategory } from '../charts/Charts';
import { FlowPipeline, RadialGauge, StackedShare, StatChip } from '../charts/Visuals';
import { DrillCard, DrillCardBody, DrillChip, Empty, Loading } from '../components/Common';
import { KpiCard } from '../components/KpiCard';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { ClaimStatistics, CycleTime, Kpis, Leakage, SEVERITY_LABEL, WORKFLOW_LABEL, gbp } from '../types';

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
  const claims = useApi<ClaimStatistics>('/api/claims/statistics');
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
  const claimStats = claims.data;
  const distribution = cycle.data?.distribution ?? {};
  // Value sitting on invoices that have not been released yet, derived from the status mix.
  const withheld = Math.max(
    0,
    Math.round((data.payments_released_gbp / Math.max(1, data.payments_released_count)) * data.queried_or_awaiting_information),
  );

  return (
    <>
      <PageHead
        eyebrow="Claims finance Agentic App"
        title="Automated invoice and outlay validation"
        sub="Audit-ready capture, redaction, claim matching, re-rating, exception routing, payment and Invoice write-back across the seeded demo estate."
        actions={<button className="btn" onClick={() => navigate('/queue')} type="button">Open work queue</button>}
      />

      {/* One line of invoice and outlay figures. */}
      <h3 className="tierLabel">Invoices and outlay</h3>
      <section className="grid kpis compact section">
        <KpiCard detail="Six-month estate" drillLabel="Queue" label="Invoices" onDrill={() => navigate('/queue')} value={data.invoices_received} />
        <KpiCard
          detail={`${data.straight_through_count.toLocaleString('en-GB')} with no human touch`}
          drillLabel="View paid"
          format={(value) => `${value.toFixed(1)}%`}
          label="Straight through"
          onDrill={() => navigate('/queue', { status: 'Paid' })}
          value={data.straight_through_pct}
        />
        <KpiCard detail="Five-reason taxonomy" drillLabel="Triage" label="Exceptions" onDrill={() => navigate('/exceptions')} value={data.exceptions_open} />
        <KpiCard detail="Queried with suppliers" drillLabel="Queried" label="In dispute" onDrill={() => navigate('/queue', { status: 'Queried' })} value={data.queried_or_awaiting_information} />
        <KpiCard
          detail={`${data.payments_released_count.toLocaleString('en-GB')} released`}
          drillLabel="Approvals"
          format={gbp}
          label="Paid out"
          onDrill={() => navigate('/approvals')}
          value={data.payments_released_gbp}
        />
        <KpiCard detail="Stopped before payment" drillLabel="Analyse" format={gbp} label="Leakage stopped" onDrill={() => navigate('/analytics')} value={data.leakage_prevented_gbp} />
      </section>

      {/* ------------------------------------------------ claims ------------------------------ */}
      {claimStats ? (
        <>
          <h3 className="tierLabel">Claims</h3>
          {claimStats.awaiting_triage > 0 ? (
            <button className="banner info bannerBtn" onClick={() => navigate('/claims')} type="button">
              <Sparkles size={16} />
              {claimStats.awaiting_triage} claim{claimStats.awaiting_triage === 1 ? '' : 's'} waiting on triage,
              including customer-raised claims. Open Claim 360 to review and instruct suppliers.
              <ChevronRight size={15} />
            </button>
          ) : null}

          {/* One line of claim figures, compact enough to read at a glance. */}
          <section className="grid kpis compact section">
            <KpiCard
              detail={`${claimStats.open_claims.toLocaleString('en-GB')} open`}
              drillLabel="Claim 360"
              label="Claims"
              onDrill={() => navigate('/claims')}
              value={claimStats.total_claims}
            />
            <KpiCard
              detail="Raised in the portal"
              drillLabel="Review"
              label="Self-service"
              onDrill={() => navigate('/claims')}
              value={claimStats.portal_claims}
            />
            <KpiCard
              detail="Waiting on a handler"
              drillLabel="Triage"
              label="Awaiting triage"
              onDrill={() => navigate('/claims')}
              value={claimStats.awaiting_triage}
            />
            <KpiCard
              detail={`${claimStats.photographs.toLocaleString('en-GB')} photographs on file`}
              drillLabel="Open"
              label="Supplier jobs"
              onDrill={() => navigate('/claims')}
              value={claimStats.work_orders_open}
            />
            <KpiCard
              detail={`${claimStats.reserve_utilisation_pct}% used`}
              drillLabel="Claim 360"
              format={gbp}
              label="Reserved"
              onDrill={() => navigate('/claims')}
              value={claimStats.reserve_gbp}
            />
            <KpiCard
              detail="Invoiced above reserve"
              drillLabel="Investigate"
              label="Over reserve"
              onDrill={() => navigate('/claims')}
              value={claimStats.over_reserve_count}
            />
          </section>

          <section className="grid two section">
            <DrillCard
              drillLabel="Claim 360"
              note="Where every claim currently sits, from triage through to the invoices arriving."
              onDrill={() => navigate('/claims')}
              title="Claims by stage"
            >
              <DrillCardBody>
                <StackedShare
                  parts={Object.entries(claimStats.by_stage).map(([stage, count]) => ({
                    label: WORKFLOW_LABEL[stage] ?? stage,
                    value: count,
                  }))}
                />
              </DrillCardBody>
              <div className="chipRow" style={{ marginTop: 16 }}>
                {Object.entries(claimStats.by_severity).map(([severity, count]) => (
                  <StatChip
                    key={severity}
                    label={SEVERITY_LABEL[severity] ?? severity}
                    tone={severity === 'total_loss' || severity === 'major' ? 'bad' : undefined}
                    value={count}
                  />
                ))}
              </div>
            </DrillCard>

            <DrillCard
              drillLabel="Claim 360"
              note="What is actually happening to these vehicles, across the claim estate."
              onDrill={() => navigate('/claims')}
              title="Claims by incident type"
            >
              <DrillCardBody>
                <LeakageByCategory
                  data={Object.fromEntries(
                    Object.entries(claimStats.by_incident_type).sort((left, right) => right[1] - left[1]),
                  )}
                  label="Claims"
                />
              </DrillCardBody>
            </DrillCard>
          </section>
        </>
      ) : null}

      {/* ------------------------------------------------ invoices ---------------------------- */}
      <h3 className="tierLabel">Invoice processing</h3>
      <section className="grid two section">
        <DrillCard
          drillLabel="Analytics"
          note="Share of invoices settled with no human involvement. Dashed marker is the 70% target."
          onDrill={() => navigate('/analytics')}
          title="Straight-through processing"
        >
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
        </DrillCard>
        <DrillCard
          drillLabel="Approvals"
          note="Released, still withheld pending a query, and stopped before it went out."
          onDrill={() => navigate('/approvals')}
          title="Where the money sits"
        >
          <DrillCardBody>
            <StackedShare
              format={gbp}
              parts={[
                { label: 'Released', value: data.payments_released_gbp },
                { label: 'Withheld', value: withheld },
                { label: 'Stopped', value: data.leakage_prevented_gbp },
              ]}
            />
            <div className="chipRow" style={{ marginTop: 16 }}>
              <DrillChip label="Median cycle" onDrill={() => navigate('/analytics')} value={`${cycle.data?.median_days ?? '—'} d`} />
              <DrillChip label="p90 cycle" onDrill={() => navigate('/analytics')} value={`${cycle.data?.p90_days ?? '—'} d`} />
              <DrillChip
                label="Open exceptions"
                onDrill={() => navigate('/exceptions')}
                tone={data.exceptions_open ? 'warn' : 'ok'}
                value={data.exceptions_open}
              />
              <DrillChip
                label="In dispute"
                onDrill={() => navigate('/queue', { status: 'Queried' })}
                tone="warn"
                value={data.queried_or_awaiting_information}
              />
            </div>
          </DrillCardBody>
        </DrillCard>
      </section>

      <DrillCard
        className="section"
        drillLabel="Work queue"
        note="Every stage drills into the matching invoices. Counts reflect current invoice status."
        onDrill={() => navigate('/queue')}
        title="Processing pipeline"
      >
        <DrillCardBody>
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
        </DrillCardBody>
      </DrillCard>

      <section className="grid two section">
        <DrillCard
          drillLabel="Exceptions"
          note="Click a segment to triage that reason."
          onDrill={() => navigate('/exceptions')}
          title="Exception mix"
        >
          <DrillCardBody>
            <ExceptionDonut data={data.exceptions_by_reason} onSelect={(reason) => navigate('/exceptions', { reason })} />
          </DrillCardBody>
        </DrillCard>
        <DrillCard
          drillLabel="Analytics"
          note="Absolute line-level variance on lines outside tolerance."
          onDrill={() => navigate('/analytics')}
          title="Leakage prevented by service type"
        >
          <DrillCardBody>
            <LeakageByCategory data={leakage.data?.by_service_type ?? {}} label="Variance" />
          </DrillCardBody>
        </DrillCard>
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

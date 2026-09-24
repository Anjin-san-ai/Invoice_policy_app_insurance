import { useApi } from '../api/useApi';
import { ExceptionDonut, LeakageByCategory, StatusDistribution } from '../charts/Charts';
import { VarianceHeatMap } from '../charts/Visuals';
import { Empty, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { CycleTime, ExceptionTrends, Kpis, Leakage, SupplierMatrix, gbp, reasonLabel } from '../types';

export function Analytics() {
  const kpis = useApi<Kpis>('/api/analytics/kpis');
  const leakage = useApi<Leakage>('/api/analytics/leakage');
  const trends = useApi<ExceptionTrends>('/api/analytics/exception-trends');
  const cycle = useApi<CycleTime>('/api/analytics/cycle-time');
  const matrix = useApi<SupplierMatrix>('/api/analytics/supplier-matrix');

  if (kpis.loading) return <Loading rows={5} />;
  if (kpis.error) return <Empty>Could not load analytics: {kpis.error}</Empty>;

  return (
    <>
      <PageHead
        eyebrow="Claims operations manager"
        title="Analytics"
        sub="Leakage prevented, straight-through rate, cycle time distribution and exception trends. Every chart drills into the underlying invoices."
      />

      <section className="grid kpis section">
        <article className="card"><h3>Straight-through rate</h3><p className="bigStat">{kpis.data?.straight_through_pct.toFixed(1)}%</p><small>Target is 70% on the demo set</small></article>
        <article className="card"><h3>Leakage prevented</h3><p className="bigStat">{gbp(kpis.data?.leakage_prevented_gbp ?? 0)}</p><small>Line-level variance stopped</small></article>
        <article className="card"><h3>Median cycle time</h3><p className="bigStat">{cycle.data?.median_days ?? '—'} d</p><small>p90 {cycle.data?.p90_days ?? '—'} days</small></article>
        <article className="card"><h3>Open exceptions</h3><p className="bigStat">{trends.data?.total_open.toLocaleString('en-GB') ?? '—'}</p><small>Across five reasons</small></article>
      </section>

      <section className="grid two section">
        <article className="card">
          <h2>Leakage by service type</h2>
          <LeakageByCategory data={leakage.data?.by_service_type ?? {}} label="Variance" />
        </article>
        <article className="card">
          <h2>Leakage by supplier</h2>
          <p className="cardNote">Top twelve suppliers by variance at risk.</p>
          <LeakageByCategory data={leakage.data?.by_supplier ?? {}} label="Variance" />
        </article>
      </section>

      <section className="grid two section">
        <article className="card">
          <h2>Leakage by exception reason</h2>
          <LeakageByCategory data={leakage.data?.by_exception_reason ?? {}} label="Variance" />
        </article>
        <article className="card">
          <h2>Exception mix</h2>
          <p className="cardNote">Click a segment to triage that reason.</p>
          <ExceptionDonut data={trends.data?.count_by_reason ?? {}} onSelect={(reason) => navigate('/exceptions', { reason })} />
        </article>
      </section>

      <article className="card section">
        <h2>Variance heat map</h2>
        <p className="cardNote">
          Highest-exposure suppliers against service type. Darker means more money stopped. Click a supplier to open their invoices.
        </p>
        {matrix.loading ? (
          <Loading rows={3} />
        ) : (
          <VarianceHeatMap
            columns={matrix.data?.columns ?? []}
            onSelect={(supplierId) => navigate('/queue', { supplier: supplierId })}
            peak={matrix.data?.peak_gbp ?? 0}
            rows={matrix.data?.rows ?? []}
          />
        )}
      </article>

      <section className="grid two">
        <article className="card">
          <h2>Cycle time distribution by status</h2>
          <p className="cardNote">Click a bar to open that status in the work queue.</p>
          <StatusDistribution data={cycle.data?.distribution ?? {}} onSelect={(status) => navigate('/queue', { status })} />
        </article>
        <article className="card">
          <h2>Value at risk by reason</h2>
          <div className="tableWrap">
            <table>
              <thead><tr><th>Reason</th><th className="num">Count</th><th className="num">Value at risk</th></tr></thead>
              <tbody>
                {Object.entries(trends.data?.count_by_reason ?? {}).map(([reason, count]) => (
                  <tr className="clickable" key={reason} onClick={() => navigate('/exceptions', { reason })}>
                    <td>{reasonLabel(reason)}</td>
                    <td className="num">{count.toLocaleString('en-GB')}</td>
                    <td className="num">{gbp(trends.data?.value_at_risk_by_reason[reason] ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="cardNote" style={{ marginTop: 12 }}>
            Cycle times are derived from the seeded status mix, not wall-clock timestamps, because the whole dataset is processed in one deterministic warm-up run.
          </p>
        </article>
      </section>
    </>
  );
}

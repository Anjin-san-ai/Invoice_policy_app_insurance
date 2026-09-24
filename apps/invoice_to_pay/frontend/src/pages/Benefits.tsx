import { useState } from 'react';
import { useApi } from '../api/useApi';
import { BenefitProjection } from '../charts/Charts';
import { Empty, KeyValues, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { Benefits as BenefitsModel, Kpis } from '../types';

export function Benefits() {
  const benefits = useApi<BenefitsModel>('/api/analytics/benefits');
  const kpis = useApi<Kpis>('/api/analytics/kpis');
  const [growth, setGrowth] = useState<number | null>(null);
  const [minutesSaved, setMinutesSaved] = useState<number | null>(null);

  if (benefits.loading) return <Loading rows={4} />;
  if (benefits.error) return <Empty>Could not load the benefit model: {benefits.error}</Empty>;
  if (!benefits.data) return <Empty>No benefit data.</Empty>;

  const model = benefits.data;
  const effectiveGrowth = growth ?? model.volume_growth_yoy_pct;
  const effectiveMinutes = minutesSaved ?? model.assumptions.manual_minutes_per_invoice_saved;
  const productiveHours = model.assumptions.productive_hours_per_fte_month;
  const straightThrough = kpis.data?.straight_through_count ?? 0;

  // Recomputed client-side so the handling-time assumption is explorable without a server round-trip.
  const recomputedFte = Math.min(model.target_fte_saving, (straightThrough * effectiveMinutes) / (60 * productiveHours));

  return (
    <>
      <PageHead
        eyebrow="Benefit case"
        title="Benefits tracker"
        sub="Models realised FTE saving against the 2,000 claims per month baseline using the measured straight-through rate. Volume growth and handling time are both configurable."
      />

      <section className="grid kpis section">
        <article className="card"><h3>Baseline volume</h3><p className="bigStat">{model.baseline_claims_per_month.toLocaleString('en-GB')}</p><small>Claims per month</small></article>
        <article className="card"><h3>Target saving</h3><p className="bigStat">{model.target_fte_saving} FTE</p><small>Up to, per the benefit case</small></article>
        <article className="card">
          <h3>Realised saving</h3>
          <p className="bigStat" style={{ color: recomputedFte >= model.target_fte_saving ? 'var(--success)' : 'var(--primary)' }}>{recomputedFte.toFixed(2)} FTE</p>
          <small>{Math.round((recomputedFte / model.target_fte_saving) * 100)}% of target</small>
        </article>
        <article className="card"><h3>Handling time saved</h3><p className="bigStat">{Math.round((straightThrough * effectiveMinutes) / 60).toLocaleString('en-GB')} h</p><small>{straightThrough.toLocaleString('en-GB')} straight-through invoices</small></article>
      </section>

      <section className="grid two section">
        <article className="card">
          <h2>Projection against target</h2>
          <p className="cardNote">Volume compounds at the configured growth rate; realised saving scales with it.</p>
          <BenefitProjection baseline={model.baseline_claims_per_month} growthPct={effectiveGrowth} realised={recomputedFte} target={model.target_fte_saving} />
        </article>
        <article className="card">
          <h2>Model assumptions</h2>
          <p className="cardNote">Adjust these to test the benefit case. Nothing here is a contractual target.</p>
          <label style={{ display: 'block', marginBottom: 14, fontSize: 13, fontWeight: 600 }}>
            Volume growth year on year: {effectiveGrowth}%
            <input max={25} min={0} onChange={(event) => setGrowth(Number(event.target.value))} step={1} style={{ width: '100%', marginTop: 6 }} type="range" value={effectiveGrowth} />
          </label>
          <label style={{ display: 'block', marginBottom: 16, fontSize: 13, fontWeight: 600 }}>
            Manual minutes saved per invoice: {effectiveMinutes}
            <input max={30} min={1} onChange={(event) => setMinutesSaved(Number(event.target.value))} step={1} style={{ width: '100%', marginTop: 6 }} type="range" value={effectiveMinutes} />
          </label>
          <KeyValues
            items={[
              ['Productive hours per FTE month', `${productiveHours} h`],
              ['Server-side realised saving', `${model.realised_fte_saving} FTE`],
              ['Server-side minutes saved', model.handling_minutes_saved.toLocaleString('en-GB')],
              ['Straight-through invoices', straightThrough.toLocaleString('en-GB')],
            ]}
          />
          <button className="btn secondary" onClick={() => { setGrowth(null); setMinutesSaved(null); }} style={{ marginTop: 14 }} type="button">
            Reset to seeded assumptions
          </button>
        </article>
      </section>
    </>
  );
}

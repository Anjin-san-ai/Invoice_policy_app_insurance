import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CalendarClock, CheckCircle2, ChevronDown, FileCheck2, Layers, PoundSterling } from 'lucide-react';
import { useMemo, useState } from 'react';
import { ApiState, useApi } from '../api/useApi';
import { StatChip } from '../charts/Visuals';
import { Empty, KeyValues, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { RateCard, SettingsResponse, gbp } from '../types';

type Filter = 'all' | 'stale' | 'in_force' | 'variance';

/** Effective window bar with a marker for today, so the dating is readable at a glance. */
function EffectiveBar({ card }: { card: RateCard }) {
  const from = new Date(card.effective_from).getTime();
  const to = new Date(card.effective_to).getTime();
  const review = new Date(card.review_due_date).getTime();
  const span = to - from || 1;
  const todayPct = Math.max(0, Math.min(100, ((Date.now() - from) / span) * 100));
  const reviewPct = Math.max(0, Math.min(100, ((review - from) / span) * 100));

  return (
    <div className="effWrap">
      <div className="effBar">
        <motion.i animate={{ width: `${todayPct}%` }} className="effElapsed" initial={{ width: 0 }} transition={{ duration: 0.7, ease: 'easeOut' }} />
        <span className="effReview" style={{ left: `${reviewPct}%` }} title={`Review due ${card.review_due_date}`} />
        <span className="effToday" style={{ left: `${todayPct}%` }} title="Today" />
      </div>
      <div className="effLabels">
        <span>{card.effective_from}</span>
        <span>review {card.review_due_date}</span>
        <span>{card.effective_to}</span>
      </div>
    </div>
  );
}

export function RateCards() {
  const cards = useApi<RateCard[]>('/api/rate-cards');
  const settings = useApi<SettingsResponse>('/api/settings');
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [tab, setTab] = useState<'registry' | 'controls'>('registry');

  const all = cards.data ?? [];
  const rows = useMemo(() => {
    let items = all;
    if (filter === 'stale') items = items.filter((card) => card.is_stale);
    if (filter === 'in_force') items = items.filter((card) => card.is_in_force);
    if (filter === 'variance') items = items.filter((card) => card.variance_found_gbp > 0);
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      items = items.filter(
        (card) => card.id.toLowerCase().includes(needle) || card.supplier_name.toLowerCase().includes(needle) || card.supplier_id.toLowerCase().includes(needle),
      );
    }
    return items;
  }, [all, filter, search]);

  const stale = all.filter((card) => card.is_stale);
  const staleInForce = stale.filter((card) => card.is_in_force);

  return (
    <>
      <PageHead
        eyebrow="Policy dependency"
        title="Policies"
        sub="Effective-dated contracts that every charge is validated against, and the thresholds those charges are judged by. A policy past its review date is flagged stale, and a stale policy still in force is the one to worry about."
      />

      {/* The controls tab holds what used to be a separate Settings screen: every value on it is
          a policy control, so it belongs with the policies it governs. */}
      <div className="filters">
        <button className={`filterChip${tab === 'registry' ? ' on' : ''}`} onClick={() => setTab('registry')} type="button">
          Policy registry ({all.length})
        </button>
        <button className={`filterChip${tab === 'controls' ? ' on' : ''}`} onClick={() => setTab('controls')} type="button">
          Validation controls
        </button>
      </div>

      {tab === 'controls' ? <PolicyControls settings={settings} /> : null}

      <div hidden={tab !== 'registry'}>
      <section className="chipRow section">
        <StatChip label="Policies" value={all.length} />
        <StatChip label="In force" tone="ok" value={all.filter((card) => card.is_in_force).length} />
        <StatChip label="Stale" tone={stale.length ? 'bad' : 'ok'} value={stale.length} />
        <StatChip label="Stale and in force" tone={staleInForce.length ? 'bad' : 'ok'} value={staleInForce.length} />
        <StatChip label="Lines validated" value={all.reduce((total, card) => total + card.lines_validated_against, 0).toLocaleString('en-GB')} />
        <StatChip label="Variance found" tone="warn" value={gbp(all.reduce((total, card) => total + card.variance_found_gbp, 0))} />
        <StatChip label="Review window" value={`${settings.data?.settings.rate_card_stale_days ?? '—'} d`} />
      </section>

      {staleInForce.length > 0 ? (
        <p className="banner warn">
          <AlertTriangle size={16} />
          {staleInForce.length} polic{staleInForce.length === 1 ? 'y is' : 'ies are'} past their review date but still being
          used to validate live invoices. Charges are being checked against contracts nobody has re-confirmed.
        </p>
      ) : null}

      <div className="filters">
        <button className={`filterChip${filter === 'all' ? ' on' : ''}`} onClick={() => setFilter('all')} type="button">All ({all.length})</button>
        <button className={`filterChip${filter === 'in_force' ? ' on' : ''}`} onClick={() => setFilter('in_force')} type="button">In force</button>
        <button className={`filterChip${filter === 'stale' ? ' on' : ''}`} onClick={() => setFilter('stale')} type="button">Stale ({stale.length})</button>
        <button className={`filterChip${filter === 'variance' ? ' on' : ''}`} onClick={() => setFilter('variance')} type="button">Found variance</button>
        <input aria-label="Search policies" onChange={(event) => setSearch(event.target.value)} placeholder="Policy id or supplier" value={search} />
      </div>

      {cards.loading ? (
        <Loading rows={4} />
      ) : cards.error ? (
        <Empty>Could not load policies: {cards.error}</Empty>
      ) : rows.length === 0 ? (
        <Empty>No policies match these filters.</Empty>
      ) : (
        <section className="grid rateGrid">
          {rows.map((card, index) => {
            const open = expanded === card.id;
            return (
              <motion.article
                animate={{ opacity: 1, y: 0 }}
                className={`rateCard${card.is_stale ? ' stale' : ''}${card.is_in_force ? ' inForce' : ''}`}
                initial={{ opacity: 0, y: 16 }}
                key={card.id}
                layout
                transition={{ delay: Math.min(index * 0.03, 0.4), type: 'spring', stiffness: 230, damping: 24 }}
              >
                <header className="rateCardHead">
                  <div>
                    <b className="mono">{card.id}</b>
                    <span className="rateCardVersion">v{card.version}</span>
                  </div>
                  <div className="rateCardFlags">
                    {card.is_in_force ? <span className="chip within"><CheckCircle2 size={11} /> in force</span> : <span className="chip">superseded</span>}
                    {card.is_stale ? <span className="chip stale"><AlertTriangle size={11} /> stale</span> : null}
                  </div>
                </header>

                <button className="rateCardSupplier" onClick={() => navigate('/queue', { supplier: card.supplier_id })} type="button">
                  {card.supplier_name}
                  <small>{card.supplier_type} · {card.supplier_id} · {card.version_count_for_supplier} version{card.version_count_for_supplier === 1 ? '' : 's'} on file</small>
                </button>

                <div className="rateCardMetrics">
                  <div>
                    <span><PoundSterling size={11} /> rate</span>
                    <b>{card.rate_span_gbp[0] === card.rate_span_gbp[1] ? gbp(card.rate_span_gbp[0]) : `${gbp(card.rate_span_gbp[0])} – ${gbp(card.rate_span_gbp[1])}`}</b>
                  </div>
                  <div>
                    <span><FileCheck2 size={11} /> checked</span>
                    <b>{card.lines_validated_against.toLocaleString('en-GB')} lines</b>
                  </div>
                  <div>
                    <span><Layers size={11} /> invoices</span>
                    <b>{card.invoices_validated_against.toLocaleString('en-GB')}</b>
                  </div>
                  <div>
                    <span>value checked</span>
                    <b>{gbp(card.value_checked_gbp)}</b>
                  </div>
                  <div>
                    <span>variance found</span>
                    <b style={{ color: card.variance_found_gbp > 0 ? 'var(--danger)' : 'var(--success)' }}>{gbp(card.variance_found_gbp)}</b>
                  </div>
                  <div>
                    <span><CalendarClock size={11} /> review</span>
                    <b style={{ color: card.days_to_review < 0 ? 'var(--critical)' : 'var(--text)' }}>
                      {card.days_to_review < 0 ? `${Math.abs(card.days_to_review)} d overdue` : `in ${card.days_to_review} d`}
                    </b>
                  </div>
                </div>

                <EffectiveBar card={card} />

                <button className="rateCardToggle" onClick={() => setExpanded(open ? null : card.id)} type="button">
                  <ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }} />
                  {open ? 'Hide' : 'Show'} {card.line_count} contracted rate{card.line_count === 1 ? '' : 's'}
                </button>

                <AnimatePresence initial={false}>
                  {open ? (
                    <motion.div
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      initial={{ height: 0, opacity: 0 }}
                      style={{ overflow: 'hidden' }}
                      transition={{ duration: 0.25 }}
                    >
                      <table className="rateLineTable">
                        <thead>
                          <tr><th>Line</th><th>Service</th><th>Unit</th><th className="num">Rate</th><th className="num">Max</th></tr>
                        </thead>
                        <tbody>
                          {card.lines.map((line) => (
                            <tr key={line.id}>
                              <td className="mono">{line.id}</td>
                              <td>{line.service_type}</td>
                              <td>{line.unit}</td>
                              <td className="num">{gbp(line.rate_gbp)}</td>
                              <td className="num">{line.max_units}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="rateCardClause">{card.lines[0]?.conditions}</p>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </motion.article>
            );
          })}
        </section>
      )}
      </div>
    </>
  );
}

/** Validation thresholds, benefit parameters and redaction rules that govern every policy check.
 *
 * This was a separate Settings screen. It reads better here: a handler questioning why a charge
 * was flagged wants the tolerance that flagged it on the same screen as the contract.
 */
function PolicyControls({ settings }: { settings: ApiState<SettingsResponse> }) {
  if (settings.loading) return <Loading rows={3} />;
  if (settings.error) return <Empty>Could not load the validation controls: {settings.error}</Empty>;
  if (!settings.data) return <Empty>No validation controls.</Empty>;

  const values = settings.data.settings;

  return (
    <>
      <p className="cardNote">
        Thresholds and redaction rules are configuration-driven, loaded from the seed file rather
        than hard-coded. Read-only in this build.
      </p>

      <section className="grid two section">
        <article className="card">
          <h2>Validation thresholds</h2>
          <KeyValues
            items={[
              ['High value threshold', gbp(values.high_value_threshold_gbp)],
              ['Tolerance percent', `${values.tolerance_pct}%`],
              ['Tolerance absolute', gbp(values.tolerance_gbp)],
              ['Minimum extraction confidence', values.min_extraction_confidence],
              ['Minimum match confidence', values.min_match_confidence],
              ['Policy staleness window', `${values.rate_card_stale_days} days`],
            ]}
          />
        </article>
        <article className="card">
          <h2>Benefit model parameters</h2>
          <KeyValues
            items={Object.entries(settings.data.metadata).map(([key, value]) => [
              key.replace(/_/g, ' '),
              String(value),
            ])}
          />
        </article>
      </section>

      <article className="card">
        <h2>GDPR and PII redaction rules</h2>
        <p className="cardNote">
          Applied by the deterministic rule engine before any model exposure. Each match writes a
          what-and-why audit entry.
        </p>
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Rule</th><th>Reason</th><th>Pattern</th></tr>
            </thead>
            <tbody>
              {values.redaction_rules.map((rule) => (
                <tr key={rule.id}>
                  <td className="mono">{rule.id}</td>
                  <td>{rule.reason}</td>
                  <td className="mono">{rule.pattern}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}

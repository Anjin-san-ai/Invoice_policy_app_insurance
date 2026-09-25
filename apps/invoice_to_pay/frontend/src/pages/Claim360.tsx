import { motion } from 'framer-motion';
import { AlertTriangle, ArrowLeft, Building2, FileText, Layers, ShieldCheck, Wallet } from 'lucide-react';
import { useState } from 'react';
import { useApi } from '../api/useApi';
import { FlowPipeline, RadialGauge, StackedShare, StatChip } from '../charts/Visuals';
import { ConfidenceMeter, Empty, KeyValues, Loading, StatusChip } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { ClaimOverview, ClaimRow, gbp, reasonLabel } from '../types';

const STAGES = ['Received', 'Extracted', 'Redacted', 'Matched', 'Validated', 'Approved', 'Paid'] as const;

/** Claim list: the entry point into the 360 view. */
function ClaimList() {
  const [search, setSearch] = useState('');
  const query = search.trim() ? `/api/claims?limit=60&search=${encodeURIComponent(search.trim())}` : '/api/claims?limit=60';
  const { data, error, loading } = useApi<ClaimRow[]>(query);

  return (
    <>
      <PageHead
        eyebrow="Claim 360"
        title="Claims with supplier spend"
        sub="One accident usually attracts several invoices from different suppliers. Open a claim to see every bill, authorisation, payment and decision attached to it in one place."
      />

      <article className="card">
        <div className="filters">
          <input aria-label="Search claims" onChange={(event) => setSearch(event.target.value)} placeholder="Claim id" value={search} />
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <Empty>Could not load claims: {error}</Empty>
        ) : !data || data.length === 0 ? (
          <Empty>No claims match.</Empty>
        ) : (
          <div className="tableWrap">
            <table>
              <thead>
                <tr><th>Claim</th><th>Incident</th><th className="num">Invoices</th><th className="num">Suppliers</th><th className="num">Invoiced</th><th className="num">Paid</th><th className="num">Open</th><th className="num">Variance</th><th>Reserve used</th></tr>
              </thead>
              <tbody>
                {data.map((row, index) => {
                  const utilisation = row.claim.reserve_gbp ? row.invoiced_gbp / row.claim.reserve_gbp : 0;
                  return (
                    <motion.tr
                      animate={{ opacity: 1, y: 0 }}
                      className="clickable"
                      initial={{ opacity: 0, y: 6 }}
                      key={row.claim.id}
                      onClick={() => navigate(`/claim/${row.claim.id}`)}
                      transition={{ delay: Math.min(index * 0.015, 0.4) }}
                    >
                      <td className="mono">{row.claim.id}</td>
                      <td className="mono">{row.claim.incident_date}</td>
                      <td className="num">{row.invoice_count}</td>
                      <td className="num">{row.supplier_count}</td>
                      <td className="num">{gbp(row.invoiced_gbp)}</td>
                      <td className="num">{gbp(row.paid_gbp)}</td>
                      <td className="num">{row.open_count > 0 ? <span className="chip warn">{row.open_count}</span> : <span className="chip within">0</span>}</td>
                      <td className="num">{row.variance_gbp > 0 ? <span style={{ color: 'var(--danger)', fontWeight: 700 }}>{gbp(row.variance_gbp)}</span> : '—'}</td>
                      <td><ConfidenceMeter threshold={1.0} value={Math.min(1, utilisation)} /></td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </>
  );
}

/** The 360 degree view of a single claim. */
function ClaimDetail({ claimId }: { claimId: string }) {
  const { data, error, loading } = useApi<ClaimOverview>(`/api/claims/${claimId}/overview`);
  const [tab, setTab] = useState<'invoices' | 'authorisations' | 'timeline'>('invoices');

  if (loading) return <Loading rows={6} />;
  if (error) return <Empty>Could not load claim {claimId}: {error}</Empty>;
  if (!data) return <Empty>Claim {claimId} not found.</Empty>;

  const money = data.financials;
  const overAuth = data.authorisations.filter((row) => row.units_over > 0 || row.value_over_gbp > 0);

  return (
    <>
      <PageHead
        eyebrow="Claim 360"
        title={data.claim.id}
        sub={`Incident ${data.claim.incident_date} · ${data.invoices.length} invoices from ${data.suppliers.length} supplier${data.suppliers.length === 1 ? '' : 's'}`}
        actions={
          <>
            <button className="btn secondary" onClick={() => navigate('/claims')} type="button">
              <ArrowLeft size={14} /> All claims
            </button>
            <button className="btn secondary" onClick={() => navigate('/queue', { search: data.claim.id })} type="button">
              Open in work queue
            </button>
          </>
        }
      />

      {money.reserve_utilisation_pct > 100 ? (
        <p className="banner warn">
          <AlertTriangle size={16} />
          Invoiced value is {money.reserve_utilisation_pct}% of the reserve set for this claim. {gbp(money.withheld_gbp)} is
          still withheld pending query resolution, so the final settled figure will be lower.
        </p>
      ) : null}

      {/* ------------------------------------------------ money ring + stat spine */}
      <section className="grid claimTop section">
        <article className="card">
          <h2>Reserve against spend</h2>
          <div className="gaugeRow">
            <RadialGauge
              caption={`Reserve ${gbp(money.reserve_gbp)}`}
              format={(value) => `${Math.round(value)}%`}
              label="reserve used"
              max={Math.max(100, money.reserve_utilisation_pct)}
              size={176}
              value={money.reserve_utilisation_pct}
            />
            <div style={{ flex: 1, minWidth: 220 }}>
              <StackedShare
                format={gbp}
                parts={[
                  { label: 'Paid', value: money.paid_gbp },
                  { label: 'Withheld', value: money.withheld_gbp },
                  { label: 'Stopped', value: money.leakage_prevented_gbp },
                ]}
              />
              <div className="chipRow" style={{ marginTop: 14 }}>
                <StatChip label="Invoiced" value={gbp(money.invoiced_gbp)} />
                <StatChip label="VAT" value={gbp(money.vat_gbp)} />
                <StatChip label="Payments" value={`${money.released_count}/${money.payment_count}`} />
                <StatChip label="Stopped" tone={money.leakage_prevented_gbp > 0 ? 'warn' : 'ok'} value={gbp(money.leakage_prevented_gbp)} />
              </div>
            </div>
          </div>
        </article>

        <article className="card">
          <h2>Spend by service</h2>
          <p className="cardNote">What this accident actually cost, split by the kind of work.</p>
          {Object.keys(data.service_mix).length === 0 ? (
            <Empty>No lines yet.</Empty>
          ) : (
            <StackedShare format={gbp} parts={Object.entries(data.service_mix).map(([label, value]) => ({ label, value }))} />
          )}
          <h3 style={{ marginTop: 18 }}>Policy</h3>
          {data.policy ? (
            <KeyValues
              items={[
                ['Cover', data.policy.cover_type],
                ['Excess', gbp(data.policy.excess_gbp)],
                ['Entitlements', data.policy.entitlements.join(', ') || '—'],
                ['Effective', `${data.policy.effective_from} to ${data.policy.effective_to}`],
              ]}
            />
          ) : (
            <Empty>No policy linked.</Empty>
          )}
        </article>
      </section>

      {/* ------------------------------------------------ pipeline across this claim */}
      <article className="card section">
        <h2>Where this claim's invoices have got to</h2>
        <p className="cardNote">Counts are for this claim only. Click a stage to filter the work queue to it.</p>
        <FlowPipeline
          onSelect={(stage) => navigate('/queue', stage.label === 'Paid' || stage.label === 'Approved' ? { status: stage.label } : {})}
          stages={STAGES.map((label) => ({ label, count: data.stage_counts[label] ?? 0 }))}
        />
      </article>

      {/* ------------------------------------------------ suppliers on the claim */}
      <section className="grid two section">
        <article className="card">
          <h2><Building2 size={15} /> Suppliers on this claim</h2>
          {data.suppliers.map((row, index) => (
            <motion.button
              animate={{ opacity: 1, x: 0 }}
              className="listRow"
              initial={{ opacity: 0, x: -10 }}
              key={row.supplier.id}
              onClick={() => navigate('/queue', { supplier: row.supplier.id })}
              transition={{ delay: index * 0.06 }}
              type="button"
            >
              <div>
                <b>{row.supplier.name}</b>
                <small>{row.supplier.type} · pays by {row.supplier.payment_path}</small>
              </div>
              <div className="listRowRight">
                <span>{gbp(row.invoiced_gbp)}</span>
                <small>
                  {row.invoice_count} invoice{row.invoice_count === 1 ? '' : 's'}
                  {row.disputed_count > 0 ? ` · ${row.disputed_count} queried` : ''}
                </small>
              </div>
            </motion.button>
          ))}
        </article>

        <article className="card">
          <h2><ShieldCheck size={15} /> Governance on this claim</h2>
          <div className="chipRow">
            <StatChip label="Exceptions" tone={data.exceptions.length ? 'warn' : 'ok'} value={data.exceptions.length} />
            <StatChip label="Open queries" tone={data.disputes.length ? 'warn' : 'ok'} value={data.disputes.length} />
            <StatChip label="Over authorisation" tone={overAuth.length ? 'bad' : 'ok'} value={overAuth.length} />
            <StatChip label="Audit events" value={data.timeline.length} />
          </div>
          {data.exceptions.length === 0 ? (
            <p className="cardNote" style={{ marginTop: 14 }}>Nothing on this claim needed a human.</p>
          ) : (
            <div style={{ marginTop: 14 }}>
              {data.exceptions.slice(0, 4).map((record) => (
                <div className="miniCard" key={record.id}>
                  <span className="chip warn">{reasonLabel(record.reason)}</span>
                  <p>{record.explanation}</p>
                  <button className="btn secondary" onClick={() => navigate(`/invoice/${record.invoice_id}`)} style={{ padding: '4px 10px', fontSize: 12 }} type="button">
                    {record.invoice_id}
                  </button>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      {/* ------------------------------------------------ tabbed detail */}
      <div className="filters">
        <button className={`filterChip${tab === 'invoices' ? ' on' : ''}`} onClick={() => setTab('invoices')} type="button">
          <FileText size={13} /> Invoices ({data.invoices.length})
        </button>
        <button className={`filterChip${tab === 'authorisations' ? ' on' : ''}`} onClick={() => setTab('authorisations')} type="button">
          <Wallet size={13} /> Authorisations ({data.authorisations.length})
        </button>
        <button className={`filterChip${tab === 'timeline' ? ' on' : ''}`} onClick={() => setTab('timeline')} type="button">
          <Layers size={13} /> Timeline ({data.timeline.length})
        </button>
      </div>

      {tab === 'invoices' ? (
        <section className="grid three">
          {data.invoices.map((invoice, index) => (
            <motion.button
              animate={{ opacity: 1, y: 0 }}
              className="invoiceCard"
              initial={{ opacity: 0, y: 14 }}
              key={invoice.id}
              onClick={() => navigate(`/invoice/${invoice.id}`)}
              transition={{ delay: index * 0.05, type: 'spring', stiffness: 240, damping: 24 }}
              type="button"
              whileHover={{ y: -4 }}
            >
              <div className="invoiceCardTop">
                <b className="mono">{invoice.invoice_number}</b>
                <StatusChip status={invoice.status} />
              </div>
              <p className="invoiceCardValue">{gbp(invoice.gross_gbp)}</p>
              <KeyValues
                items={[
                  ['Supplier', invoice.supplier_id],
                  ['Channel', invoice.channel],
                  ['Lines', `${invoice.line_count}${invoice.outside_line_ids.length ? ` (${invoice.outside_line_ids.length} disputed)` : ''}`],
                  ['Decision', invoice.decision ?? '—'],
                ]}
              />
              {invoice.variance_gbp > 0 ? (
                <p className="invoiceCardFlag">
                  <AlertTriangle size={12} /> {gbp(invoice.variance_gbp)} over the rate card
                </p>
              ) : (
                <p className="invoiceCardOk">Charges match the rate card</p>
              )}
            </motion.button>
          ))}
        </section>
      ) : null}

      {tab === 'authorisations' ? (
        <article className="card">
          <h2>What we authorised against what we were charged</h2>
          <p className="cardNote">This is where the classic overcharge shows up: 10 days approved, 14 days billed.</p>
          {data.authorisations.length === 0 ? (
            <Empty>No authorisations recorded for this claim.</Empty>
          ) : (
            <div className="tableWrap">
              <table>
                <thead>
                  <tr><th>Authorisation</th><th>Supplier</th><th>Service</th><th className="num">Units approved</th><th className="num">Units billed</th><th className="num">Value approved</th><th className="num">Value billed</th><th>Outcome</th></tr>
                </thead>
                <tbody>
                  {data.authorisations.map((row) => {
                    const over = row.units_over > 0 || row.value_over_gbp > 0;
                    return (
                      <tr key={row.authorisation.id}>
                        <td className="mono">{row.authorisation.id}</td>
                        <td className="mono">{row.authorisation.supplier_id}</td>
                        <td>{row.authorisation.service_type}</td>
                        <td className="num">{row.authorisation.authorised_units}</td>
                        <td className="num">{row.charged_units}</td>
                        <td className="num">{gbp(row.authorisation.authorised_value_gbp)}</td>
                        <td className="num">{gbp(row.charged_value_gbp)}</td>
                        <td>
                          {over ? (
                            <span className="chip outside">
                              <AlertTriangle size={12} /> over by {row.units_over > 0 ? `${row.units_over} units` : gbp(row.value_over_gbp)}
                            </span>
                          ) : (
                            <span className="chip within">within authorisation</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ) : null}

      {tab === 'timeline' ? (
        <article className="card">
          <h2>Everything that happened on this claim</h2>
          <p className="cardNote">Drawn from the append-only audit log, oldest first.</p>
          <div className="trace">
            {data.timeline.map((event, index) => (
              <motion.div
                animate={{ opacity: 1, x: 0 }}
                className="traceItem"
                initial={{ opacity: 0, x: 10 }}
                key={event.id}
                transition={{ delay: Math.min(index * 0.03, 0.5) }}
              >
                <b style={{ fontSize: 13 }}>{event.event_type.replace(/_/g, ' ')}</b>
                <div className="meta">
                  {event.entity_type} <span className="mono">{event.entity_id}</span> · {event.actor} {event.actor_id} · {event.occurred_at}
                </div>
              </motion.div>
            ))}
          </div>
        </article>
      ) : null}
    </>
  );
}

export function Claim360({ claimId }: { claimId: string }) {
  return claimId ? <ClaimDetail claimId={claimId} /> : <ClaimList />;
}

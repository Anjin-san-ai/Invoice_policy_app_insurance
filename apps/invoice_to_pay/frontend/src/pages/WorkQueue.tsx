import { motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { apiPost } from '../api/client';
import { useApi } from '../api/useApi';
import { Sparkline } from '../charts/Visuals';
import { ConfidenceMeter, Empty, Loading, StatusChip } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { CANONICAL_STATUSES, Invoice, gbp, reasonLabel } from '../types';

type SortKey = 'value' | 'age' | 'confidence';

export function WorkQueue({
  status,
  reason,
  supplierId,
  initialSearch,
}: {
  status: string;
  reason: string;
  supplierId: string;
  initialSearch: string;
}) {
  // Status and supplier filter server-side; reason and free-text narrow the returned page. A larger
  // page is requested when arriving with a search term, since the match may be deep in the estate.
  const query = new URLSearchParams({ limit: initialSearch ? '2000' : '400' });
  if (status) query.set('status', status);
  if (supplierId) query.set('supplier_id', supplierId);
  const { data, error, loading, reload } = useApi<Invoice[]>(`/api/invoices?${query.toString()}`);
  const [search, setSearch] = useState(initialSearch);
  const [sort, setSort] = useState<SortKey>('value');
  const [approving, setApproving] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  /** Approve from the queue, which raises the payment and sends it to the release lane. */
  async function approve(invoiceId: string) {
    setApproving(invoiceId);
    setActionError(null);
    setNote(null);
    try {
      await apiPost(`/api/invoices/${invoiceId}/approve`, { actor_id: 'analyst-alice' });
      setNote(`${invoiceId} approved and now awaiting release on Approvals & Payments.`);
      reload();
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setApproving('');
    }
  }

  // Adopt a new search term when the route changes, for example arriving from Claim 360.
  useEffect(() => {
    setSearch(initialSearch);
  }, [initialSearch]);

  // Recent variance trend per supplier, drawn from the invoices already on this page so the
  // sparkline costs no extra request.
  const trends = useMemo(() => {
    const bySupplier = new Map<string, number[]>();
    for (const invoice of data ?? []) {
      const variance = invoice.lines.reduce((total, line) => total + (line.tolerance_outcome === 'outside' ? Math.abs(line.variance_gbp) : 0), 0);
      const series = bySupplier.get(invoice.supplier_id) ?? [];
      if (series.length < 12) series.push(variance);
      bySupplier.set(invoice.supplier_id, series);
    }
    return bySupplier;
  }, [data]);

  const rows = useMemo(() => {
    let items = data ?? [];
    if (reason) items = items.filter((invoice) => invoice.exception_reason === reason);
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      items = items.filter(
        (invoice) =>
          invoice.invoice_number.toLowerCase().includes(needle) ||
          invoice.supplier_id.toLowerCase().includes(needle) ||
          (invoice.claim_id ?? '').toLowerCase().includes(needle),
      );
    }
    const sorted = [...items];
    if (sort === 'value') sorted.sort((left, right) => right.gross_gbp - left.gross_gbp);
    if (sort === 'age') sorted.sort((left, right) => left.received_at.localeCompare(right.received_at));
    if (sort === 'confidence') sorted.sort((left, right) => left.match_confidence - right.match_confidence);
    return sorted;
  }, [data, reason, search, sort]);

  return (
    <>
      <PageHead
        eyebrow="Claims finance analyst"
        title="Invoice work queue"
        sub="Prioritised queue across the seeded estate. Select a row to open the invoice drilldown with document viewer, line validation and agent trace."
      />

      <div className="filters">
        <button className={`filterChip${status === '' ? ' on' : ''}`} onClick={() => navigate('/queue')} type="button">
          All statuses
        </button>
        {CANONICAL_STATUSES.map((value) => (
          <button className={`filterChip${status === value ? ' on' : ''}`} key={value} onClick={() => navigate('/queue', { status: value })} type="button">
            {value}
          </button>
        ))}
        <input aria-label="Search invoices" onChange={(event) => setSearch(event.target.value)} placeholder="Invoice, supplier or claim" value={search} />
        <select aria-label="Sort by" onChange={(event) => setSort(event.target.value as SortKey)} value={sort}>
          <option value="value">Sort by value</option>
          <option value="age">Sort by age</option>
          <option value="confidence">Sort by match confidence</option>
        </select>
      </div>

      {reason || supplierId ? (
        <p className="cardNote">
          Filtered to{reason ? <> exception reason <strong>{reasonLabel(reason)}</strong></> : null}
          {reason && supplierId ? ' and' : null}
          {supplierId ? <> supplier <strong className="mono">{supplierId}</strong></> : null}.{' '}
          <button className="btn secondary" onClick={() => navigate('/queue', status ? { status } : {})} type="button">
            Clear filters
          </button>
        </p>
      ) : null}

      {note ? <p className="banner ok">{note}</p> : null}
      {actionError ? <p className="banner bad">{actionError}</p> : null}

      <article className="card">
        <h2>
          {rows.length.toLocaleString('en-GB')} invoice{rows.length === 1 ? '' : 's'}
        </h2>
        {loading ? (
          <Loading />
        ) : error ? (
          <Empty>Could not load invoices: {error}</Empty>
        ) : rows.length === 0 ? (
          <Empty>No invoices match these filters.</Empty>
        ) : (
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Supplier</th>
                  <th>Claim</th>
                  <th>Channel</th>
                  <th className="num">Gross</th>
                  <th className="num">VAT</th>
                  <th>Status</th>
                  <th>Match confidence</th>
                  <th>Supplier variance</th>
                  <th>Exception</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 150).map((invoice, index) => (
                  <motion.tr
                    animate={{ opacity: 1, y: 0 }}
                    className="clickable"
                    initial={{ opacity: 0, y: 5 }}
                    key={invoice.id}
                    onClick={() => navigate(`/invoice/${invoice.id}`)}
                    transition={{ delay: Math.min(index * 0.012, 0.35) }}
                  >
                    <td className="mono">{invoice.invoice_number}</td>
                    <td>{invoice.supplier_id}</td>
                    <td className="mono">{invoice.claim_id ?? '—'}</td>
                    <td>{invoice.channel}</td>
                    <td className="num">{gbp(invoice.gross_gbp)}</td>
                    <td className="num">{gbp(invoice.vat_gbp)}</td>
                    <td>
                      <StatusChip status={invoice.status} />
                    </td>
                    <td>
                      <ConfidenceMeter value={invoice.match_confidence} />
                    </td>
                    <td>
                      <Sparkline points={trends.get(invoice.supplier_id) ?? []} />
                    </td>
                    <td>{invoice.exception_reason ? <span className="chip warn">{reasonLabel(invoice.exception_reason)}</span> : <span className="chip within">clean</span>}</td>
                    <td>
                      {/* Approving here raises the payment, so the invoice moves straight to the
                          release lane on Approvals & Payments without opening the drilldown. */}
                      {invoice.status === 'Paid' ? (
                        <span className="chip within">
                          <CheckCircle2 size={11} /> paid
                        </span>
                      ) : invoice.status === 'Approved' ? (
                        <button
                          className="chip linkChip"
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate('/approvals');
                          }}
                          type="button"
                        >
                          awaiting release
                        </button>
                      ) : (
                        <button
                          className="btn small"
                          disabled={approving === invoice.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void approve(invoice.id);
                          }}
                          type="button"
                        >
                          {approving === invoice.id ? 'Approving…' : 'Approve'}
                        </button>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
            {rows.length > 150 ? <p className="cardNote" style={{ marginTop: 12 }}>Showing the first 150 of {rows.length.toLocaleString('en-GB')}. Narrow with search or a status filter.</p> : null}
          </div>
        )}
      </article>
    </>
  );
}

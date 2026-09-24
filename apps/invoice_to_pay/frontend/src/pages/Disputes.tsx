import { useMemo, useState } from 'react';
import { useApi } from '../api/useApi';
import { LeakageByCategory } from '../charts/Charts';
import { Empty, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { DisputeQuery, Invoice } from '../types';

export function Disputes() {
  const disputes = useApi<DisputeQuery[]>('/api/disputes');
  const invoices = useApi<Invoice[]>('/api/invoices?limit=2000');
  const [search, setSearch] = useState('');

  const bySupplier = useMemo(() => {
    const lookup = new Map((invoices.data ?? []).map((invoice) => [invoice.id, invoice]));
    const totals: Record<string, number> = {};
    for (const dispute of disputes.data ?? []) {
      const invoice = lookup.get(dispute.invoice_id);
      if (!invoice) continue;
      totals[invoice.supplier_id] = (totals[invoice.supplier_id] ?? 0) + invoice.gross_gbp;
    }
    return Object.fromEntries(Object.entries(totals).sort((left, right) => right[1] - left[1]).slice(0, 12));
  }, [disputes.data, invoices.data]);

  const rows = useMemo(() => {
    const items = disputes.data ?? [];
    if (!search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter((dispute) => dispute.invoice_id.toLowerCase().includes(needle) || dispute.line_ids.join(' ').toLowerCase().includes(needle));
  }, [disputes.data, search]);

  const awaiting = rows.filter((dispute) => !dispute.response_received_at).length;

  return (
    <>
      <PageHead
        eyebrow="Supplier relationship manager"
        title="Disputes workspace"
        sub="Every open query names the specific line items in question, never the whole invoice. Supplier responses trigger re-validation."
      />

      <section className="grid three section">
        <article className="card">
          <h3>Open queries</h3>
          <p className="bigStat">{rows.length.toLocaleString('en-GB')}</p>
        </article>
        <article className="card">
          <h3>Awaiting supplier response</h3>
          <p className="bigStat">{awaiting.toLocaleString('en-GB')}</p>
        </article>
        <article className="card">
          <h3>Lines in question</h3>
          <p className="bigStat">{rows.reduce((total, dispute) => total + dispute.line_ids.length, 0).toLocaleString('en-GB')}</p>
        </article>
      </section>

      <article className="card section">
        <h2>Disputed value by supplier</h2>
        <p className="cardNote">Top twelve suppliers by gross value of invoices under query.</p>
        <LeakageByCategory data={bySupplier} label="Disputed value" />
      </article>

      <article className="card">
        <h2>Open dispute queries</h2>
        <div className="filters">
          <input aria-label="Search disputes" onChange={(event) => setSearch(event.target.value)} placeholder="Invoice or line id" value={search} />
        </div>
        {disputes.loading ? (
          <Loading />
        ) : disputes.error ? (
          <Empty>Could not load disputes: {disputes.error}</Empty>
        ) : rows.length === 0 ? (
          <Empty>No dispute queries match.</Empty>
        ) : (
          <div className="tableWrap">
            <table>
              <thead>
                <tr><th>Dispute</th><th>Invoice</th><th>Lines in question</th><th>Basis</th><th>Sent</th><th>Response</th><th>Outcome</th></tr>
              </thead>
              <tbody>
                {rows.slice(0, 120).map((dispute) => (
                  <tr className="clickable" key={dispute.id} onClick={() => navigate(`/invoice/${dispute.invoice_id}`)}>
                    <td className="mono">{dispute.id}</td>
                    <td className="mono">{dispute.invoice_id}</td>
                    <td className="mono">{dispute.line_ids.join(', ')}</td>
                    <td style={{ fontSize: 11 }}>{dispute.basis}</td>
                    <td className="mono">{dispute.sent_at ?? '—'}</td>
                    <td>{dispute.response_received_at ? <span className="chip within">received</span> : <span className="chip warn">awaiting</span>}</td>
                    <td>{dispute.outcome ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length > 120 ? <p className="cardNote" style={{ marginTop: 12 }}>Showing the first 120 of {rows.length.toLocaleString('en-GB')}.</p> : null}
          </div>
        )}
      </article>
    </>
  );
}

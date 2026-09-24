import { useMemo, useState } from 'react';
import { useApi } from '../api/useApi';
import { ConfidenceMeter, Empty, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { SupplierScorecard, gbp } from '../types';

export function Suppliers() {
  const { data, error, loading } = useApi<SupplierScorecard[]>('/api/suppliers');
  const [type, setType] = useState('');
  const [search, setSearch] = useState('');

  const rows = useMemo(() => {
    let items = data ?? [];
    if (type) items = items.filter((card) => card.supplier.type === type);
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      items = items.filter((card) => card.supplier.name.toLowerCase().includes(needle) || card.supplier.id.toLowerCase().includes(needle));
    }
    return items;
  }, [data, type, search]);

  const types = useMemo(() => Array.from(new Set((data ?? []).map((card) => card.supplier.type))), [data]);
  const templateCoverage = (data ?? []).filter((card) => card.has_extraction_template).length;

  return (
    <>
      <PageHead
        eyebrow="Supplier relationship manager"
        title="Supplier scorecards"
        sub="Volume, value, dispute rate, straight-through rate and rate card compliance per supplier. Drill from any supplier into their invoices."
      />

      <section className="grid three section">
        <article className="card"><h3>Suppliers</h3><p className="bigStat">{(data ?? []).length}</p></article>
        <article className="card"><h3>Extraction template coverage</h3><p className="bigStat">{(data ?? []).length ? Math.round((templateCoverage / (data ?? []).length) * 100) : 0}%</p><small>{templateCoverage} of {(data ?? []).length} suppliers</small></article>
        <article className="card"><h3>Total invoiced value</h3><p className="bigStat">{gbp((data ?? []).reduce((total, card) => total + card.invoice_value_gbp, 0))}</p></article>
      </section>

      <article className="card">
        <h2>Scorecards</h2>
        <div className="filters">
          <button className={`filterChip${type === '' ? ' on' : ''}`} onClick={() => setType('')} type="button">All types</button>
          {types.map((value) => (
            <button className={`filterChip${type === value ? ' on' : ''}`} key={value} onClick={() => setType(value)} type="button">{value}</button>
          ))}
          <input aria-label="Search suppliers" onChange={(event) => setSearch(event.target.value)} placeholder="Supplier name or id" value={search} />
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <Empty>Could not load suppliers: {error}</Empty>
        ) : rows.length === 0 ? (
          <Empty>No suppliers match.</Empty>
        ) : (
          <div className="tableWrap">
            <table>
              <thead>
                <tr><th>Supplier</th><th>Type</th><th>Payment path</th><th className="num">Invoices</th><th className="num">Value</th><th>Dispute rate</th><th>Straight through</th><th>Rate card compliance</th><th className="num">Variance at risk</th><th>Template</th></tr>
              </thead>
              <tbody>
                {rows.map((card) => (
                  <tr className="clickable" key={card.supplier.id} onClick={() => navigate('/queue', { supplier: card.supplier.id })}>
                    <td>{card.supplier.name}</td>
                    <td><span className="chip">{card.supplier.type}</span></td>
                    <td><span className="chip">{card.supplier.payment_path}</span></td>
                    <td className="num">{card.invoice_count}</td>
                    <td className="num">{gbp(card.invoice_value_gbp)}</td>
                    <td><ConfidenceMeter threshold={2} value={card.dispute_rate} /></td>
                    <td><ConfidenceMeter threshold={0.7} value={card.straight_through_rate} /></td>
                    <td><ConfidenceMeter threshold={0.9} value={card.rate_card_compliance_rate} /></td>
                    <td className="num">{gbp(card.variance_at_risk_gbp)}</td>
                    <td>{card.has_extraction_template ? <span className="chip within">yes</span> : <span className="chip warn">generic</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </>
  );
}

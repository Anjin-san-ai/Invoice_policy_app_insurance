import { useMemo, useState } from 'react';
import { apiPost } from '../api/client';
import { useApi } from '../api/useApi';
import { Empty, KeyValues, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { ExceptionRecord, ExceptionTrends, Invoice, EXCEPTION_REASONS, gbp, reasonLabel } from '../types';

export function Exceptions({ reason }: { reason: string }) {
  const exceptions = useApi<ExceptionRecord[]>('/api/exceptions');
  const trends = useApi<ExceptionTrends>('/api/analytics/exception-trends');
  const invoices = useApi<Invoice[]>('/api/invoices?limit=2000');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  // Optimistic completion so the tick lands immediately, before the list reload returns.
  const [done, setDone] = useState<Record<string, boolean>>({});

  const valueByInvoice = useMemo(() => {
    const map = new Map<string, number>();
    for (const invoice of invoices.data ?? []) map.set(invoice.id, invoice.gross_gbp);
    return map;
  }, [invoices.data]);

  const rows = useMemo(() => {
    const items = (exceptions.data ?? []).filter((record) => !reason || record.reason === reason);
    // Spec 13.6: prioritise by value then age.
    return [...items].sort((left, right) => (valueByInvoice.get(right.invoice_id) ?? 0) - (valueByInvoice.get(left.invoice_id) ?? 0) || left.opened_at.localeCompare(right.opened_at));
  }, [exceptions.data, reason, valueByInvoice]);

  async function execute(record: ExceptionRecord) {
    setBusy(record.id);
    setMessage('');
    try {
      const result = await apiPost<{ action: Record<string, unknown> }>(`/api/exceptions/${record.id}/execute-action`);
      setMessage(`Executed ${String(result.action?.type ?? 'action')} for ${record.invoice_id}. Event written to the audit log.`);
      setDone((current) => ({ ...current, [record.id]: true }));
      exceptions.reload();
    } catch (cause) {
      setMessage(`Failed: ${cause instanceof Error ? cause.message : String(cause)}`);
    } finally {
      setBusy('');
    }
  }

  async function override(record: ExceptionRecord) {
    const input = window.prompt('Override reason is mandatory. Why are you overriding this exception?');
    if (!input) {
      setMessage('Override cancelled. A reason is mandatory.');
      return;
    }
    setBusy(record.id);
    try {
      await apiPost(`/api/exceptions/${record.id}/override`, { reason: input, actor_id: 'analyst-alice' });
      setMessage(`Override recorded for ${record.invoice_id}. Original recommendation preserved in audit.`);
      exceptions.reload();
    } catch (cause) {
      setMessage(`Failed: ${cause instanceof Error ? cause.message : String(cause)}`);
    } finally {
      setBusy('');
    }
  }

  return (
    <>
      <PageHead
        eyebrow="Exception-only handling"
        title="Exceptions workspace"
        sub="The five-value taxonomy is fixed. Every exception carries a clear explanation and a pre-filled next action you can execute in one click."
      />

      <section className="grid kpis section">
        {EXCEPTION_REASONS.map((value) => (
          <button className="kpi" key={value} onClick={() => navigate('/exceptions', reason === value ? {} : { reason: value })} type="button">
            <span>{reasonLabel(value)}</span>
            <strong>{(trends.data?.count_by_reason[value] ?? 0).toLocaleString('en-GB')}</strong>
            <small>{gbp(trends.data?.value_at_risk_by_reason[value] ?? 0)} at risk</small>
            <span className="drill">{reason === value ? 'Clear filter' : 'Triage'} &rarr;</span>
          </button>
        ))}
      </section>

      {message ? <p className="cardNote" style={{ fontWeight: 700 }}>{message}</p> : null}

      <article className="card">
        <h2>{rows.length.toLocaleString('en-GB')} open exception{rows.length === 1 ? '' : 's'}{reason ? ` · ${reasonLabel(reason)}` : ''}</h2>
        <p className="cardNote">Prioritised by value at risk, then age.</p>
        {exceptions.loading ? (
          <Loading />
        ) : exceptions.error ? (
          <Empty>Could not load exceptions: {exceptions.error}</Empty>
        ) : rows.length === 0 ? (
          <Empty>No exceptions match this filter.</Empty>
        ) : (
          rows.slice(0, 60).map((record) => {
            const complete = done[record.id] === true || record.resolved_at != null;
            return (
            <div className={`card tight${complete ? ' exceptionDone' : ''}`} key={record.id} style={{ marginBottom: 10, boxShadow: 'none' }}>
              {complete ? (
                <p className="doneBadge">
                  <span className="doneTick" aria-hidden="true">&#10003;</span>
                  Complete &middot; next action executed{record.next_action.type ? ` (${record.next_action.type})` : ''}
                </p>
              ) : null}
              <KeyValues
                items={[
                  ['Invoice', <button className="btn secondary" onClick={() => navigate(`/invoice/${record.invoice_id}`)} type="button">{record.invoice_id}</button>],
                  ['Reason', <span className="chip warn">{reasonLabel(record.reason)}</span>],
                  ['Value at risk', gbp(valueByInvoice.get(record.invoice_id) ?? 0)],
                  ['Priority', `P${record.priority}`],
                  ['Explanation', record.explanation],
                  ['Next action', `${record.next_action.type ?? '—'} → ${record.next_action.target ?? '—'}`],
                  ['Draft content', record.next_action.draft_content ?? '—'],
                  ...(record.next_action.line_ids ? ([['Lines in question', record.next_action.line_ids.join(', ')]] as Array<[string, string]>) : []),
                  ...(record.resolution ? ([['Override', record.resolution]] as Array<[string, string]>) : []),
                ]}
              />
              <div className="btnRow" style={{ marginTop: 10 }}>
                {complete ? null : (
                  <button className="btn" disabled={busy === record.id} onClick={() => execute(record)} type="button">
                    {busy === record.id ? 'Executing…' : 'Execute next action'}
                  </button>
                )}
                <button className="btn secondary" disabled={busy === record.id} onClick={() => override(record)} type="button">Override with reason</button>
              </div>
            </div>
            );
          })
        )}
        {rows.length > 60 ? <p className="cardNote">Showing the first 60 of {rows.length.toLocaleString('en-GB')}.</p> : null}
      </article>
    </>
  );
}

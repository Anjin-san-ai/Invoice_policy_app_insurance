import { motion } from 'framer-motion';
import { ArrowLeft, Download, HelpCircle, Send, Undo2 } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { API_BASE, apiPost } from '../api/client';
import { useApi } from '../api/useApi';
import { VarianceWaterfall } from '../charts/Charts';
import { ConfidenceMeter, Empty, KeyValues, Loading, StatusChip, ToleranceChip } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { Invoice, RedactionLog, gbp, reasonLabel } from '../types';

/** Render the document with its PII regions blacked out, from the redaction log char offsets. */
function RedactedDocument({ text, redactions, showRedacted }: { text: string; redactions: RedactionLog[]; showRedacted: boolean }) {
  const regions = useMemo(() => {
    return redactions
      .map((entry) => {
        const match = /chars:(\d+)-(\d+)/.exec(entry.field_or_region);
        return match ? { start: Number(match[1]), end: Number(match[2]), rule: entry.rule_id, reason: entry.reason } : null;
      })
      .filter((region): region is { start: number; end: number; rule: string; reason: string } => region !== null)
      .sort((left, right) => left.start - right.start);
  }, [redactions]);

  if (!showRedacted || regions.length === 0) return <div className="docViewer">{text}</div>;

  const parts: Array<{ text: string; region?: { rule: string; reason: string } }> = [];
  let cursor = 0;
  for (const region of regions) {
    if (region.start > cursor) parts.push({ text: text.slice(cursor, region.start) });
    parts.push({ text: text.slice(region.start, region.end), region: { rule: region.rule, reason: region.reason } });
    cursor = region.end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) });

  return (
    <div className="docViewer">
      {parts.map((part, index) =>
        part.region ? (
          <span className="redacted" key={index} title={`${part.region.rule}: ${part.region.reason}`}>
            {part.text}
          </span>
        ) : (
          <Fragment key={index}>{part.text}</Fragment>
        ),
      )}
    </div>
  );
}

/** Standard reasons an invoice goes back to a supplier, so the query text stays consistent. */
const RETURN_REASONS = [
  'Charges exceed the contracted rate card — please verify and resubmit',
  'Missing or invalid claim / supplier reference',
  'Units charged exceed the authorised quantity',
  'Illegible or incomplete document — please resend a clear copy',
  'Duplicate of an invoice already submitted',
] as const;

export function InvoiceDrilldown({ invoiceId }: { invoiceId: string }) {
  const { data, error, loading, reload } = useApi<Invoice>(`/api/invoices/${invoiceId}`);
  const [showRedacted, setShowRedacted] = useState(true);
  const [showWhy, setShowWhy] = useState(false);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  // Send-back-to-supplier flow state: the composer is a step, not a blind POST.
  const [showReturn, setShowReturn] = useState(false);
  const [returnReason, setReturnReason] = useState<string>(RETURN_REASONS[0]);
  const [returnNote, setReturnNote] = useState('');
  const [returnLines, setReturnLines] = useState<string[] | null>(null);

  async function act(label: string, path: string, body: unknown = {}) {
    setBusy(label);
    setMessage('');
    try {
      await apiPost(path, body);
      setMessage(`${label} completed.`);
      reload();
    } catch (cause) {
      setMessage(`${label} failed: ${cause instanceof Error ? cause.message : String(cause)}`);
    } finally {
      setBusy('');
    }
  }

  async function exportPack() {
    setBusy('Evidence pack');
    try {
      const response = await fetch(`${API_BASE}/api/invoices/${invoiceId}/evidence-pack`);
      const pack = await response.json();
      const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `evidence-pack-${invoiceId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage('Evidence pack downloaded as JSON. PDF rendition is mocked in this prototype.');
    } catch (cause) {
      setMessage(`Evidence pack failed: ${cause instanceof Error ? cause.message : String(cause)}`);
    } finally {
      setBusy('');
    }
  }

  if (loading) return <Loading rows={6} />;
  if (error) return <Empty>Could not load invoice {invoiceId}: {error}</Empty>;
  if (!data) return <Empty>Invoice {invoiceId} not found.</Empty>;

  const outside = data.validation_summary?.outside_line_ids ?? [];
  const redactions = data.redactions ?? [];
  // A return query stays open until the supplier resubmits, and drives which step the flow shows.
  const returnQuery = (data.disputes ?? []).find((item) => item.basis === 'returned_for_resubmission');
  const isReturned = returnQuery != null && returnQuery.outcome == null;
  const selectedLines = returnLines ?? outside;
  const previewText =
    `Invoice ${data.invoice_number} has been returned for verification and resubmission. ` +
    `Reason: ${[returnReason, returnNote.trim()].filter(Boolean).join(' — ')}` +
    (selectedLines.length ? ` Lines to recheck: ${selectedLines.join(', ')}.` : '');

  return (
    <>
      <PageHead
        eyebrow="Invoice drilldown"
        title={data.invoice_number}
        sub={`${data.supplier?.name ?? data.supplier_id} · received via ${data.channel} · layout ${data.layout_id}`}
        actions={
          <>
            <button className="btn secondary" onClick={() => navigate('/queue')} type="button">
              <ArrowLeft size={14} style={{ verticalAlign: '-2px' }} /> Queue
            </button>
            <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Reprocess', `/api/invoices/${invoiceId}/reprocess`)} type="button">
              Reprocess
            </button>
            <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Approve', `/api/invoices/${invoiceId}/approve`, { actor_id: 'analyst-alice' })} type="button">
              Approve
            </button>
            <button
              className="btn warnBtn"
              disabled={busy !== '' || isReturned || data.status === 'Paid'}
              onClick={() => { setReturnLines(outside.length ? outside : []); setShowReturn((current) => !current); }}
              type="button"
            >
              <Undo2 size={14} style={{ verticalAlign: '-2px' }} /> Send back to supplier
            </button>
            <button className="btn" disabled={busy !== ''} onClick={exportPack} type="button">
              <Download size={14} style={{ verticalAlign: '-2px' }} /> Evidence pack
            </button>
          </>
        }
      />

      {message ? <p className="cardNote" style={{ fontWeight: 700 }}>{message}</p> : null}

      {isReturned ? (
        <motion.article animate={{ opacity: 1, y: 0 }} className="card returnOpen" initial={{ opacity: 0, y: -8 }}>
          <h2><Undo2 size={16} style={{ verticalAlign: '-3px' }} /> With the supplier for verification</h2>
          <p className="cardNote">
            Sent {returnQuery?.sent_at ?? 'just now'}. The invoice sits at <b>Awaiting information</b> and will not pay
            until the supplier resubmits. Query <span className="mono">{returnQuery?.id}</span>.
          </p>
          <blockquote className="returnQuote">{returnQuery?.query_text}</blockquote>
          {selectedLines.length ? <p className="cardNote">Lines under query: <span className="mono">{returnQuery?.line_ids.join(', ')}</span></p> : null}
          <div className="btnRow" style={{ marginTop: 10 }}>
            <button
              className="btn"
              disabled={busy !== ''}
              onClick={() => act('Supplier resubmission', `/api/invoices/${invoiceId}/resubmit`, { actor_id: 'analyst-alice', note: 'Corrected invoice received from supplier.' })}
              type="button"
            >
              <Send size={14} style={{ verticalAlign: '-2px' }} /> Record resubmission and re-validate
            </button>
          </div>
          <p className="cardNote">Recording the resubmission closes the query and re-runs every validation step, so the corrected invoice earns its status again.</p>
        </motion.article>
      ) : null}

      {showReturn && !isReturned ? (
        <motion.article animate={{ opacity: 1, y: 0 }} className="card returnComposer" initial={{ opacity: 0, y: -8 }}>
          <h2>Send back for verification and resubmission</h2>
          <p className="cardNote">Step 1 of 2 — compose the query. The supplier is notified and the invoice moves to Awaiting information.</p>

          <label className="fieldLabel" htmlFor="returnReason">Standard reason</label>
          <select className="field" id="returnReason" onChange={(event) => setReturnReason(event.target.value)} value={returnReason}>
            {RETURN_REASONS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>

          <label className="fieldLabel" htmlFor="returnNote">Additional detail (optional)</label>
          <textarea className="field" id="returnNote" onChange={(event) => setReturnNote(event.target.value)} placeholder="Anything specific the supplier should check" rows={2} value={returnNote} />

          {data.lines.length ? (
            <>
              <p className="fieldLabel">Lines to recheck {outside.length ? '(pre-selected from lines outside tolerance)' : ''}</p>
              <div className="lineChips">
                {data.lines.map((line) => {
                  const picked = selectedLines.includes(line.id);
                  return (
                    <button
                      className={`chip toggle${picked ? ' on' : ''}`}
                      key={line.id}
                      onClick={() => setReturnLines(picked ? selectedLines.filter((value) => value !== line.id) : [...selectedLines, line.id])}
                      type="button"
                    >
                      L{line.line_no} · {line.service_type} · {gbp(line.amount_gbp)}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}

          <p className="fieldLabel">Preview of the supplier query</p>
          <blockquote className="returnQuote">{previewText}</blockquote>

          <div className="btnRow" style={{ marginTop: 10 }}>
            <button
              className="btn warnBtn"
              disabled={busy !== ''}
              onClick={() =>
                act('Send back to supplier', `/api/invoices/${invoiceId}/return-to-supplier`, {
                  actor_id: 'analyst-alice',
                  reason: [returnReason, returnNote.trim()].filter(Boolean).join(' — '),
                  line_ids: selectedLines,
                }).then(() => setShowReturn(false))
              }
              type="button"
            >
              {busy === 'Send back to supplier' ? 'Sending…' : 'Send back to supplier'}
            </button>
            <button className="btn secondary" disabled={busy !== ''} onClick={() => setShowReturn(false)} type="button">Cancel</button>
          </div>
        </motion.article>
      ) : null}

      <div className="ribbon">
        <div className="cell"><span>Status</span><b><StatusChip status={data.status} /></b></div>
        <div className="cell"><span>Gross</span><b>{gbp(data.gross_gbp)}</b></div>
        <div className="cell"><span>Net</span><b>{gbp(data.net_gbp)}</b></div>
        <div className="cell"><span>VAT</span><b>{gbp(data.vat_gbp)}</b></div>
        <div className="cell"><span>Claim</span><b className="mono">{data.claim_id ?? 'unmatched'}</b></div>
        <div className="cell"><span>Match ({data.match_method})</span><b><ConfidenceMeter value={data.match_confidence} /></b></div>
        <div className="cell"><span>Straight through</span><b>{data.straight_through ? 'Yes' : 'No'}</b></div>
        {data.exception_reason ? <div className="cell"><span>Exception</span><b><span className="chip warn">{reasonLabel(data.exception_reason)}</span></b></div> : null}
      </div>

      <div className="threePane">
        <article className="card">
          <h2>Document viewer</h2>
          <div className="btnRow" style={{ marginBottom: 10 }}>
            <button className={`filterChip${showRedacted ? ' on' : ''}`} onClick={() => setShowRedacted(true)} type="button">Redacted</button>
            <button className={`filterChip${!showRedacted ? ' on' : ''}`} onClick={() => setShowRedacted(false)} type="button">Original</button>
          </div>
          <RedactedDocument redactions={redactions} showRedacted={showRedacted} text={data.document_text} />
          <h3 style={{ marginTop: 16 }}>Redaction log ({redactions.length})</h3>
          {redactions.length === 0 ? (
            <Empty>No PII detected in this document.</Empty>
          ) : (
            <table>
              <thead><tr><th>Rule</th><th>Region</th><th>Reason</th></tr></thead>
              <tbody>
                {redactions.map((entry) => (
                  <tr key={entry.id}><td className="mono">{entry.rule_id}</td><td className="mono">{entry.field_or_region}</td><td>{entry.reason}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </article>

        <article className="card">
          <h2>Line-level validation</h2>
          <p className="cardNote">Charged against the rate card effective on the service date. Outside-tolerance lines are named individually.</p>
          <VarianceWaterfall rows={data.lines} />
          <div className="tableWrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>#</th><th>Service</th><th>Dates</th><th className="num">Units</th><th className="num">Charged</th><th className="num">Expected</th><th className="num">Variance</th><th>Outcome</th><th>Extraction</th></tr>
              </thead>
              <tbody>
                {data.lines.map((line) => (
                  <Fragment key={line.id}>
                    <tr>
                      <td>{line.line_no}</td>
                      <td>{line.service_type}</td>
                      <td className="mono">{line.service_date_from} to {line.service_date_to}</td>
                      <td className="num">{line.units}</td>
                      <td className="num">{gbp(line.amount_gbp)}</td>
                      <td className="num">{gbp(line.expected_amount_gbp)}</td>
                      <td className="num">{gbp(line.variance_gbp)} ({line.variance_pct.toFixed(1)}%)</td>
                      <td><ToleranceChip outcome={line.tolerance_outcome} /></td>
                      <td><ConfidenceMeter value={line.extracted_confidence} /></td>
                    </tr>
                    {line.evidence.length > 0 ? (
                      <tr>
                        <td colSpan={9} style={{ paddingTop: 0 }}>
                          <details>
                            <summary style={{ cursor: 'pointer', fontSize: 12, color: '#5a6b85' }}>Evidence applied to line {line.line_no}</summary>
                            <pre>{JSON.stringify(line.evidence, null, 2)}</pre>
                          </details>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <h2>Agent trace</h2>
          <p className="cardNote">{data.trace?.length ?? 0} agents ran. Expand any step for its inputs and outputs.</p>
          <div className="trace">
            {(data.trace ?? []).map((entry, index) => (
              <motion.details
                animate={{ opacity: 1, x: 0 }}
                className="traceItem"
                initial={{ opacity: 0, x: 8 }}
                key={entry.id}
                open={index === 0}
                transition={{ delay: index * 0.06 }}
              >
                <summary>
                  {entry.agent_name}
                  <div className="meta">
                    {entry.duration_ms} ms · confidence {Math.round(entry.confidence * 100)}% · prompt {entry.prompt_version}
                  </div>
                </summary>
                <pre>{JSON.stringify({ input: entry.input_json, output: entry.output_json }, null, 2)}</pre>
              </motion.details>
            ))}
          </div>

          <h3 style={{ marginTop: 18 }}>Recommendation</h3>
          {data.decision ? (
            <>
              <KeyValues
                items={[
                  ['Decision', <span className="chip">{data.decision.decision}</span>],
                  ['Confidence', `${Math.round(data.decision.confidence * 100)}%`],
                  ['Affected lines', data.decision.affected_lines.length ? data.decision.affected_lines.join(', ') : 'none'],
                  ['Model', data.decision.model_version],
                  ['Prompt', data.decision.prompt_version],
                ]}
              />
              <button className="btn secondary" onClick={() => setShowWhy((value) => !value)} style={{ marginTop: 12 }} type="button">
                <HelpCircle size={14} style={{ verticalAlign: '-2px' }} /> {showWhy ? 'Hide' : 'Why this decision?'}
              </button>
              {showWhy ? (
                <>
                  <p className="cardNote" style={{ marginTop: 10 }}>{data.decision.reasoning}</p>
                  <h3>Evidence cited</h3>
                  <pre>{JSON.stringify(data.decision.evidence, null, 2)}</pre>
                </>
              ) : null}
            </>
          ) : (
            <Empty>No decision recorded yet.</Empty>
          )}
        </article>
      </div>

      {outside.length > 0 || (data.disputes?.length ?? 0) > 0 ? (
        <article className="card" style={{ marginTop: 16 }}>
          <h2>Dispute queries</h2>
          {(data.disputes ?? []).map((dispute) => (
            <div key={dispute.id}>
              <KeyValues items={[['Lines in question', dispute.line_ids.join(', ')], ['Basis', dispute.basis], ['Sent', dispute.sent_at ?? 'not sent']]} />
              <p className="cardNote" style={{ marginTop: 8 }}>{dispute.query_text}</p>
            </div>
          ))}
        </article>
      ) : null}

      {(data.exceptions?.length ?? 0) > 0 ? (
        <article className="card" style={{ marginTop: 16 }}>
          <h2>Exceptions and next actions</h2>
          {(data.exceptions ?? []).map((record) => (
            <div key={record.id} style={{ marginBottom: 14 }}>
              <KeyValues
                items={[
                  ['Reason', <span className="chip warn">{reasonLabel(record.reason)}</span>],
                  ['Explanation', record.explanation],
                  ['Next action', `${record.next_action.type ?? '—'} → ${record.next_action.target ?? '—'}`],
                  ['Draft', record.next_action.draft_content ?? '—'],
                ]}
              />
              <button className="btn" disabled={busy !== ''} onClick={() => act('Execute action', `/api/exceptions/${record.id}/execute-action`)} style={{ marginTop: 10 }} type="button">
                Execute pre-filled action
              </button>
            </div>
          ))}
        </article>
      ) : null}
    </>
  );
}

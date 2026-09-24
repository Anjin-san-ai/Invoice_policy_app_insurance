import { ShieldCheck, ShieldX } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useApi } from '../api/useApi';
import { Empty, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { AuditEvent, AuditResponse, RedactionLog } from '../types';

type Tab = 'events' | 'redactions' | 'replay';

export function AuditTrail() {
  const audit = useApi<AuditResponse>('/api/audit?limit=400');
  const redactions = useApi<RedactionLog[]>('/api/redactions?limit=300');
  const [tab, setTab] = useState<Tab>('events');
  const [entityType, setEntityType] = useState('');
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const entityTypes = useMemo(() => Array.from(new Set((audit.data?.events ?? []).map((event) => event.entity_type))), [audit.data]);
  const events = useMemo(() => {
    const items = audit.data?.events ?? [];
    return entityType ? items.filter((event) => event.entity_type === entityType) : items;
  }, [audit.data, entityType]);

  const valid = audit.data?.hash_chain_valid;

  return (
    <>
      <PageHead
        eyebrow="Compliance and audit officer"
        title="Audit trail"
        sub="Append-only, hash-chained event log covering every state change, agent decision, human override and payment action. Select any event to open its replay view."
        actions={
          <span className={`chip ${valid ? 'within' : 'danger'}`} style={{ padding: '10px 16px', fontSize: 13 }}>
            {valid ? <ShieldCheck size={15} /> : <ShieldX size={15} />}
            Hash chain {valid ? 'verified' : 'BROKEN'}
          </span>
        }
      />

      <section className="grid three section">
        <article className="card"><h3>Total audit events</h3><p className="bigStat">{(audit.data?.total ?? 0).toLocaleString('en-GB')}</p></article>
        <article className="card"><h3>Redaction log rows</h3><p className="bigStat">{(redactions.data ?? []).length.toLocaleString('en-GB')}</p><small>Showing most recent 300</small></article>
        <article className="card"><h3>Entity types tracked</h3><p className="bigStat">{entityTypes.length}</p></article>
      </section>

      <div className="filters">
        <button className={`filterChip${tab === 'events' ? ' on' : ''}`} onClick={() => setTab('events')} type="button">Event log</button>
        <button className={`filterChip${tab === 'redactions' ? ' on' : ''}`} onClick={() => setTab('redactions')} type="button">Redaction log</button>
        <button className={`filterChip${tab === 'replay' ? ' on' : ''}`} onClick={() => setTab('replay')} type="button">Decision replay</button>
      </div>

      {tab === 'events' ? (
        <article className="card">
          <h2>{events.length.toLocaleString('en-GB')} events</h2>
          <div className="filters">
            <button className={`filterChip${entityType === '' ? ' on' : ''}`} onClick={() => setEntityType('')} type="button">All entities</button>
            {entityTypes.map((value) => (
              <button className={`filterChip${entityType === value ? ' on' : ''}`} key={value} onClick={() => setEntityType(value)} type="button">{value}</button>
            ))}
          </div>
          {audit.loading ? (
            <Loading />
          ) : audit.error ? (
            <Empty>Could not load the audit log: {audit.error}</Empty>
          ) : (
            <div className="tableWrap">
              <table>
                <thead><tr><th>Event</th><th>Entity</th><th>Type</th><th>Actor</th><th>Occurred</th><th>Hash</th></tr></thead>
                <tbody>
                  {events.slice().reverse().slice(0, 150).map((event) => (
                    <tr className="clickable" key={event.id} onClick={() => { setSelected(event); setTab('replay'); }}>
                      <td className="mono">{event.id}</td>
                      <td className="mono">{event.entity_type}:{event.entity_id}</td>
                      <td><span className="chip">{event.event_type}</span></td>
                      <td>{event.actor} / <span className="mono">{event.actor_id}</span></td>
                      <td className="mono">{event.occurred_at}</td>
                      <td className="mono" title={event.hash}>{event.hash.slice(0, 10)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ) : null}

      {tab === 'redactions' ? (
        <article className="card">
          <h2>GDPR and PII redaction log</h2>
          <p className="cardNote">Records what was redacted and why, per rule, for every PII-bearing document.</p>
          {redactions.loading ? (
            <Loading />
          ) : (redactions.data ?? []).length === 0 ? (
            <Empty>No redaction records.</Empty>
          ) : (
            <div className="tableWrap">
              <table>
                <thead><tr><th>Record</th><th>Invoice</th><th>Rule</th><th>Region</th><th>Reason</th><th>Redacted at</th></tr></thead>
                <tbody>
                  {(redactions.data ?? []).slice(0, 150).map((entry) => (
                    <tr className="clickable" key={entry.id} onClick={() => navigate(`/invoice/${entry.invoice_id}`)}>
                      <td className="mono">{entry.id}</td>
                      <td className="mono">{entry.invoice_id}</td>
                      <td className="mono">{entry.rule_id}</td>
                      <td className="mono">{entry.field_or_region}</td>
                      <td>{entry.reason}</td>
                      <td className="mono">{entry.redacted_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ) : null}

      {tab === 'replay' ? (
        <article className="card">
          <h2>Decision replay</h2>
          {selected === null ? (
            <Empty>Select an event from the event log to replay it.</Empty>
          ) : (
            <>
              <p className="cardNote">
                Event <strong className="mono">{selected.id}</strong> on {selected.entity_type} <strong className="mono">{selected.entity_id}</strong>, by {selected.actor} {selected.actor_id}, at {selected.occurred_at}.
              </p>
              <div className="btnRow" style={{ marginBottom: 12 }}>
                <button className="btn secondary" onClick={() => navigate(`/invoice/${selected.entity_id}`)} type="button">Open invoice drilldown</button>
                <button className="btn secondary" onClick={() => setTab('events')} type="button">Back to event log</button>
              </div>
              <div className="grid two">
                <div>
                  <h3>Chain position</h3>
                  <pre>{JSON.stringify({ previous_hash: selected.previous_hash, hash: selected.hash }, null, 2)}</pre>
                </div>
                <div>
                  <h3>Event type</h3>
                  <pre>{selected.event_type}</pre>
                </div>
              </div>
              <h3 style={{ marginTop: 14 }}>Before</h3>
              <pre>{JSON.stringify(selected.before_json, null, 2)}</pre>
              <h3>After</h3>
              <pre>{JSON.stringify(selected.after_json, null, 2)}</pre>
            </>
          )}
        </article>
      ) : null}
    </>
  );
}

import { motion } from 'framer-motion';
import {
  CalendarDays,
  Car,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileText,
  Gauge,
  Hash,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Send,
  Sparkles,
  Truck,
  User,
} from 'lucide-react';
import { useState } from 'react';
import { apiPost } from '../api/client';
import { useApi } from '../api/useApi';
import { navigate } from '../router';
import {
  Claim,
  ClaimAttachment,
  DISPATCHABLE_SERVICES,
  IntakeTurn,
  SEVERITY_LABEL,
  WORKFLOW_LABEL,
  WorkOrder,
  gbp,
} from '../types';
import { Empty } from './Common';
import { PhotoGallery } from './PhotoGallery';

/** Two-letter monogram for the policyholder. */
function initials(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '—';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** How the claim reached us, as an icon plus a label rather than a bare code. */
function channelBadge(claim: Claim) {
  const isPortal = claim.origin === 'customer_portal';
  const Icon = isPortal ? Sparkles : claim.report_channel === 'phone' ? Phone : FileText;
  const label = isPortal ? 'Customer portal' : claim.report_channel.replace(/_/g, ' ');
  return (
    <span className={`chip${isPortal ? ' new' : ''}`}>
      <Icon size={12} /> {label}
    </span>
  );
}

/** Incident narrative, provenance and photographs for a claim. */
export function ClaimIncidentPanel({
  claim,
  photos,
  transcript,
}: {
  claim: Claim;
  photos: ClaimAttachment[];
  transcript: IntakeTurn[];
}) {
  const [showTranscript, setShowTranscript] = useState(false);

  return (
    <article className="card section">
      <div className="bentoCardHead">
        <h2>What happened</h2>
        <div className="btnRow">
          {channelBadge(claim)}
          <span className="chip">{SEVERITY_LABEL[claim.severity] ?? claim.severity}</span>
          <span className="chip">{WORKFLOW_LABEL[claim.workflow_status] ?? claim.workflow_status}</span>
        </div>
      </div>

      {/* Who the claim belongs to, and the two things a handler most often wants to do next. */}
      <div className="contactRow">
        <div className="contactCard person">
          <span className="contactAvatar">{initials(claim.customer_name)}</span>
          <div className="contactText">
            <b>{claim.customer_name || 'Policyholder not recorded'}</b>
            <small>{claim.insurance_number || 'No insurance number'}</small>
            <em>{claim.address || 'No address on file'}</em>
          </div>
        </div>

        <a
          aria-disabled={!claim.contact_number}
          className={`contactCard action${claim.contact_number ? '' : ' disabled'}`}
          href={claim.contact_number ? `tel:${claim.contact_number.replace(/\s+/g, '')}` : undefined}
        >
          <span className="contactIcon call">
            <Phone size={17} />
          </span>
          <div className="contactText">
            <b>Call customer</b>
            <small>{claim.contact_number || 'No number supplied'}</small>
          </div>
          <ChevronRight className="contactGo" size={15} />
        </a>

        <a
          aria-disabled={!claim.contact_email}
          className={`contactCard action${claim.contact_email ? '' : ' disabled'}`}
          href={
            claim.contact_email
              ? `mailto:${claim.contact_email}?subject=${encodeURIComponent(`Your claim ${claim.id}`)}`
              : undefined
          }
        >
          <span className="contactIcon mail">
            <Mail size={17} />
          </span>
          <div className="contactText">
            <b>Email customer</b>
            <small>{claim.contact_email || 'No email supplied'}</small>
          </div>
          <ChevronRight className="contactGo" size={15} />
        </a>
      </div>

      <p className="incidentStory">
        {claim.description || 'No incident narrative was recorded for this claim.'}
      </p>

      {/* The incident facts as small labelled tiles rather than a definition list. */}
      <div className="factGrid">
        {(
          [
            [Car, 'Incident', claim.incident_type.replace(/_/g, ' ')],
            [CalendarDays, 'When', claim.incident_date || 'not recorded'],
            [MapPin, 'Vehicle is', claim.incident_location || 'not recorded'],
            [Gauge, 'Drivable', claim.vehicle_drivable || 'not recorded'],
            [Hash, 'Registration', claim.vehicle_registration || 'not recorded'],
            [Clock, 'Reported', claim.reported_at ? claim.reported_at.replace('T', ' ').replace('Z', '') : 'not recorded'],
          ] as Array<[typeof Car, string, string]>
        ).map(([Icon, label, value]) => (
          <div className="factTile" key={label}>
            <span className="factIcon">
              <Icon size={14} />
            </span>
            <div>
              <span>{label}</span>
              <b>{value}</b>
            </div>
          </div>
        ))}
      </div>

      {claim.triage_summary ? (
        <p className="banner info" style={{ marginTop: 14 }}>
          <Sparkles size={15} /> {claim.triage_summary}
        </p>
      ) : null}

      {photos.length ? (
        <>
          <h3 style={{ marginTop: 16 }}>Incident photographs ({photos.length})</h3>
          <PhotoGallery photos={photos} />
        </>
      ) : (
        <Empty>No photographs were supplied with this claim.</Empty>
      )}

      {transcript.length ? (
        <>
          <button
            className="rateCardToggle"
            onClick={() => setShowTranscript((open) => !open)}
            style={{ marginTop: 16 }}
            type="button"
          >
            <MessageSquare size={13} />
            {showTranscript ? 'Hide' : 'Show'} the customer's conversation with Theo ({transcript.length} turns)
          </button>
          {showTranscript ? (
            <div className="chatLog" style={{ maxHeight: 360, padding: '14px 0 0' }}>
              {transcript.map((turn) => (
                <div className={`chatTurn ${turn.role === 'customer' ? 'user' : 'agent'}`} key={turn.id}>
                  <span className="chatPip">
                    {turn.role === 'customer' ? <User size={13} /> : <Sparkles size={13} />}
                  </span>
                  <div>
                    <div className="chatBubble" style={{ fontSize: 13 }}>
                      {turn.text}
                    </div>
                    {turn.reasoning.length ? (
                      <details className="chatReasoning">
                        <summary>Agent reasoning</summary>
                        <ul>
                          {turn.reasoning.map((line) => (
                            <li key={line}>{line}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

/** Supplier dispatch and the work-order board for one claim. */
export function ClaimWorkPanel({
  claim,
  onChanged,
  selectedSupplier,
  onSelectSupplier,
}: {
  claim: Claim;
  onChanged: () => void;
  /** Work order id currently focused, shared with the agent graph beside it. */
  selectedSupplier: string | null;
  onSelectSupplier: (workOrderId: string | null) => void;
}) {
  const orders = useApi<WorkOrder[]>(`/api/claims/${claim.id}/work-orders`);
  const [selected, setSelected] = useState<string[]>(claim.recommended_services);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const existing = new Set((orders.data ?? []).map((order) => order.service_type));
  const available = DISPATCHABLE_SERVICES.filter((service) => !existing.has(service.id));

  function toggle(service: string) {
    setSelected((current) =>
      current.includes(service) ? current.filter((item) => item !== service) : [...current, service],
    );
  }

  async function dispatch() {
    const services = selected.filter((service) => !existing.has(service));
    if (!services.length) {
      setError('Select at least one service that has not already been instructed.');
      return;
    }
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await apiPost<{ dispatched: WorkOrder[] }>(`/api/claims/${claim.id}/dispatch`, {
        services,
        actor_id: 'demo-user',
      });
      setNote(`Instructed ${result.dispatched.length} supplier${result.dispatched.length === 1 ? '' : 's'}.`);
      orders.reload();
      onChanged();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function advance(order: WorkOrder) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await apiPost<{ work_order: WorkOrder; invoice: Record<string, unknown> | null }>(
        `/api/work-orders/${order.id}/advance`,
        { actor_id: 'demo-user' },
      );
      const raised = result.invoice as { invoice?: { id?: string }; id?: string } | null;
      const invoiceId = raised?.invoice?.id ?? raised?.id;
      setNote(
        invoiceId
          ? `${order.supplier_name} invoiced — ${invoiceId} is now in the work queue.`
          : `${order.id} moved to ${result.work_order.status.replace(/_/g, ' ')}.`,
      );
      orders.reload();
      onChanged();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card section">
      <div className="bentoCardHead">
        <h2>Supplier work</h2>
        <span className="chip">{(orders.data ?? []).length} work orders</span>
      </div>

      {error ? <p className="banner bad">{error}</p> : null}
      {note ? <p className="banner ok">{note}</p> : null}

      {available.length ? (
        <>
          <p className="cardNote">
            Theo recommended <b>{claim.recommended_services.join(', ') || 'repair'}</b> from the incident and the
            photographs. Confirm or change what to instruct, then dispatch.
          </p>
          <div className="dispatchGrid">
            {available.map((service) => {
              const on = selected.includes(service.id);
              return (
                <button
                  className={`dispatchOption${on ? ' on' : ''}`}
                  key={service.id}
                  onClick={() => toggle(service.id)}
                  type="button"
                >
                  <b>
                    <Truck size={14} /> {service.label}
                    {on ? <CheckCircle2 className="tick" size={15} /> : null}
                  </b>
                  <small>{service.blurb}</small>
                </button>
              );
            })}
          </div>
          <button className="btn" disabled={busy} onClick={() => void dispatch()} type="button">
            <Send size={14} /> Instruct suppliers
          </button>
        </>
      ) : (
        <p className="cardNote">Every service on this claim has been instructed.</p>
      )}

      {orders.loading ? null : (orders.data ?? []).length === 0 ? (
        <Empty>No suppliers instructed yet.</Empty>
      ) : (
        <div className="woGrid stacked" style={{ marginTop: 16 }}>
          {(orders.data ?? []).map((order, index) => (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className={`woCard ${order.status}${selectedSupplier === order.id ? ' selected' : ''}`}
              initial={{ opacity: 0, y: 10 }}
              key={order.id}
              // Selecting a supplier focuses its lane in the agent graph beside this panel.
              onClick={() => onSelectSupplier(selectedSupplier === order.id ? null : order.id)}
              transition={{ delay: Math.min(index * 0.05, 0.3) }}
            >
              <div className="woCardTop">
                <div>
                  <b>{order.service_type.replace(/_/g, ' ')}</b>
                  <small>{order.supplier_name}</small>
                </div>
                <span className="chip">{order.status.replace(/_/g, ' ')}</span>
              </div>

              <div className="woSteps" title={order.stages.join(' → ')}>
                {order.stages.map((stage, position) => (
                  <i className={`woStepDot${position <= order.stage_index ? ' on' : ''}`} key={stage} />
                ))}
              </div>

              <div className="woMeta">
                <span>
                  {order.authorised_units} unit{order.authorised_units === 1 ? '' : 's'} authorised
                </span>
                <span>{gbp(order.authorised_value_gbp)}</span>
              </div>

              {/* These sit inside a selectable card, so their clicks must not also change the
                  selection. */}
              {order.invoice_id ? (
                <button
                  className="btn secondary small swimAction"
                  onClick={(event) => {
                    event.stopPropagation();
                    navigate(`/invoice/${order.invoice_id}`);
                  }}
                  type="button"
                >
                  <FileText size={13} /> View invoice <ChevronRight size={13} />
                </button>
              ) : (
                <button
                  className="btn small swimAction"
                  disabled={busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    void advance(order);
                  }}
                  type="button"
                >
                  {nextLabel(order)}
                </button>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </article>
  );
}

/** Label the button with the transition it will actually perform. */
function nextLabel(order: WorkOrder): string {
  const next = order.stages[order.stage_index + 1];
  const labels: Record<string, string> = {
    accepted: 'Mark accepted by supplier',
    in_progress: 'Mark work started',
    completed: 'Mark work complete',
    invoiced: 'Receive supplier invoice',
  };
  return labels[next] ?? 'Advance';
}

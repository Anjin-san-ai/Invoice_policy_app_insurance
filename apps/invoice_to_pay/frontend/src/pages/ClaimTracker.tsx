import { AnimatePresence, motion } from 'framer-motion';
import {
  BellRing,
  Camera,
  Check,
  CreditCard,
  Info,
  Loader2,
  Search,
  Truck,
  Wrench,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../api/client';
import { useApi } from '../api/useApi';
import { Empty, Loading } from '../components/Common';
import { PhotoGallery } from '../components/PhotoGallery';
import { MyClaimRow, SEVERITY_LABEL, TrackingState } from '../types';

/** Poll interval while a tracker is open, so a back-office change appears without a refresh. */
const POLL_MS = 6000;

const KIND_ICON: Record<string, typeof Info> = {
  info: Info,
  progress: Wrench,
  payment: CreditCard,
  action: BellRing,
};

/** Customer claim tracker: the customer's claims, then one claim's journey and updates. */
export function ClaimTracker({
  customerName,
  initialReference = '',
}: {
  customerName: string;
  initialReference?: string;
}) {
  const [reference, setReference] = useState(initialReference);
  const [state, setState] = useState<TrackingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seenNotifications, setSeenNotifications] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);
  const mine = useApi<MyClaimRow[]>(`/api/portal/my-claims?customer_name=${encodeURIComponent(customerName)}`);

  const load = useCallback(
    async (ref: string, quiet = false) => {
      if (!ref.trim()) return;
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        const result = await apiGet<TrackingState>(`/api/portal/track/${encodeURIComponent(ref.trim())}`);
        setState((previous) => {
          // A new notification arriving while the tab is open is the whole point of the tracker,
          // so it is announced rather than quietly appended.
          if (previous && result.notifications.length > previous.notifications.length) {
            setFlash(result.notifications[0]?.title ?? 'Your claim was updated');
            window.setTimeout(() => setFlash(null), 6000);
          }
          return result;
        });
      } catch (cause: unknown) {
        if (!quiet) setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [],
  );

  // Look up straight away when the portal hands us a reference it just created.
  useEffect(() => {
    if (initialReference) void load(initialReference);
  }, [initialReference, load]);

  // Keep it fresh while the tracker is on screen.
  useEffect(() => {
    if (!state) return;
    const id = window.setInterval(() => void load(state.claim.id, true), POLL_MS);
    return () => window.clearInterval(id);
  }, [state, load]);

  const unread = state ? Math.max(0, state.notifications.length - seenNotifications) : 0;

  return (
    <section>
      {/* The customer's own claims, so nobody has to remember a reference. */}
      <div className="trackLookup">
        <div className="bentoCardHead">
          <h2 style={{ margin: 0 }}>Your claims</h2>
          <span className="chip">{(mine.data ?? []).length}</span>
        </div>
        {mine.loading ? (
          <Loading rows={2} />
        ) : (mine.data ?? []).length === 0 ? (
          <Empty>You have no claims with us yet.</Empty>
        ) : (
          <div className="myClaims">
            {(mine.data ?? []).map((row, index) => (
              <motion.button
                animate={{ opacity: 1, y: 0 }}
                className={`myClaim${state?.claim.id === row.claim_id ? ' on' : ''}`}
                initial={{ opacity: 0, y: 8 }}
                key={row.claim_id}
                onClick={() => {
                  setReference(row.claim_id);
                  void load(row.claim_id);
                }}
                transition={{ delay: Math.min(index * 0.05, 0.3) }}
                type="button"
              >
                <div className="myClaimTop">
                  <b className="mono">{row.claim_id}</b>
                  {row.update_count > 0 ? (
                    <span className="chip new">
                      <BellRing size={11} /> {row.update_count}
                    </span>
                  ) : null}
                </div>
                <span className="myClaimWhat">
                  {row.incident_type.replace(/_/g, ' ')} · {row.incident_date}
                </span>
                <span className="myClaimWhere">
                  {row.vehicle_registration || 'vehicle not recorded'}
                  {row.incident_location ? ` · ${row.incident_location}` : ''}
                </span>
                <div className="myClaimBar">
                  <motion.i
                    animate={{ width: `${row.percent_complete}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                  />
                </div>
                <span className="myClaimStage">
                  {row.stage_title}
                  {row.photo_count ? ` · ${row.photo_count} photos` : ''}
                </span>
              </motion.button>
            ))}
          </div>
        )}

        <details className="trackByRef">
          <summary>Or look up a claim by reference</summary>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void load(reference);
            }}
            style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 10 }}
          >
            <input
              aria-label="Claim reference"
              className="field"
              onChange={(event) => setReference(event.target.value)}
              placeholder="CLM-00002"
              style={{ maxWidth: 240 }}
              value={reference}
            />
            <button className="btn" disabled={busy || !reference.trim()} type="submit">
              {busy ? <Loader2 className="spin" size={15} /> : <Search size={15} />} Track
            </button>
          </form>
        </details>
        {error ? <p className="banner bad" style={{ marginTop: 14 }}>{error}</p> : null}
      </div>

      <AnimatePresence>
        {flash ? (
          <motion.p
            animate={{ opacity: 1, y: 0 }}
            className="banner ok trackFlash"
            exit={{ opacity: 0, y: -8 }}
            initial={{ opacity: 0, y: -8 }}
          >
            <BellRing size={16} /> Update: {flash}
          </motion.p>
        ) : null}
      </AnimatePresence>

      {state ? (
        <>
          {/* -------------------------------------------------- headline */}
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="trackHead"
            initial={{ opacity: 0, y: 12 }}
          >
            <div>
              <p className="heroEyebrow" style={{ margin: '0 0 8px' }}>
                Claim {state.claim.id}
              </p>
              <h1 style={{ fontSize: 30, margin: '0 0 6px' }}>
                {state.steps.find((step) => step.state === 'current')?.title ?? 'Claim settled'}
              </h1>
              <p className="cardNote" style={{ margin: 0 }}>
                {state.claim.incident_type.replace(/_/g, ' ')} on {state.claim.incident_date} ·{' '}
                {SEVERITY_LABEL[state.claim.severity] ?? state.claim.severity} · vehicle{' '}
                {state.claim.vehicle_registration || 'not recorded'}
              </p>
            </div>
            <div className="trackRing">
              <svg height="112" viewBox="0 0 112 112" width="112">
                <circle cx="56" cy="56" fill="none" r="48" stroke="var(--border-light)" strokeWidth="10" />
                <motion.circle
                  animate={{ strokeDashoffset: 301.6 - (301.6 * state.percent_complete) / 100 }}
                  cx="56"
                  cy="56"
                  fill="none"
                  initial={{ strokeDashoffset: 301.6 }}
                  r="48"
                  stroke="var(--primary)"
                  strokeDasharray="301.6"
                  strokeLinecap="round"
                  strokeWidth="10"
                  transform="rotate(-90 56 56)"
                  transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
                />
              </svg>
              <div className="trackRingLabel">
                <b>{state.percent_complete}%</b>
                <small>
                  {state.completed_steps} of {state.total_steps}
                </small>
              </div>
            </div>
          </motion.div>

          <div className="grid two section">
            {/* ---------------------------------------------- journey */}
            <article className="card">
              <h2>Your claim journey</h2>
              <ol className="journey">
                {state.steps.map((step, index) => (
                  <motion.li
                    animate={{ opacity: 1, x: 0 }}
                    className={`journeyStep ${step.state}`}
                    initial={{ opacity: 0, x: -10 }}
                    key={step.id}
                    transition={{ delay: Math.min(index * 0.07, 0.5) }}
                  >
                    <span className="journeyTick">
                      {step.state === 'done' ? (
                        <motion.span
                          animate={{ scale: 1, opacity: 1 }}
                          initial={{ scale: 0.2, opacity: 0 }}
                          transition={{ delay: Math.min(index * 0.07, 0.5) + 0.12, type: 'spring', stiffness: 420 }}
                        >
                          <Check size={14} strokeWidth={3.4} />
                        </motion.span>
                      ) : step.state === 'current' ? (
                        <motion.i
                          animate={{ scale: [1, 1.45, 1], opacity: [1, 0.55, 1] }}
                          transition={{ duration: 1.5, repeat: Infinity }}
                        />
                      ) : (
                        <i />
                      )}
                    </span>
                    <div>
                      <b>{step.title}</b>
                      <small>{step.blurb}</small>
                      {step.at ? <em className="journeyAt">{step.at}</em> : null}
                    </div>
                  </motion.li>
                ))}
              </ol>
            </article>

            {/* ---------------------------------------------- notifications */}
            <article className="card">
              <div className="bentoCardHead">
                <h2>Updates</h2>
                {unread > 0 ? (
                  <button
                    className="chip new"
                    onClick={() => setSeenNotifications(state.notifications.length)}
                    type="button"
                  >
                    <BellRing size={12} /> {unread} new
                  </button>
                ) : null}
              </div>
              {state.notifications.length === 0 ? (
                <Empty>No updates yet. We will post here as your claim progresses.</Empty>
              ) : (
                <div className="noteFeed">
                  <AnimatePresence initial={false}>
                    {state.notifications.map((note, index) => {
                      const Icon = KIND_ICON[note.kind] ?? Info;
                      return (
                        <motion.div
                          animate={{ opacity: 1, y: 0 }}
                          className={`noteItem ${note.kind}${index < unread ? ' fresh' : ''}`}
                          initial={{ opacity: 0, y: -8 }}
                          key={note.id}
                          transition={{ duration: 0.25 }}
                        >
                          <span className="noteIcon">
                            <Icon size={14} />
                          </span>
                          <div>
                            <b>{note.title}</b>
                            <small>{note.body}</small>
                            <em className="journeyAt">{note.at}</em>
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              )}
            </article>
          </div>

          {/* ---------------------------------------------- suppliers + photos */}
          {state.work_orders.length ? (
            <article className="card section">
              <h2>Who is working on your vehicle</h2>
              <div className="woGrid">
                {state.work_orders.map((order) => (
                  <div className={`woCard ${order.status}`} key={order.id}>
                    <div className="woCardTop">
                      <div>
                        <b>{order.service_type.replace(/_/g, ' ')}</b>
                        <small>{order.supplier_name}</small>
                      </div>
                      <span className="chip">
                        <Truck size={11} /> {order.status.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="woSteps">
                      {[0, 1, 2, 3, 4].map((position) => (
                        <i className={`woStepDot${position <= order.stage_index ? ' on' : ''}`} key={position} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ) : null}

          {state.attachments.length ? (
            <article className="card section">
              <h2>
                <Camera size={15} style={{ verticalAlign: '-2px' }} /> Photographs you sent
              </h2>
              <PhotoGallery photos={state.attachments} />
            </article>
          ) : null}

          <p className="cardNote" style={{ textAlign: 'center' }}>
            We settle the suppliers directly — there is nothing for you to pay beyond your policy excess.
          </p>
        </>
      ) : null}
    </section>
  );
}

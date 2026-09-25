import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, ArrowRight, Ban, CheckCircle2, ChevronRight, Lock, ShieldCheck, Stamp } from 'lucide-react';
import { useState } from 'react';
import { apiPost } from '../api/client';
import { useApi } from '../api/useApi';
import { StatChip } from '../charts/Visuals';
import { Empty, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { navigate } from '../router';
import { PaymentBoard, PaymentBoardItem, gbp } from '../types';

/* Two identities so the two-person control is demonstrable end to end: authorise as one, then try
   to release as that same one (spec 13.8, TC-11). */
const ACTORS = ['analyst-alice', 'lead-ben'] as const;

const LANE_ICON: Record<string, typeof Stamp> = {
  authorise: Stamp,
  release: ShieldCheck,
  released: CheckCircle2,
  blocked: Ban,
};

type Outcome = { kind: 'ok' | 'blocked' | 'conflict' | 'error'; text: string };

export function Approvals() {
  const board = useApi<PaymentBoard>('/api/payments/board?limit_per_lane=40');
  const [actor, setActor] = useState<string>(ACTORS[0]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState('');

  async function authorise(item: PaymentBoardItem) {
    setBusy(item.invoice_id);
    setOutcome(null);
    try {
      await apiPost(`/api/invoices/${item.invoice_id}/approve`, { actor_id: actor });
      setOutcome({
        kind: 'ok',
        text: `${actor} authorised ${item.invoice_number}. It has moved to Awaiting release, where a different identity must release it.`,
      });
      board.reload();
    } catch (cause) {
      setOutcome({ kind: 'error', text: `Authorise failed: ${cause instanceof Error ? cause.message : String(cause)}` });
    } finally {
      setBusy('');
    }
  }

  async function release(item: PaymentBoardItem) {
    if (!item.payment_id) return;
    setBusy(item.invoice_id);
    setOutcome(null);
    try {
      const result = await apiPost<{ path: string; reference: string; ice_writeback_status: string }>(
        `/api/payments/${item.payment_id}/release`,
        { actor_id: actor },
      );
      setOutcome({
        kind: 'ok',
        text: `${item.payment_id} released by ${actor} via the ${result.path} route. Invoice write-back ${result.ice_writeback_status}, reference ${result.reference}.`,
      });
      board.reload();
    } catch (cause) {
      const text = cause instanceof Error ? cause.message : String(cause);
      if (text.includes('Segregation')) {
        setOutcome({
          kind: 'blocked',
          text: `Blocked by segregation of duties. ${actor} authorised ${item.payment_id} and cannot also release it. The rejection is written to the audit log. Switch the acting identity and try again.`,
        });
      } else if (text.includes('already released')) {
        setOutcome({ kind: 'conflict', text: `${item.payment_id} was already released. Re-releasing is refused so the supplier is never paid twice.` });
      } else {
        setOutcome({ kind: 'error', text: `Release failed: ${text}` });
      }
      board.reload();
    } finally {
      setBusy('');
    }
  }

  if (board.loading) return <Loading rows={5} />;
  if (board.error) return <Empty>Could not load the payment board: {board.error}</Empty>;
  if (!board.data) return <Empty>No payment data.</Empty>;

  const lanes = board.data.lanes;
  const chipClass = outcome?.kind === 'ok' ? 'within' : outcome?.kind === 'error' ? 'outside' : 'warn';

  return (
    <>
      <PageHead
        eyebrow="Finance team lead"
        title="Approvals and payments"
        sub="Work flows left to right. Nothing can cross from Awaiting release to Released without a second identity, and that is enforced in the API, not just in this screen."
        actions={
          <select
            aria-label="Acting identity"
            onChange={(event) => setActor(event.target.value)}
            style={{ padding: '10px 16px', borderRadius: 999, border: '1px solid var(--border)', fontWeight: 700, background: 'var(--surface)', color: 'var(--text)' }}
            value={actor}
          >
            {ACTORS.map((value) => (
              <option key={value} value={value}>Acting as {value}</option>
            ))}
          </select>
        }
      />

      <section className="chipRow section">
        {lanes.map((lane) => (
          <StatChip
            key={lane.key}
            label={lane.title}
            tone={lane.key === 'blocked' ? 'bad' : lane.key === 'released' ? 'ok' : lane.count ? 'warn' : undefined}
            value={`${lane.count.toLocaleString('en-GB')} · ${gbp(lane.value_gbp)}`}
          />
        ))}
        <StatChip label="Threshold" value={gbp(board.data.high_value_threshold_gbp)} />
      </section>

      <AnimatePresence>
        {outcome ? (
          <motion.p
            animate={{ opacity: 1, height: 'auto' }}
            className={`banner ${chipClass === 'within' ? 'ok' : chipClass === 'outside' ? 'bad' : 'warn'}`}
            exit={{ opacity: 0, height: 0 }}
            initial={{ opacity: 0, height: 0 }}
          >
            {outcome.kind === 'ok' ? <CheckCircle2 size={16} /> : outcome.kind === 'blocked' ? <Lock size={16} /> : <AlertTriangle size={16} />}
            {outcome.text}
          </motion.p>
        ) : null}
      </AnimatePresence>

      <div className="swimHeader">
        {lanes.map((lane, index) => (
          <div className="swimHeaderItem" key={lane.key}>
            <span className={`swimStep ${lane.key}`}>{index + 1}</span>
            <span>{lane.title}</span>
            {index < lanes.length - 1 ? <ArrowRight className="swimArrow" size={15} /> : null}
          </div>
        ))}
      </div>

      <div className="swimBoard">
        {lanes.map((lane, laneIndex) => {
          const Icon = LANE_ICON[lane.key] ?? Stamp;
          return (
            <motion.section
              animate={{ opacity: 1, y: 0 }}
              className={`swimLane ${lane.key}`}
              initial={{ opacity: 0, y: 16 }}
              key={lane.key}
              transition={{ delay: laneIndex * 0.08 }}
            >
              <header className="swimLaneHead">
                <h3><Icon size={14} /> {lane.title}</h3>
                <span className="swimCount">{lane.count.toLocaleString('en-GB')}</span>
              </header>
              <p className="swimLaneSub">{lane.description}</p>
              <p className="swimLaneValue">{gbp(lane.value_gbp)}</p>

              <div className="swimLaneBody">
                {lane.items.length === 0 ? (
                  <p className="swimEmpty">
                    {lane.key === 'release'
                      ? 'Nothing awaiting release. Authorise an item in the first lane and it will appear here.'
                      : 'Nothing in this lane.'}
                  </p>
                ) : (
                  <AnimatePresence initial={false}>
                    {lane.items.map((item, index) => {
                      const wouldBreach = item.authorised_by === actor;
                      return (
                        <motion.article
                          animate={{ opacity: 1, x: 0 }}
                          className="swimCard"
                          exit={{ opacity: 0, x: 24 }}
                          initial={{ opacity: 0, x: -14 }}
                          key={item.invoice_id}
                          layout
                          transition={{ delay: Math.min(index * 0.035, 0.4) }}
                        >
                          <div className="swimCardTop">
                            <button className="swimCardId" onClick={() => navigate(`/invoice/${item.invoice_id}`)} type="button">
                              {item.invoice_number} <ChevronRight size={12} />
                            </button>
                            <b>{gbp(item.amount_gbp)}</b>
                          </div>
                          <p className="swimCardSupplier">{item.supplier_name}</p>
                          <div className="swimCardTags">
                            <span className="chip">{item.path}</span>
                            {item.above_threshold ? <span className="chip warn">over threshold</span> : null}
                            {item.claim_id ? (
                              <button className="chip linkChip" onClick={() => navigate(`/claim/${item.claim_id}`)} type="button">
                                {item.claim_id}
                              </button>
                            ) : null}
                          </div>
                          <p className="swimCardReason">{item.reason}</p>

                          {lane.key === 'release' || lane.key === 'released' ? (
                            <dl className="swimCardDuties">
                              <div>
                                <dt>authorised</dt>
                                <dd className="mono">{item.authorised_by ?? '—'}</dd>
                              </div>
                              <div>
                                <dt>released</dt>
                                <dd className="mono">{item.released_by ?? 'pending'}</dd>
                              </div>
                            </dl>
                          ) : null}

                          {lane.key === 'authorise' ? (
                            <button className="btn swimAction" disabled={busy === item.invoice_id} onClick={() => authorise(item)} type="button">
                              {busy === item.invoice_id ? 'Authorising…' : `Authorise as ${actor}`}
                            </button>
                          ) : null}

                          {lane.key === 'release' ? (
                            <button
                              className="btn swimAction"
                              disabled={busy === item.invoice_id}
                              onClick={() => release(item)}
                              style={wouldBreach ? { background: 'var(--warning)' } : undefined}
                              title={wouldBreach ? `${actor} authorised this payment, so releasing it will be blocked` : `Release as ${actor}`}
                              type="button"
                            >
                              {busy === item.invoice_id ? 'Releasing…' : wouldBreach ? 'Release (will block)' : `Release as ${actor}`}
                            </button>
                          ) : null}

                          {lane.key === 'released' ? (
                            <p className="swimCardSettled">
                              <CheckCircle2 size={12} /> {item.ice_writeback_status} · <span className="mono">{item.reference}</span>
                            </p>
                          ) : null}

                          {lane.key === 'blocked' ? (
                            <p className="swimCardBlocked"><Ban size={12} /> never paid</p>
                          ) : null}
                        </motion.article>
                      );
                    })}
                  </AnimatePresence>
                )}
                {lane.truncated > 0 ? <p className="swimEmpty">+{lane.truncated.toLocaleString('en-GB')} more in this lane</p> : null}
              </div>
            </motion.section>
          );
        })}
      </div>

      <p className="cardNote" style={{ marginTop: 16 }}>
        To see the control fire: authorise an item as <strong>{actor}</strong>, then try to release it while still acting as{' '}
        <strong>{actor}</strong>. The API returns 403 and audits the attempt. Switch identity and the same release succeeds.
      </p>
    </>
  );
}

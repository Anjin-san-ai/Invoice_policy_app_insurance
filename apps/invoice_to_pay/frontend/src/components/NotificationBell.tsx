import { AnimatePresence, motion } from 'framer-motion';
import { Bell, BellRing, CreditCard, Info, Wrench, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from '../api/client';
import { ClaimNotification } from '../types';

/** How often the portal asks whether the back office has moved the claim on. */
const POLL_MS = 5000;

const KIND_ICON: Record<string, typeof Info> = {
  info: Info,
  progress: Wrench,
  payment: CreditCard,
  action: BellRing,
};

/**
 * Poll one claim's notification feed.
 *
 * The prototype has no push channel to a browser, so the portal pulls. It is deliberately a short
 * interval: at a booth, the gap between a handler clicking "work started" and the customer screen
 * reacting is the thing people are watching for.
 */
export function useClaimNotifications(claimId: string | null) {
  const [items, setItems] = useState<ClaimNotification[]>([]);
  const [latest, setLatest] = useState<ClaimNotification | null>(null);
  const seenIds = useRef<Set<string>>(new Set());
  const primed = useRef(false);

  const poll = useCallback(async (id: string) => {
    try {
      const result = await apiGet<ClaimNotification[]>(`/api/portal/claims/${id}/notifications`);
      setItems(result);
      const fresh = result.filter((item) => !seenIds.current.has(item.id));
      result.forEach((item) => seenIds.current.add(item.id));
      // The first poll after opening a claim is priming, not news: announcing the whole backlog
      // as new would fire a toast for history the customer has already seen.
      if (primed.current && fresh.length) setLatest(fresh[0]);
      primed.current = true;
    } catch {
      // A failed poll is not worth surfacing; the next one will pick the feed up.
    }
  }, []);

  useEffect(() => {
    if (!claimId) return;
    seenIds.current = new Set();
    primed.current = false;
    void poll(claimId);
    const timer = window.setInterval(() => void poll(claimId), POLL_MS);
    return () => window.clearInterval(timer);
  }, [claimId, poll]);

  return { items, latest, dismissLatest: () => setLatest(null) };
}

/** Header bell with an unread count and a dropdown of the claim's updates. */
export function NotificationBell({
  items,
  unread,
  onOpen,
}: {
  items: ClaimNotification[];
  unread: number;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bellWrap">
      <button
        aria-label={`Updates${unread ? `, ${unread} new` : ''}`}
        className={`bellBtn${unread ? ' hot' : ''}`}
        onClick={() => {
          setOpen((current) => !current);
          if (!open) onOpen();
        }}
        type="button"
      >
        {unread ? <BellRing size={17} /> : <Bell size={17} />}
        {unread ? (
          <motion.span animate={{ scale: 1 }} className="bellCount" initial={{ scale: 0.3 }} key={unread}>
            {unread}
          </motion.span>
        ) : null}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="bellPanel"
            exit={{ opacity: 0, y: -6 }}
            initial={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16 }}
          >
            <div className="bellPanelHead">
              <b>Your claim updates</b>
              <button aria-label="Close" onClick={() => setOpen(false)} type="button">
                <X size={14} />
              </button>
            </div>
            {items.length === 0 ? (
              <p className="searchEmpty">No updates yet.</p>
            ) : (
              items.map((item) => {
                const Icon = KIND_ICON[item.kind] ?? Info;
                return (
                  <div className={`noteItem ${item.kind}`} key={item.id}>
                    <span className="noteIcon">
                      <Icon size={13} />
                    </span>
                    <div>
                      <b>{item.title}</b>
                      <small>{item.body}</small>
                    </div>
                  </div>
                );
              })
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

/** Corner toast announcing one new update. */
export function NotificationToast({
  note,
  onDismiss,
}: {
  note: ClaimNotification | null;
  onDismiss: () => void;
}) {
  useEffect(() => {
    if (!note) return;
    const timer = window.setTimeout(onDismiss, 7000);
    return () => window.clearTimeout(timer);
  }, [note, onDismiss]);

  const Icon = note ? (KIND_ICON[note.kind] ?? Info) : Info;

  return (
    <AnimatePresence>
      {note ? (
        <motion.div
          animate={{ opacity: 1, y: 0, scale: 1 }}
          className={`toast ${note.kind}`}
          exit={{ opacity: 0, y: 20, scale: 0.96 }}
          initial={{ opacity: 0, y: 24, scale: 0.96 }}
          transition={{ type: 'spring', stiffness: 380, damping: 30 }}
        >
          <span className="toastIcon">
            <Icon size={17} />
          </span>
          <div>
            <b>{note.title}</b>
            <small>{note.body}</small>
          </div>
          <button aria-label="Dismiss" className="toastClose" onClick={onDismiss} type="button">
            <X size={14} />
          </button>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  CheckCircle2,
  Copy,
  ImagePlus,
  LogOut,
  Plus,
  Radar,
  Send,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react';
import { ChangeEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react';
import { apiPost } from '../api/client';
import { Empty } from '../components/Common';
import { AgentMood, EmotingAgent } from '../components/EmotingAgent';
import { MuteButton } from '../components/MuteButton';
import {
  NotificationBell,
  NotificationToast,
  useClaimNotifications,
} from '../components/NotificationBell';
import { PhotoGallery } from '../components/PhotoGallery';
import { ThemeToggle } from '../components/ThemeToggle';
import { useSpeech } from '../theme/useSpeech';
import { CustomerProfile, IntakeState, SEVERITY_LABEL } from '../types';
import { ClaimTracker } from './ClaimTracker';
import { PortalLogin } from './PortalLogin';

const MAX_IMAGE_BYTES = 6 * 1024 * 1024;

/** Customer self-service portal. Runs outside the back-office shell: no sidebar, no modules. */
export function Portal() {
  const [profile, setProfile] = useState<CustomerProfile | null>(readSession);
  const [tab, setTab] = useState<'new' | 'track'>('new');
  const [trackRef, setTrackRef] = useState('');
  const [state, setState] = useState<IntakeState | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [mood, setMood] = useState<AgentMood>('idle');
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [seen, setSeen] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const speech = useSpeech();

  // Watch whichever claim the customer has in play: the one they just submitted, or the one they
  // looked up on the tracking tab. A draft has nothing to notify about yet.
  const watchedClaim = state?.submitted && state.claim.workflow_status !== 'draft' ? state.claim.id : trackRef || null;
  const notifications = useClaimNotifications(watchedClaim);
  const unread = Math.max(0, notifications.items.length - seen);

  /** Open a fresh draft claim for the signed-in policyholder. */
  const openDraft = useCallback(async (who: CustomerProfile) => {
    setError(null);
    setState(null);
    setDraft('');
    setMood('idle');
    try {
      setState(await apiPost<IntakeState>('/api/portal/claims', who));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  // Theo greets the customer as soon as they are signed in, already knowing who they are.
  useEffect(() => {
    if (profile && state === null && !error) void openDraft(profile);
  }, [profile, state, error, openDraft]);

  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' });
  }, [state?.turns.length, mood]);

  // Speak whatever Theo just said, including his opening introduction. Driven off the transcript
  // rather than the send handler, so the greeting that arrives with the draft is read out too.
  // The ref guards against re-speaking the same turn when the component re-renders.
  const spokenTurn = useRef('');
  useEffect(() => {
    const last = state?.turns[state.turns.length - 1];
    if (!last || last.role !== 'assistant' || spokenTurn.current === last.id) return;
    spokenTurn.current = last.id;
    speech.speak(last.text);
  }, [state?.turns, speech]);

  /** Drop back to idle after a reaction has played. */
  const settle = useCallback((next: AgentMood = 'idle', after = 1500) => {
    window.setTimeout(() => setMood((current) => (current === 'idle' ? current : next)), after);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const claimId = state?.claim.id;
      if (!claimId || !text.trim() || busy) return;
      setBusy(true);
      setError(null);
      setDraft('');
      setMood('thinking');
      const before = state?.missing_slots.length ?? 0;
      try {
        const result = await apiPost<IntakeState>(`/api/portal/claims/${claimId}/messages`, { text });
        setState(result);
        // Pleased when a question got answered, sympathetic on a serious incident.
        const progressed = result.missing_slots.length < before;
        const serious = result.claim.severity === 'major' || result.claim.severity === 'total_loss';
        setMood(result.ready_to_submit ? 'approving' : progressed ? (serious ? 'concerned' : 'happy') : 'idle');
        settle('idle', 1800);
      } catch (cause: unknown) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setMood('concerned');
        settle('idle', 2000);
      } finally {
        setBusy(false);
      }
    },
    [busy, settle, state],
  );

  const upload = useCallback(
    async (files: FileList | null) => {
      const claimId = state?.claim.id;
      if (!claimId || !files || !files.length) return;
      setBusy(true);
      setError(null);
      setMood('thinking');
      try {
        for (const file of Array.from(files)) {
          if (file.size > MAX_IMAGE_BYTES) {
            setError(`${file.name} is larger than 6 MB`);
            continue;
          }
          const dataUri = await readAsDataUri(file);
          const result = await apiPost<IntakeState>(`/api/portal/claims/${claimId}/attachments`, {
            label: file.name.replace(/\.[^.]+$/, ''),
            content_type: file.type,
            data_uri: dataUri,
          });
          setState(result);
        }
        setMood('happy');
        settle('idle', 1600);
      } catch (cause: unknown) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setMood('idle');
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [settle, state],
  );

  async function submit() {
    const claimId = state?.claim.id;
    if (!claimId) return;
    setBusy(true);
    setError(null);
    setMood('thinking');
    try {
      const result = await apiPost<IntakeState>(`/api/portal/claims/${claimId}/submit`, {});
      setState(result);
      setTrackRef(result.claim.id);
      setMood('celebrating');
      settle('happy', 2600);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setMood('concerned');
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void send(draft);
    }
  }

  function onType(event: ChangeEvent<HTMLTextAreaElement>) {
    setDraft(event.target.value);
    // Theo leans in while the customer is typing, and relaxes when the box is emptied.
    if (event.target.value.trim() && mood !== 'listening' && !busy) setMood('listening');
    if (!event.target.value.trim() && mood === 'listening') setMood('idle');
  }

  const submitted = Boolean(state?.submitted && state.claim.workflow_status !== 'draft');

  function signIn(who: CustomerProfile) {
    setProfile(who);
    writeSession(who);
    setTab('new');
    void openDraft(who);
  }

  function signOut() {
    setProfile(null);
    writeSession(null);
    setState(null);
    setTrackRef('');
    setTab('new');
  }

  if (!profile) {
    return (
      <div className="portal">
        <header className="portalBar">
          <div className="portalBrand">
            <span className="portalMark">
              <ShieldCheck size={20} />
            </span>
            <div>
              <b>Cognizant Motor Claims</b>
              <small>Report and track a claim in minutes</small>
            </div>
          </div>
          <ThemeToggle />
        </header>
        <div className="portalBody">
          <PortalLogin onSignIn={signIn} />
        </div>
      </div>
    );
  }

  return (
    <div className="portal">
      <header className="portalBar">
        <div className="portalBrand">
          <span className="portalMark">
            <ShieldCheck size={20} />
          </span>
          <div>
            <b>Cognizant Motor Claims</b>
            <small>Report and track a claim in minutes</small>
          </div>
        </div>
        <div className="portalTabs">
          <button className={`portalTab${tab === 'new' ? ' on' : ''}`} onClick={() => setTab('new')} type="button">
            <Sparkles size={14} /> New claim
          </button>
          <button className={`portalTab${tab === 'track' ? ' on' : ''}`} onClick={() => setTab('track')} type="button">
            <Radar size={14} /> Track a claim
          </button>
        </div>
        {/* Customer-facing only: no staff entry point is advertised here. Staff reach the back
            office from their own shell, or directly at #/dashboard. */}
        <div className="btnRow">
          {watchedClaim ? (
            <NotificationBell
              items={notifications.items}
              onOpen={() => setSeen(notifications.items.length)}
              unread={unread}
            />
          ) : null}
          <MuteButton
            muted={speech.muted}
            onToggle={speech.toggleMute}
            speaking={speech.speaking}
            supported={speech.supported}
          />
          <ThemeToggle />
          <button className="whoami" onClick={signOut} title="Sign out" type="button">
            <span className="whoamiInitials">{initials(profile.customer_name)}</span>
            <span className="whoamiName">{profile.customer_name}</span>
            <LogOut size={13} />
          </button>
        </div>
      </header>

      {/* A back-office change shows up here wherever the customer is in the portal. */}
      <NotificationToast note={notifications.latest} onDismiss={notifications.dismissLatest} />

      <div className="portalBody">
        <AnimatePresence mode="wait">
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            initial={{ opacity: 0, y: 12 }}
            key={tab}
            transition={{ duration: 0.22 }}
          >
            {tab === 'track' ? (
              <ClaimTracker customerName={profile.customer_name} initialReference={trackRef} />
            ) : submitted ? (
              <Receipt
                onNewClaim={() => void openDraft(profile)}
                onTrack={() => setTab('track')}
                state={state as IntakeState}
                copied={copied}
                onCopy={() => {
                  void navigator.clipboard?.writeText((state as IntakeState).claim.id);
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 2000);
                }}
              />
            ) : (
              <>
                {error ? <p className="banner bad">{error}</p> : null}
                {state === null ? (
                  <Empty>Connecting you to the claims assistant…</Empty>
                ) : (
                  <>
                    {/* Bot centre stage, conversation alongside. Stacks to bot-then-chat on a
                        phone so the same markup works inside a mobile app webview. */}
                    <section className="portalStage">
                      <div className="stageBot">
                        <EmotingAgent mood={mood} size={300} variant="full" />
                        <h1 className="stageTitle">
                          Hi, I'm <em>Theo</em>
                        </h1>
                        <p className="stageBlurb">
                          {state.ready_to_submit
                            ? "That's everything I need — add photos, then submit."
                            : 'Answer as you would in a text message and I will do the rest.'}
                        </p>
                        <div className="stageMeter">
                          <div className="chatProgress" title="How much Theo still needs">
                            <motion.i
                              animate={{ width: `${Math.round(((9 - state.missing_slots.length) / 9) * 100)}%` }}
                              transition={{ duration: 0.5, ease: 'easeOut' }}
                            />
                          </div>
                          <small>
                            {state.ready_to_submit
                              ? 'All questions answered'
                              : `${state.missing_slots.length} question${state.missing_slots.length === 1 ? '' : 's'} to go`}
                          </small>
                        </div>
                      </div>

                      <article className="chatCard stageChat">
                      <div className="chatHead">
                        <EmotingAgent mood={mood} showMood={false} size={44} />
                        <div>
                          <b>Theo · Claims assistant</b>
                          <small>
                            {state.ready_to_submit ? 'Ready to submit your claim' : 'Online now'}
                          </small>
                        </div>
                      </div>

                      <div className="chatLog" ref={logRef}>
                        <AnimatePresence initial={false}>
                          {state.turns.map((turn) => (
                            <motion.div
                              animate={{ opacity: 1, y: 0 }}
                              className={`chatTurn ${turn.role === 'customer' ? 'user' : 'agent'}`}
                              initial={{ opacity: 0, y: 10 }}
                              key={turn.id}
                              transition={{ duration: 0.22 }}
                            >
                              <span className="chatPip">
                                {turn.role === 'customer' ? <User size={14} /> : <Sparkles size={14} />}
                              </span>
                              <div>
                                <div className="chatBubble">{turn.text}</div>
                                {turn.reasoning.length ? (
                                  <details className="chatReasoning">
                                    <summary>How Theo read that</summary>
                                    <ul>
                                      {turn.reasoning.map((line) => (
                                        <li key={line}>{line}</li>
                                      ))}
                                    </ul>
                                  </details>
                                ) : null}
                              </div>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                        {mood === 'thinking' ? (
                          <div className="chatTurn agent">
                            <span className="chatPip">
                              <Sparkles size={14} />
                            </span>
                            <div className="chatBubble chatTyping">
                              <i />
                              <i />
                              <i />
                            </div>
                          </div>
                        ) : null}
                      </div>

                      {/* Uploads live in the conversation, as a strip above the composer. */}
                      {state.attachments.length ? (
                        <div className="chatPhotos">
                          {state.attachments.map((photo) => (
                            <span className="chatPhotoThumb" key={photo.id}>
                              <img alt={photo.label} src={photo.data_uri} />
                            </span>
                          ))}
                          <small>
                            {state.attachments.length} photo{state.attachments.length === 1 ? '' : 's'} attached
                          </small>
                        </div>
                      ) : null}

                      {state.quick_replies.length ? (
                        <div className="chatQuick">
                          {state.quick_replies.map((reply) => (
                            <button
                              className="chatQuickChip"
                              disabled={busy}
                              key={reply}
                              onClick={() => void send(reply)}
                              type="button"
                            >
                              {reply}
                            </button>
                          ))}
                        </div>
                      ) : null}

                      <div className="chatComposer">
                        <button
                          aria-label="Add photographs"
                          className="chatAttach"
                          onClick={() => fileRef.current?.click()}
                          type="button"
                        >
                          <ImagePlus size={18} />
                        </button>
                        <textarea
                          onChange={onType}
                          onKeyDown={onKeyDown}
                          placeholder="Type your answer, or tap a suggestion…"
                          value={draft}
                        />
                        <button
                          aria-label="Send"
                          className="chatSend"
                          disabled={busy || !draft.trim()}
                          onClick={() => void send(draft)}
                          type="button"
                        >
                          <Send size={17} />
                        </button>
                      </div>
                      </article>
                    </section>

                    <input
                      accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
                      hidden
                      multiple
                      onChange={(event) => void upload(event.target.files)}
                      ref={fileRef}
                      type="file"
                    />

                    {state.ready_to_submit ? (
                      <motion.div
                        animate={{ opacity: 1, y: 0 }}
                        className="card section submitCard"
                        initial={{ opacity: 0, y: 12 }}
                        style={{ marginTop: 18 }}
                      >
                        <h2>Ready when you are</h2>
                        <p className="cardNote">
                          Theo assessed this as{' '}
                          <b>{SEVERITY_LABEL[state.claim.severity] ?? state.claim.severity}</b> and will request:{' '}
                          {state.claim.recommended_services.join(', ') || 'repair'}.
                        </p>
                        <button className="btn big" disabled={busy} onClick={() => void submit()} type="button">
                          Submit claim <ArrowRight size={16} />
                        </button>
                      </motion.div>
                    ) : null}
                  </>
                )}
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

/** Confirmation screen carrying the claim reference and what happens next. */
function Receipt({
  state,
  onTrack,
  onNewClaim,
  onCopy,
  copied,
}: {
  state: IntakeState;
  onTrack: () => void;
  onNewClaim: () => void;
  onCopy: () => void;
  copied: boolean;
}) {
  return (
    <motion.section animate={{ opacity: 1, y: 0 }} className="card receipt" initial={{ opacity: 0, y: 14 }}>
      <EmotingAgent mood="celebrating" size={128} />
      <h1 style={{ fontSize: 31, marginTop: 10 }}>Your claim is registered</h1>
      <p className="cardNote" style={{ fontSize: 14 }}>
        Keep this reference — you can track your claim with it at any time.
      </p>

      <button className="receiptId" onClick={onCopy} title="Copy reference" type="button">
        {state.claim.id}
        {copied ? <CheckCircle2 size={18} /> : <Copy size={16} />}
      </button>
      <p className="cardNote">{copied ? 'Copied to your clipboard' : 'Tap to copy'}</p>

      <div className="btnRow" style={{ justifyContent: 'center', marginTop: 8 }}>
        <button className="btn" onClick={onTrack} type="button">
          <Radar size={15} /> Track this claim
        </button>
        {/* Without this the receipt is a dead end: a customer with a second incident, or anyone
            trying the demo twice, had no way back to the start. */}
        <button className="btn secondary" onClick={onNewClaim} type="button">
          <Plus size={15} /> Report another incident
        </button>
      </div>

      <PhotoGallery photos={state.attachments} />

      <div className="receiptNext">
        <div>
          <b>1. Handler review</b>
          <small>A claims handler checks your photographs and the policy cover today.</small>
        </div>
        <div>
          <b>2. Suppliers instructed</b>
          <small>
            We will instruct {state.claim.recommended_services.join(', ') || 'a repairer'} and notify you at each step.
          </small>
        </div>
        <div>
          <b>3. Work and settlement</b>
          <small>Suppliers invoice us directly. You pay only your policy excess.</small>
        </div>
      </div>
    </motion.section>
  );
}

const SESSION_KEY = 'i2p.portal.customer';

/** Restore the signed-in policyholder, so a refresh does not throw them back to the login. */
function readSession(): CustomerProfile | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CustomerProfile;
    return parsed.customer_name ? parsed : null;
  } catch {
    return null;
  }
}

/** Persist or clear the session. */
function writeSession(profile: CustomerProfile | null): void {
  try {
    if (profile) window.localStorage.setItem(SESSION_KEY, JSON.stringify(profile));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Private browsing blocks storage; the portal still works for this visit.
  }
}

/** Two-letter monogram for the signed-in customer. */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** Read a picked file into a data URI so it can be posted as JSON. */
function readAsDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

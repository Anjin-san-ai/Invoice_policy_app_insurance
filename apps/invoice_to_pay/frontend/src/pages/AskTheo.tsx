import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowUpRight,
  BadgePoundSterling,
  Building2,
  CornerDownLeft,
  FileText,
  ListChecks,
  MessageSquareWarning,
  Radar,
  RotateCcw,
  Send,
  Sparkles,
  Tags,
  User,
} from 'lucide-react';
import { ChangeEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';
import { apiPost } from '../api/client';
import { AgentMood, EmotingAgent } from '../components/EmotingAgent';
import { MuteButton } from '../components/MuteButton';
import { navigate } from '../router';
import { useSpeech } from '../theme/useSpeech';
import { AssistantAnswer } from '../types';

type Turn = { id: string; role: 'user' | 'theo'; text: string; answer?: AssistantAnswer };

/** Prompt cards for the empty state, grouped the way a handler thinks about their day. */
const PROMPT_CARDS = [
  { Icon: ListChecks, topic: 'My day', question: 'What needs my attention today?' },
  { Icon: Radar, topic: 'Claims', question: 'Which claims are waiting on triage?' },
  { Icon: FileText, topic: 'A claim', question: 'Tell me about CLM-00002' },
  { Icon: BadgePoundSterling, topic: 'Outlay', question: 'What is our total outlay?' },
  { Icon: MessageSquareWarning, topic: 'Disputes', question: 'What is in dispute with suppliers?' },
  { Icon: Building2, topic: 'Suppliers', question: 'Which suppliers have the most variance?' },
  { Icon: Tags, topic: 'Policies', question: 'Are any policies out of date?' },
  { Icon: Sparkles, topic: 'Payments', question: 'What is waiting for payment approval?' },
] as const;

/**
 * Theo, the back-office assistant.
 *
 * Laid out as a conversation-first screen: one centred column, the agent front and centre while
 * the screen is empty, shrinking into the header once a conversation starts. Every figure Theo
 * quotes is computed by the backend from live data, and each answer carries the detail behind it
 * plus the screens that prove it.
 */
export function AskTheo() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [mood, setMood] = useState<AgentMood>('idle');
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const started = turns.length > 0;
  const speech = useSpeech();

  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' });
  }, [turns.length, busy]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setDraft('');
    setMood('thinking');
    const stamp = Date.now();
    setTurns((current) => [...current, { id: `u${stamp}`, role: 'user', text: question }]);
    try {
      const answer = await apiPost<AssistantAnswer>('/api/assistant/ask', { question });
      setTurns((current) => [...current, { id: `t${stamp}`, role: 'theo', text: answer.text, answer }]);
      // Thumbs up on every answer, and read the headline out unless muted.
      setMood('approving');
      speech.speak(answer.text);
      window.setTimeout(() => setMood('idle'), 2600);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setMood('concerned');
      window.setTimeout(() => setMood('idle'), 2000);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  }

  return (
    <div className="theoScreen">
      <header className="theoBar">
        <EmotingAgent mood={mood} showMood={false} size={started ? 52 : 64} />
        <div className="theoBarText">
          <b>Theo</b>
          <small>
            <i className={`theoDot${busy ? ' busy' : ''}`} />
            {busy ? 'Working it out…' : 'Claims operations assistant · sees every claim, invoice and payment'}
          </small>
        </div>
        <MuteButton
          muted={speech.muted}
          onToggle={speech.toggleMute}
          speaking={speech.speaking}
          supported={speech.supported}
        />
        {started ? (
          <button
            className="btn secondary small"
            onClick={() => {
              speech.stop();
              setTurns([]);
            }}
            type="button"
          >
            <RotateCcw size={13} /> New chat
          </button>
        ) : null}
      </header>

      <div className="theoConversation" ref={logRef}>
        {!started ? (
          <motion.div animate={{ opacity: 1, y: 0 }} className="theoWelcome" initial={{ opacity: 0, y: 12 }}>
            {/* Sized so the welcome, the copy and the prompt grid all fit without scrolling, and
                showMood off so the caption pill never sits over the figure. */}
            <EmotingAgent mood={mood} showMood={false} size={172} variant="full" />
            <h1>How can I help?</h1>
            <p>
              Ask me about a claim, an invoice, a dispute, a payment or the total outlay. Name a
              reference like <code>CLM-00002</code> or <code>INV-000123</code> and I will pull it up.
            </p>
            <div className="promptGrid">
              {PROMPT_CARDS.map(({ Icon, topic, question }) => (
                <button
                  className="promptCard"
                  disabled={busy}
                  key={question}
                  onClick={() => void ask(question)}
                  type="button"
                >
                  <span className="promptIcon">
                    <Icon size={16} />
                  </span>
                  <span className="promptText">
                    <small>{topic}</small>
                    <b>{question}</b>
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        ) : null}

        <AnimatePresence initial={false}>
          {turns.map((turn) => (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className={`msg ${turn.role}`}
              initial={{ opacity: 0, y: 10 }}
              key={turn.id}
              transition={{ duration: 0.22 }}
            >
              <span className="msgAvatar">
                {turn.role === 'user' ? <User size={15} /> : <Sparkles size={15} />}
              </span>
              <div className="msgBody">
                <span className="msgWho">{turn.role === 'user' ? 'You' : 'Theo'}</span>
                <p className="msgText">{turn.text}</p>

                {turn.answer?.bullets.length ? (
                  <ul className="msgBullets">
                    {turn.answer.bullets.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                ) : null}

                {turn.answer?.metrics.length ? (
                  <div className="msgMetrics">
                    {turn.answer.metrics.map((metric) => (
                      <div className="msgMetric" key={metric.label}>
                        <span>{metric.label}</span>
                        <b>{metric.value}</b>
                      </div>
                    ))}
                  </div>
                ) : null}

                {turn.answer?.links.length ? (
                  <div className="msgLinks">
                    {turn.answer.links.map((link) => (
                      <button
                        className="msgLink"
                        key={`${link.route}-${link.label}`}
                        onClick={() => navigate(link.route.split('?')[0], queryOf(link.route))}
                        type="button"
                      >
                        {link.label} <ArrowUpRight size={13} />
                      </button>
                    ))}
                  </div>
                ) : null}

                {turn.answer?.follow_ups.length ? (
                  <div className="msgFollowUps">
                    <small>Ask next</small>
                    <div>
                      {turn.answer.follow_ups.map((question) => (
                        <button
                          className="chatQuickChip"
                          disabled={busy}
                          key={question}
                          onClick={() => void ask(question)}
                          type="button"
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {busy ? (
          <div className="msg theo">
            <span className="msgAvatar">
              <Sparkles size={15} />
            </span>
            <div className="msgBody">
              <span className="msgWho">Theo</span>
              <div className="chatTyping" style={{ padding: '6px 0' }}>
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {error ? <p className="banner bad theoError">{error}</p> : null}

      <div className="theoComposer">
        <textarea
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a claim, an invoice, a dispute, a payment or the outlay…"
          rows={1}
          value={draft}
        />
        <span className="composerHint">
          <CornerDownLeft size={12} /> to send
        </span>
        <button
          aria-label="Ask Theo"
          className="chatSend"
          disabled={busy || !draft.trim()}
          onClick={() => void ask(draft)}
          type="button"
        >
          <Send size={17} />
        </button>
      </div>
    </div>
  );
}

/** Split any query string off a suggested route so navigate() gets its params separately. */
function queryOf(route: string): Record<string, string> {
  const [, query] = route.split('?');
  if (!query) return {};
  return Object.fromEntries(new URLSearchParams(query).entries());
}

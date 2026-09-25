import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

/** What Theo is doing, which drives her expression, lighting and motion. */
export type AgentMood =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'happy'
  | 'concerned'
  | 'celebrating'
  /** Answered a question: smiles and gives a thumbs up. */
  | 'approving';

const MOOD_COPY: Record<AgentMood, string> = {
  idle: 'Ready when you are',
  listening: 'Listening',
  thinking: 'Thinking',
  happy: 'Got it, thank you',
  concerned: 'That sounds nasty',
  celebrating: 'All done',
  approving: 'Hope that helps',
};

/** The moods that read as pleased, which share the smile, cheeks and raised brows. */
const POSITIVE: ReadonlySet<AgentMood> = new Set<AgentMood>(['happy', 'celebrating', 'approving']);

/**
 * Theo, rendered as a stylised digital human.
 *
 * This is deliberately not a cartoon: the face is built from anatomical layers — cranium, jaw,
 * cheekbone and brow shading, almond eyes with iris, limbus, pupil and a specular highlight,
 * separate upper and lower lips — and it is animated the way a face actually moves. She breathes,
 * her head drifts, her eyes make small saccades and blink irregularly, and her expression is
 * carried by brow and lid position rather than by a smile curve.
 *
 * A genuinely photoreal avatar (Soul Machines, or Azure AI text-to-speech avatar) is a streamed
 * 3D render and cannot be drawn in SVG; this is the closest a self-contained, dependency-free
 * component gets, and it costs nothing to run on a booth machine.
 */
export function EmotingAgent({
  mood,
  size = 148,
  variant = 'avatar',
  showMood = true,
}: {
  mood: AgentMood;
  size?: number;
  /** 'avatar' is a tight head crop for the chat header; 'full' is the head and shoulders bust. */
  variant?: 'avatar' | 'full';
  /** Off for small inline avatars, where the caption pill would be wider than the figure. */
  showMood?: boolean;
}) {
  const [blink, setBlink] = useState(false);
  const [gaze, setGaze] = useState({ x: 0, y: 0 });
  const uid = useRef(`ava${Math.random().toString(36).slice(2, 8)}`).current;
  const isFull = variant === 'full';

  // Irregular blinking. A metronomic blink is one of the things that makes a face read as fake.
  useEffect(() => {
    let timer: number;
    function schedule() {
      timer = window.setTimeout(
        () => {
          setBlink(true);
          window.setTimeout(() => setBlink(false), 95 + Math.random() * 60);
          schedule();
        },
        1800 + Math.random() * 3400,
      );
    }
    schedule();
    return () => window.clearTimeout(timer);
  }, []);

  // Saccades: small, fast eye movements between fixations, which is how eyes actually behave.
  useEffect(() => {
    if (mood === 'thinking') {
      setGaze({ x: 1.6, y: -2.2 });
      return;
    }
    let timer: number;
    function schedule() {
      timer = window.setTimeout(
        () => {
          setGaze({ x: (Math.random() - 0.5) * 2.6, y: (Math.random() - 0.5) * 1.5 });
          schedule();
        },
        900 + Math.random() * 2200,
      );
    }
    schedule();
    return () => window.clearTimeout(timer);
  }, [mood]);

  const lidClosure = blink ? 1 : mood === 'listening' ? -0.12 : mood === 'concerned' ? 0.16 : 0.04;
  const browLift = mood === 'listening' ? -2.2 : mood === 'concerned' ? 1.6 : POSITIVE.has(mood) ? -1.6 : 0;

  return (
    <div
      className={`agentStage${isFull ? ' full' : ''}`}
      style={{ width: size, height: isFull ? size * 1.24 : size }}
    >
      {/* Volumetric glow behind the figure. */}
      <motion.span
        animate={{
          scale: mood === 'idle' ? 1 : mood === 'celebrating' ? 1.14 : 1.07,
          opacity: mood === 'idle' ? 0.55 : 0.9,
        }}
        className={`agentAura ${mood}`}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      />

      {/* Concentric presence rings, the visual language of a listening assistant. */}
      {(mood === 'listening' || mood === 'thinking') && (
        <span className="agentRings">
          {[0, 1, 2].map((ring) => (
            <motion.i
              animate={{ scale: [0.82, 1.22], opacity: [0.5, 0] }}
              key={ring}
              transition={{ duration: 2.4, repeat: Infinity, delay: ring * 0.8, ease: 'easeOut' }}
            />
          ))}
        </span>
      )}

      <motion.div
        animate={{
          // Breathing, plus a slow head drift so she is never perfectly still.
          scale: mood === 'celebrating' ? [1, 1.035, 1] : [1, 1.012, 1],
          y: mood === 'celebrating' ? [0, -6, 0] : [0, -2.2, 0],
          rotate: mood === 'thinking' ? [-1.2, 0.4, -1.2] : [-0.5, 0.5, -0.5],
        }}
        className="agentBody"
        transition={{
          duration: mood === 'celebrating' ? 1.1 : mood === 'listening' ? 3.2 : 5.2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      >
        <svg height="100%" role="img" viewBox={isFull ? '0 0 200 250' : '0 0 200 200'} width="100%">
          <title>{`Theo, the claims assistant: ${MOOD_COPY[mood]}`}</title>
          <defs>
            <linearGradient id={`${uid}skin`} x1="0.2" x2="0.9" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--agent-skin-1)" />
              <stop offset="62%" stopColor="var(--agent-skin-2)" />
              <stop offset="100%" stopColor="var(--agent-shade)" />
            </linearGradient>
            <linearGradient id={`${uid}hair`} x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--agent-hair)" />
              <stop offset="100%" stopColor="var(--accent-2)" />
            </linearGradient>
            <linearGradient id={`${uid}cloth`} x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" />
              <stop offset="100%" stopColor="var(--accent-2)" />
            </linearGradient>
            <radialGradient id={`${uid}iris`} cx="0.42" cy="0.36" r="0.75">
              <stop offset="0%" stopColor="var(--agent-rim)" />
              <stop offset="55%" stopColor="var(--agent-iris)" />
              <stop offset="100%" stopColor="var(--agent-hair)" />
            </radialGradient>
            {/* Soft shading, which is what separates a rendered face from flat clip art. */}
            <filter id={`${uid}blur`} x="-30%" y="-30%" height="160%" width="160%">
              <feGaussianBlur stdDeviation="5.5" />
            </filter>
            <filter id={`${uid}blurSm`} x="-30%" y="-30%" height="160%" width="160%">
              <feGaussianBlur stdDeviation="2.4" />
            </filter>
            <clipPath id={`${uid}face`}>
              <path d="M100 30 C126 30 141 48 141 76 C141 104 126 136 100 136 C74 136 59 104 59 76 C59 48 74 30 100 30 Z" />
            </clipPath>
          </defs>

          {/* ---------------- shoulders and neck ---------------- */}
          {isFull && (
            <g>
              <path d="M88 128 L112 128 L114 156 L86 156 Z" fill="var(--agent-skin-2)" />
              <path d="M86 150 Q100 162 114 150 L118 156 Q100 170 82 156 Z" fill="var(--agent-shade)" opacity="0.55" />
              <path
                d="M100 152 C133 152 162 174 168 208 L172 250 L28 250 L32 208 C38 174 67 152 100 152 Z"
                fill={`url(#${uid}cloth)`}
              />
              {/* Collar. */}
              <path d="M84 154 L100 178 L116 154 L110 150 L100 166 L90 150 Z" fill="var(--surface)" opacity="0.22" />
              {/* Rim light along the shoulder, the cue that reads as a lit 3D form. */}
              <path
                d="M100 152 C133 152 162 174 168 208"
                fill="none"
                opacity="0.5"
                stroke="var(--agent-rim)"
                strokeLinecap="round"
                strokeWidth="2.4"
              />
            </g>
          )}

          {/* ---------------- hair, behind the face ---------------- */}
          <path
            d="M100 22 C130 22 150 44 150 76 C150 92 147 104 144 112 L140 84 C138 60 122 46 100 46 C78 46 62 60 60 84 L56 112 C53 104 50 92 50 76 C50 44 70 22 100 22 Z"
            fill={`url(#${uid}hair)`}
          />

          {/* ---------------- face ---------------- */}
          <path
            d="M100 30 C126 30 141 48 141 76 C141 104 126 136 100 136 C74 136 59 104 59 76 C59 48 74 30 100 30 Z"
            fill={`url(#${uid}skin)`}
          />

          {/* Shading inside the face: temple, cheekbones, jaw and a nose shadow. */}
          <g clipPath={`url(#${uid}face)`}>
            <ellipse cx="138" cy="88" fill="var(--agent-shade)" filter={`url(#${uid}blur)`} opacity="0.5" rx="16" ry="34" />
            <ellipse cx="62" cy="88" fill="var(--agent-shade)" filter={`url(#${uid}blur)`} opacity="0.32" rx="13" ry="30" />
            <ellipse cx="100" cy="132" fill="var(--agent-shade)" filter={`url(#${uid}blur)`} opacity="0.42" rx="26" ry="12" />
            <ellipse cx="78" cy="94" fill="var(--agent-skin-1)" filter={`url(#${uid}blur)`} opacity="0.5" rx="14" ry="9" />
            <ellipse cx="122" cy="94" fill="var(--agent-skin-1)" filter={`url(#${uid}blur)`} opacity="0.4" rx="14" ry="9" />
            {/* Rim light down the right edge of the face. */}
            <path
              d="M138 58 C143 74 142 104 128 124"
              fill="none"
              filter={`url(#${uid}blurSm)`}
              opacity="0.55"
              stroke="var(--agent-rim)"
              strokeWidth="3"
            />
          </g>

          {/* Brows: thin, and they carry most of the expression. */}
          <g transform={`translate(0 ${browLift})`}>
            <path
              d={mood === 'concerned' ? 'M74 68 Q84 64 93 68' : 'M74 66 Q84 61 93 65'}
              fill="none"
              stroke="var(--agent-hair)"
              strokeLinecap="round"
              strokeWidth="2.8"
            />
            <path
              d={mood === 'concerned' ? 'M126 68 Q116 64 107 68' : 'M126 66 Q116 61 107 65'}
              fill="none"
              stroke="var(--agent-hair)"
              strokeLinecap="round"
              strokeWidth="2.8"
            />
          </g>

          {/* Eyes: almond socket, iris, pupil, highlight, then a lid that closes over the top. */}
          {[
            { cx: 84, dir: -1 },
            { cx: 116, dir: 1 },
          ].map((eye) => (
            <g key={eye.cx}>
              <ellipse cx={eye.cx} cy="80" fill="#fdfbfa" rx="10.5" ry="6.4" />
              <g transform={`translate(${gaze.x * eye.dir * 0.6 + gaze.x * 0.4} ${gaze.y})`}>
                <circle cx={eye.cx} cy="80" fill={`url(#${uid}iris)`} r="4.9" />
                <circle cx={eye.cx} cy="80" fill="var(--agent-hair)" opacity="0.5" r="4.9" />
                <circle cx={eye.cx} cy="80" fill={`url(#${uid}iris)`} r="4.1" />
                <circle cx={eye.cx} cy="80" fill="#0b0a14" r="2.1" />
                <circle cx={eye.cx - 1.8} cy="78" fill="#ffffff" opacity="0.92" r="1.5" />
                <circle cx={eye.cx + 2.1} cy="82.4" fill="var(--agent-rim)" opacity="0.5" r="0.9" />
              </g>
              {/* Upper lid. scaleY drives both the blink and the lid aperture per mood. */}
              <motion.ellipse
                animate={{ scaleY: lidClosure }}
                cx={eye.cx}
                cy="74.2"
                fill="var(--agent-skin-1)"
                rx="11.4"
                ry="7.6"
                style={{ originX: `${eye.cx}px`, originY: '74.2px' }}
                transition={{ duration: 0.085, ease: 'easeOut' }}
              />
              {/* Lash line and lower lid crease. */}
              <path
                d={`M${eye.cx - 10.5} 79.6 Q${eye.cx} ${blink ? 80.4 : 72.6} ${eye.cx + 10.5} 79.6`}
                fill="none"
                stroke="var(--agent-hair)"
                strokeLinecap="round"
                strokeWidth="1.7"
              />
              <path
                d={`M${eye.cx - 8.6} 86.4 Q${eye.cx} 88.6 ${eye.cx + 8.6} 86.4`}
                fill="none"
                opacity="0.32"
                stroke="var(--agent-shade)"
                strokeWidth="1.1"
              />
            </g>
          ))}

          {/* Nose: implied by shadow and a nostril hint, never outlined. */}
          <path d="M100 86 Q97 98 94 104" fill="none" opacity="0.3" stroke="var(--agent-shade)" strokeWidth="1.6" />
          <ellipse cx="95" cy="106" fill="var(--agent-shade)" opacity="0.45" rx="1.7" ry="1.1" />
          <ellipse cx="105" cy="106" fill="var(--agent-shade)" opacity="0.45" rx="1.7" ry="1.1" />

          {/* Mouth: separate upper and lower lip, so it changes shape rather than curving. */}
          <motion.path
            animate={{ d: upperLip(mood) }}
            fill="var(--agent-lip)"
            opacity="0.92"
            transition={{ duration: 0.3, ease: 'easeOut' }}
          />
          <motion.path
            animate={{ d: lowerLip(mood) }}
            fill="var(--agent-lip)"
            transition={{ duration: 0.3, ease: 'easeOut' }}
          />
          {/* Teeth appear only on a broad smile. */}
          {mood === 'celebrating' && <path d="M91 114 Q100 118 109 114 Q100 116 91 114 Z" fill="#fffdfb" />}

          {/* Thumbs up: raised forearm and fist, drawn only when Theo has just answered. */}
          {isFull && mood === 'approving' ? (
            <motion.g
              animate={{ y: 0, opacity: 1, rotate: 0 }}
              initial={{ y: 16, opacity: 0, rotate: -10 }}
              transition={{ type: 'spring', stiffness: 260, damping: 16 }}
            >
              <path
                d="M150 182 Q162 166 160 148"
                fill="none"
                stroke={`url(#${uid}cloth)`}
                strokeLinecap="round"
                strokeWidth="9"
              />
              <rect fill="var(--agent-skin-1)" height="23" rx="9" width="21" x="150" y="126" />
              <path
                d="M155 130 L155 114"
                fill="none"
                stroke="var(--agent-skin-1)"
                strokeLinecap="round"
                strokeWidth="9"
              />
              <path
                d="M157 136 L168 136 M157 142 L168 142"
                opacity="0.38"
                stroke="var(--agent-shade)"
                strokeWidth="1.4"
              />
            </motion.g>
          ) : null}
          <path d="M100 124 Q100 127 100 128" opacity="0.3" stroke="var(--agent-shade)" strokeWidth="1.2" />

          {/* Voice waveform while listening: the assistant's "I can hear you" signal. */}
          {mood === 'listening' && isFull && (
            <g transform="translate(100 196)">
              {[-24, -14, -4, 6, 16].map((offset, index) => (
                <motion.rect
                  animate={{ height: [5, 17, 5], y: [-2.5, -8.5, -2.5] }}
                  fill="var(--agent-rim)"
                  key={offset}
                  opacity="0.85"
                  rx="1.8"
                  transition={{ duration: 0.75, repeat: Infinity, delay: index * 0.1, ease: 'easeInOut' }}
                  width="3.6"
                  x={offset}
                />
              ))}
            </g>
          )}
        </svg>
      </motion.div>

      {/* Celebration motes, kept sparse so it reads as considered rather than confetti. */}
      <AnimatePresence>
        {mood === 'celebrating' ? (
          <span className="agentBurst">
            {Array.from({ length: 12 }).map((_, index) => (
              <motion.i
                animate={{
                  opacity: 0,
                  scale: 1,
                  x: Math.cos((index / 12) * Math.PI * 2) * 86,
                  y: Math.sin((index / 12) * Math.PI * 2) * 86,
                }}
                initial={{ opacity: 0.95, scale: 0.25, x: 0, y: 0 }}
                key={index}
                transition={{ duration: 1.1, delay: index * 0.025, ease: 'easeOut' }}
              />
            ))}
          </span>
        ) : null}
      </AnimatePresence>

      {showMood ? (
        <AnimatePresence mode="wait">
          <motion.p
            animate={{ opacity: 1, y: 0 }}
            className="agentMood"
            exit={{ opacity: 0, y: -4 }}
            initial={{ opacity: 0, y: 4 }}
            key={mood}
            transition={{ duration: 0.2 }}
          >
            {MOOD_COPY[mood]}
          </motion.p>
        </AnimatePresence>
      ) : null}
    </div>
  );
}

/** Upper lip shape per mood. */
function upperLip(mood: AgentMood): string {
  switch (mood) {
    case 'celebrating':
      return 'M88 112 Q100 106 112 112 Q100 116 88 112 Z';
    case 'happy':
      return 'M90 113 Q100 108 110 113 Q100 116 90 113 Z';
    case 'concerned':
      return 'M91 115 Q100 112 109 115 Q100 117 91 115 Z';
    case 'listening':
      return 'M92 113 Q100 110 108 113 Q100 116 92 113 Z';
    default:
      return 'M91 114 Q100 111 109 114 Q100 116.5 91 114 Z';
  }
}

/** Lower lip shape per mood. */
function lowerLip(mood: AgentMood): string {
  switch (mood) {
    case 'celebrating':
      return 'M88 112 Q100 128 112 112 Q100 122 88 112 Z';
    case 'happy':
      return 'M90 113 Q100 124 110 113 Q100 120 90 113 Z';
    case 'concerned':
      return 'M91 115 Q100 120 109 115 Q100 122 91 115 Z';
    case 'thinking':
      return 'M93 114 Q101 118 108 113 Q100 119 93 114 Z';
    default:
      return 'M91 114 Q100 121 109 114 Q100 119 91 114 Z';
  }
}

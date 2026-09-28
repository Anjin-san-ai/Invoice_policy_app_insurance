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

/** The rim-light colour per mood: cyan at rest, amber for concern, blue-violet when celebrating. */
const MOOD_RIM: Record<AgentMood, string> = {
  idle: 'rgba(42, 212, 255, 0.55)',
  listening: 'rgba(42, 212, 255, 0.95)',
  thinking: 'rgba(107, 79, 216, 0.85)',
  happy: 'rgba(5, 150, 105, 0.7)',
  concerned: 'rgba(217, 119, 6, 0.75)',
  celebrating: 'rgba(0, 51, 160, 0.9)',
  approving: 'rgba(0, 165, 201, 0.8)',
};

/** Theo's canonical likeness, served from `public/`. See the note on the component. */
const PORTRAIT = 'theo.jpg';

/**
 * Theo, the claims assistant, rendered as her reference portrait under a live animation rig.
 *
 * The likeness itself is the authored render in `public/theo.jpg` — the white android helmet with
 * cyan light channels, the dark brow visor and the segmented neck. Everything that moves is done
 * in code around that still: she breathes and drifts, her gaze parallaxes, she blinks with an
 * irregular cadence, and a rim light plus concentric presence rings react to her mood.
 *
 * Why a portrait and not drawn geometry: the previous revision of this component built the face
 * from SVG primitives, and a hand-authored path set cannot hold a stylised human likeness — it
 * read as clip art next to the reference. Compositing motion over the real render is both exact
 * and cheap, and it keeps the whole mood API below unchanged.
 *
 * All motion honours `prefers-reduced-motion` through the `reduced` guard.
 */
export function EmotingAgent({
  mood,
  size = 148,
  variant = 'avatar',
  showMood = true,
}: {
  mood: AgentMood;
  size?: number;
  /** 'avatar' is a tight circular head crop; 'full' is the head and shoulders bust. */
  variant?: 'avatar' | 'full';
  /** Off for small inline avatars, where the caption pill would be wider than the figure. */
  showMood?: boolean;
}) {
  const [blink, setBlink] = useState(false);
  const [gaze, setGaze] = useState({ x: 0, y: 0 });
  const isFull = variant === 'full';
  const reduced = useRef(
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  ).current;

  // Irregular blinking. A metronomic blink is one of the things that makes a face read as fake.
  useEffect(() => {
    if (reduced) return;
    let timer: number;
    function schedule() {
      timer = window.setTimeout(
        () => {
          setBlink(true);
          window.setTimeout(() => setBlink(false), 105 + Math.random() * 55);
          schedule();
        },
        1800 + Math.random() * 3400,
      );
    }
    schedule();
    return () => window.clearTimeout(timer);
  }, [reduced]);

  // Saccades: small, fast shifts between fixations, which is how a gaze actually behaves. They
  // parallax the portrait rather than moving an eyeball, so the whole head settles into a new pose.
  useEffect(() => {
    if (reduced) return;
    if (mood === 'thinking') {
      setGaze({ x: 2.4, y: -2.6 });
      return;
    }
    let timer: number;
    function schedule() {
      timer = window.setTimeout(
        () => {
          setGaze({ x: (Math.random() - 0.5) * 3.4, y: (Math.random() - 0.5) * 2 });
          schedule();
        },
        900 + Math.random() * 2200,
      );
    }
    schedule();
    return () => window.clearTimeout(timer);
  }, [mood, reduced]);

  const rim = MOOD_RIM[mood];
  // The portrait is a square crop framing the helmet; 'full' pulls back to include the shoulders.
  const zoom = isFull ? 1.02 : 1.34;

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
      {(mood === 'listening' || mood === 'thinking') && !reduced && (
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
        animate={
          reduced
            ? {}
            : {
                // Breathing, plus a slow head drift so she is never perfectly still.
                scale: mood === 'celebrating' ? [1, 1.035, 1] : [1, 1.014, 1],
                y: mood === 'celebrating' ? [0, -6, 0] : [0, -2.6, 0],
                rotate: mood === 'thinking' ? [-1.4, 0.5, -1.4] : [-0.6, 0.6, -0.6],
              }
        }
        className="agentBody"
        transition={{
          duration: mood === 'celebrating' ? 1.1 : mood === 'listening' ? 3.2 : 5.2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        style={{ width: '100%', height: '100%' }}
      >
        <div
          aria-label={`Theo, the claims assistant: ${MOOD_COPY[mood]}`}
          role="img"
          style={{
            position: 'relative',
            width: '100%',
            height: '100%',
            overflow: 'hidden',
            borderRadius: isFull ? '22% 22% 26% 26% / 18% 18% 12% 12%' : '50%',
            // The rim light. Two stacked shadows read as a lit edge plus an ambient bloom.
            boxShadow: `inset 0 0 ${isFull ? 26 : 18}px ${rim}, 0 0 28px ${rim}`,
            transition: 'box-shadow 420ms ease-out',
          }}
        >
          {/* The likeness. The gaze offset parallaxes it inside the frame; the blink squashes it
              briefly about the eye line, which reads as a blink without redrawing the face. */}
          <motion.img
            alt=""
            animate={{
              x: gaze.x,
              y: gaze.y,
              scaleY: blink ? 0.975 : 1,
              // The crop zoom lives here, not in `style`, because framer-motion owns `transform`.
              scale: mood === 'celebrating' ? zoom * 1.04 : zoom,
            }}
            src={PORTRAIT}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              objectPosition: isFull ? 'center top' : '50% 34%',
              transformOrigin: '50% 40%',
              display: 'block',
            }}
            transition={{ duration: blink ? 0.09 : 0.42, ease: 'easeOut' }}
          />

          {/* Mood wash over the portrait, so her lighting changes with what she is doing. */}
          <motion.span
            animate={{ opacity: mood === 'idle' ? 0 : 0.22 }}
            style={{
              position: 'absolute',
              inset: 0,
              background: `radial-gradient(circle at 50% 30%, ${rim}, transparent 72%)`,
              mixBlendMode: 'screen',
              pointerEvents: 'none',
            }}
            transition={{ duration: 0.5 }}
          />

          {/* Scanline sweep while she is thinking: the one overtly synthetic cue. */}
          {mood === 'thinking' && !reduced && (
            <motion.span
              animate={{ y: ['-12%', '112%'] }}
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                height: '18%',
                background: 'linear-gradient(transparent, rgba(42, 212, 255, 0.3), transparent)',
                pointerEvents: 'none',
              }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
            />
          )}

          {/* Voice waveform while listening: the assistant's "I can hear you" signal. */}
          {mood === 'listening' && !reduced && (
            <span
              style={{
                position: 'absolute',
                bottom: '7%',
                left: 0,
                right: 0,
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'center',
                gap: 4,
                height: '16%',
                pointerEvents: 'none',
              }}
            >
              {[0, 1, 2, 3, 4].map((bar) => (
                <motion.i
                  animate={{ height: ['18%', '86%', '18%'] }}
                  key={bar}
                  style={{
                    width: 3.5,
                    borderRadius: 2,
                    background: 'var(--agent-glow, #2ad4ff)',
                    boxShadow: '0 0 8px rgba(42, 212, 255, 0.9)',
                  }}
                  transition={{ duration: 0.75, repeat: Infinity, delay: bar * 0.1, ease: 'easeInOut' }}
                />
              ))}
            </span>
          )}
        </div>
      </motion.div>

      {/* Celebration motes, kept sparse so it reads as considered rather than confetti. */}
      <AnimatePresence>
        {mood === 'celebrating' && !reduced ? (
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

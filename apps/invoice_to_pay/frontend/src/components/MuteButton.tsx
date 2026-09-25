import { motion } from 'framer-motion';
import { Volume2, VolumeX } from 'lucide-react';

/** Mute control for Theo's voice. Hidden entirely where the browser cannot speak. */
export function MuteButton({
  muted,
  speaking,
  supported,
  onToggle,
}: {
  muted: boolean;
  speaking: boolean;
  supported: boolean;
  onToggle: () => void;
}) {
  if (!supported) return null;

  return (
    <button
      aria-label={muted ? 'Unmute Theo' : 'Mute Theo'}
      aria-pressed={muted}
      className={`muteBtn${muted ? ' muted' : ''}${speaking ? ' speaking' : ''}`}
      onClick={onToggle}
      title={muted ? 'Theo is muted — click to hear him' : 'Theo speaks answers aloud — click to mute'}
      type="button"
    >
      {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
      {/* Bars animate only while actually speaking, so the control doubles as a status light. */}
      {speaking ? (
        <span className="muteBars">
          {[0, 1, 2].map((bar) => (
            <motion.i
              animate={{ scaleY: [0.4, 1, 0.4] }}
              key={bar}
              transition={{ duration: 0.6, repeat: Infinity, delay: bar * 0.12, ease: 'easeInOut' }}
            />
          ))}
        </span>
      ) : null}
    </button>
  );
}

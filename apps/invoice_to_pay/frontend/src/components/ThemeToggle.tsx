import { motion } from 'framer-motion';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../theme/useTheme';

/** Light/dark switch. Lives in the shell top bar and in the customer portal header. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
      className={`themeToggle${isDark ? ' on' : ''}`}
      onClick={toggle}
      title={isDark ? 'Light mode' : 'Dark mode'}
      type="button"
    >
      <span className="themeToggleTrack">
        <motion.span
          className="themeToggleKnob"
          layout
          transition={{ type: 'spring', stiffness: 520, damping: 34 }}
        >
          {isDark ? <Moon size={12} /> : <Sun size={12} />}
        </motion.span>
      </span>
      <span className="themeToggleLabel">{isDark ? 'Dark' : 'Light'}</span>
    </button>
  );
}

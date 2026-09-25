import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type ThemeName = 'light' | 'dark';

const STORAGE_KEY = 'i2p.theme';

/** Read the persisted choice, falling back to light so the corporate default is what a new user sees. */
function initialTheme(): ThemeName {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // Private-mode browsers throw on localStorage access; the default below is still correct.
  }
  return 'light';
}

type ThemeContextValue = { theme: ThemeName; toggle: () => void; setTheme: (next: ThemeName) => void };

const ThemeContext = createContext<ThemeContextValue>({ theme: 'light', toggle: () => {}, setTheme: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(initialTheme);

  // The data-theme attribute on <html> is what the token blocks in style.css key off.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Persistence is a convenience, not a requirement; ignore a write failure.
    }
  }, [theme]);

  const setTheme = useCallback((next: ThemeName) => setThemeState(next), []);
  const toggle = useCallback(() => setThemeState((current) => (current === 'light' ? 'dark' : 'light')), []);
  const value = useMemo(() => ({ theme, toggle, setTheme }), [theme, toggle, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

/** Chart colours resolved from the active theme's CSS custom properties.
 *
 * Recharts needs concrete colour strings rather than var() references, so the tokens are read off
 * the document once per theme change and handed to the chart components as plain hex values.
 */
export function useChartTokens() {
  const { theme } = useTheme();
  return useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
    return {
      theme,
      series: [
        token('--series-1', '#0033a0'),
        token('--series-2', '#00a5c9'),
        token('--series-3', '#6b4fd8'),
        token('--series-4', '#d97706'),
        token('--series-5', '#059669'),
        token('--series-6', '#b91c1c'),
      ],
      axis: token('--text-muted', '#5a6b85'),
      grid: token('--border-light', '#e6ecf5'),
      text: token('--text', '#173793'),
      surface: token('--surface', '#ffffff'),
      primary: token('--primary', '#0033a0'),
      accent: token('--accent', '#00a5c9'),
      success: token('--success', '#059669'),
      warning: token('--warning', '#d97706'),
      danger: token('--danger', '#dc2626'),
      heatBase: token('--heat-base', '0, 51, 160'),
      heatInk: token('--heat-ink', '#ffffff'),
    };
  }, [theme]);
}

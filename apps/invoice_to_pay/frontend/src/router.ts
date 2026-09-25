import { useEffect, useState } from 'react';

export type Route = { path: string; params: URLSearchParams };

/** The front door is the audience chooser, not the back office. */
export const DEFAULT_PATH = '/';
export const BACK_OFFICE_PATH = '/dashboard';

function parseHash(): Route {
  const raw = window.location.hash.replace(/^#/, '') || DEFAULT_PATH;
  const [path, query = ''] = raw.split('?');
  return { path: path || DEFAULT_PATH, params: new URLSearchParams(query) };
}

/** Subscribe to hash changes so the shell re-renders when the active module changes. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parseHash);

  useEffect(() => {
    function onChange() {
      setRoute(parseHash());
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  return route;
}

/** Navigate to a module, optionally with filter query parameters. */
export function navigate(path: string, params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  window.location.hash = query ? `${path}?${query}` : path;
}

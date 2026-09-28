import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGet } from './client';

export type ApiState<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Fetch a JSON endpoint, exposing loading and error state so screens never fail silently. */
export function useApi<T>(path: string | null): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [nonce, setNonce] = useState(0);
  /** Which path the data on screen belongs to, so a revalidation is distinguishable from a move. */
  const loadedPath = useRef<string | null>(null);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    // Revalidate in place: re-fetching a path we already hold keeps the current data on screen
    // rather than flipping to the loading state. Callers render a skeleton while `loading` is
    // true, so doing that on every `reload()` would unmount the whole screen and read to the
    // user as the page refreshing — losing scroll position and any local UI state with it.
    const movedPath = loadedPath.current !== path;
    setLoading(movedPath);
    setError(null);
    apiGet<T>(path)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        loadedPath.current = path;
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  return { data, error, loading, reload };
}

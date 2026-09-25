import { AnimatePresence, motion } from 'framer-motion';
import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiGet } from '../api/client';
import { navigate } from '../router';
import { SearchResponse } from '../types';

/** Global search bar rendered by the shell, so it is present on every screen. */
export function GlobalSearch() {
  const [term, setTerm] = useState('');
  const [data, setData] = useState<SearchResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    if (term.trim().length < 2) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      apiGet<SearchResponse>(`/api/search?q=${encodeURIComponent(term.trim())}`)
        .then((result) => {
          if (!cancelled) {
            setData(result);
            setCursor(0);
            setOpen(true);
          }
        })
        .catch(() => {
          if (!cancelled) setData(null);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [term]);

  // Ctrl+K / Cmd+K focuses the bar from anywhere; Escape closes the panel.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const flat = useMemo(
    () => (data?.groups ?? []).flatMap((group) => group.hits.map((hit) => ({ ...hit, group: group.title }))),
    [data],
  );

  function go(route: string) {
    setOpen(false);
    setTerm('');
    setData(null);
    const [path, query] = route.split('?');
    const params = query ? Object.fromEntries(new URLSearchParams(query).entries()) : {};
    navigate(path, params);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!flat.length) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCursor((current) => (current + 1) % flat.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor((current) => (current - 1 + flat.length) % flat.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = flat[cursor];
      if (hit) go(hit.route);
    }
  }

  let index = -1;

  return (
    <div className="globalSearch" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false); }}>
      <div className="searchField">
        <Search size={16} />
        <input
          aria-label="Search invoices, claims, suppliers, policies and modules"
          onChange={(event) => setTerm(event.target.value)}
          onFocus={() => { if (data) setOpen(true); }}
          onKeyDown={onKeyDown}
          placeholder="Search invoices, claims, suppliers, policies…"
          ref={inputRef}
          type="search"
          value={term}
        />
        {term ? (
          <button aria-label="Clear search" className="searchClear" onClick={() => { setTerm(''); setData(null); setOpen(false); }} type="button">
            <X size={14} />
          </button>
        ) : (
          <kbd className="searchKbd">Ctrl K</kbd>
        )}
      </div>

      <AnimatePresence>
        {open && data ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="searchPanel"
            exit={{ opacity: 0, y: -6 }}
            initial={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16 }}
          >
            <p className="searchMeta">
              {data.total.toLocaleString('en-GB')} match{data.total === 1 ? '' : 'es'} for &ldquo;{data.query}&rdquo;
              {loading ? ' · searching…' : ''}
            </p>
            {data.groups.length === 0 ? (
              <p className="searchEmpty">Nothing matched. Try an invoice number, claim reference, supplier or policy id.</p>
            ) : (
              data.groups.map((group) => (
                <div className="searchGroup" key={group.key}>
                  <p className="searchGroupTitle">
                    {group.title}
                    <span>{group.count.toLocaleString('en-GB')}</span>
                  </p>
                  {group.hits.map((hit) => {
                    index += 1;
                    const active = index === cursor;
                    return (
                      <button
                        className={`searchHit${active ? ' active' : ''}`}
                        key={`${group.key}-${hit.route}-${hit.title}`}
                        onClick={() => go(hit.route)}
                        onMouseEnter={() => setCursor(flat.findIndex((candidate) => candidate.route === hit.route && candidate.title === hit.title))}
                        type="button"
                      >
                        <span className="searchHitMain">
                          <strong>{hit.title}</strong>
                          <small>{hit.subtitle}</small>
                        </span>
                        <span className="chip">{hit.badge}</span>
                      </button>
                    );
                  })}
                  {group.count > group.hits.length ? (
                    <p className="searchMore">+{(group.count - group.hits.length).toLocaleString('en-GB')} more in {group.title.toLowerCase()}</p>
                  ) : null}
                </div>
              ))
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

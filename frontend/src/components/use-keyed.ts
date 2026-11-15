"use client";
import { useEffect, useRef, useState } from 'react';

/** Runs `fn` whenever `key` changes (after `delay` ms) and returns the result for the CURRENT key only. A null key means "do nothing". */
export function useKeyed<T>(key: string | null, fn: () => Promise<T>, delay = 0) {
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null } | null>(null);
  const latest = useRef(fn);
  useEffect(() => { latest.current = fn; });
  useEffect(() => {
    if (key === null) return;
    let live = true;
    const timer = setTimeout(() => {
      latest.current().then(data => { if (live) setState({ key, data, error: null }); })
        .catch((e: unknown) => { if (live) setState({ key, data: null, error: e instanceof Error ? e.message : String(e) }); });
    }, delay);
    return () => { live = false; clearTimeout(timer); };
  }, [key, delay]);
  const current = state && state.key === key ? state : null;
  return { data: current?.data ?? null, error: current?.error ?? null, loading: key !== null && current === null };
}

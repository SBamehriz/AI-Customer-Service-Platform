import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  /** Run the loader again. Safe to call from event handlers. */
  reload: () => void;
  /** Replace the data locally, for optimistic updates. */
  setData: (next: T | ((current: T | null) => T)) => void;
}

/** Run an async loader and track its state. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const runId = useRef(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    runId.current += 1;
    const current = runId.current;
    let active = true;

    setLoading(true);
    loaderRef
      .current()
      .then((result) => {
        if (active && current === runId.current) {
          setDataState(result);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (active && current === runId.current) {
          setError(cause instanceof Error ? cause : new Error(String(cause)));
        }
      })
      .finally(() => {
        if (active && current === runId.current) setLoading(false);
      });

    return () => {
      active = false;
    };
    // The caller owns the dependency list. `nonce` is what makes reload work.
  }, [...deps, nonce]);

  const setData = useCallback((next: T | ((current: T | null) => T)) => {
    setDataState((current) =>
      typeof next === 'function' ? (next as (value: T | null) => T)(current) : next,
    );
  }, []);

  return { data, error, loading, reload: () => setNonce((value) => value + 1), setData };
}

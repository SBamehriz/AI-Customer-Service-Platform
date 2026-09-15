import { useCallback, useState } from 'react';

/** State mirrored into localStorage. */
export function useLocalStorage<T>(key: string, initial: T): [T, (value: T) => void] {
  const [stored, setStored] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (value: T) => {
      setStored(value);
      try {
        window.localStorage.setItem(key, JSON.stringify(value));
      } catch {
        // Preference simply will not persist this session.
      }
    },
    [key],
  );

  return [stored, set];
}

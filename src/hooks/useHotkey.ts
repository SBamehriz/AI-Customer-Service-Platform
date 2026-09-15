import { useEffect, useRef } from 'react';

export interface HotkeyOptions {
  /** Fire even while a text field has focus. Off by default. */
  allowInInput?: boolean;
  enabled?: boolean;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  );
}

/** Bind a keyboard shortcut. */
export function useHotkey(combo: string, handler: (event: KeyboardEvent) => void, options: HotkeyOptions = {}) {
  const { allowInInput = false, enabled = true } = options;
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!enabled) return;

    const parts = combo.toLowerCase().split('+');
    const key = parts[parts.length - 1];
    const needsMod = parts.includes('mod');
    const needsShift = parts.includes('shift');

    const onKeyDown = (event: KeyboardEvent) => {
      if (!allowInInput && isTypingTarget(event.target)) return;
      const mod = event.metaKey || event.ctrlKey;
      if (needsMod !== mod) return;
      if (needsShift !== event.shiftKey) return;
      if (event.key.toLowerCase() !== key) return;
      event.preventDefault();
      handlerRef.current(event);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [combo, allowInInput, enabled]);
}

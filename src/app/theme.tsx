/** Theme selection. */

import * as React from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'ucsp.theme';

interface ThemeState {
  choice: ThemeChoice;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = React.createContext<ThemeState | null>(null);

function readChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
  } catch {
    // Fall through to the default.
  }
  return 'system';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [choice, setChoiceState] = React.useState<ThemeChoice>(readChoice);

  React.useEffect(() => {
    const root = document.documentElement;
    if (choice === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', choice);
    try {
      window.localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // The preference will not persist, but the current page still respects it.
    }
  }, [choice]);

  const value = React.useMemo(() => ({ choice, setChoice: setChoiceState }), [choice]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const context = React.useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used inside <ThemeProvider>');
  return context;
}

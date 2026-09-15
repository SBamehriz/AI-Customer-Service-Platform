import * as React from 'react';
import { AlertTriangle, Check, Info, X } from '@/components/icons';
import { cn } from '@/lib/utils';

type ToastTone = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = React.createContext<ToastApi | null>(null);

/** Long enough to read a sentence, short enough not to nag. */
const DISMISS_AFTER = 4000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const nextId = React.useRef(0);

  const push = React.useCallback((tone: ToastTone, message: string) => {
    nextId.current += 1;
    const id = nextId.current;
    setToasts((current) => [...current, { id, tone, message }]);
    setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), DISMISS_AFTER);
  }, []);

  const api = React.useMemo<ToastApi>(
    () => ({
      success: (message) => push('success', message),
      error: (message) => push('error', message),
      info: (message) => push('info', message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'animate-fade-up pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3.5 py-3',
              'bg-surface shadow-lg',
              toast.tone === 'error' ? 'border-danger/40' : 'border-line',
            )}
          >
            <span
              className={cn(
                'mt-0.5 shrink-0',
                toast.tone === 'success' && 'text-success',
                toast.tone === 'error' && 'text-danger',
                toast.tone === 'info' && 'text-accent',
              )}
            >
              {toast.tone === 'success' ? (
                <Check className="h-4 w-4" />
              ) : toast.tone === 'error' ? (
                <AlertTriangle className="h-4 w-4" />
              ) : (
                <Info className="h-4 w-4" />
              )}
            </span>
            <p className="min-w-0 flex-1 text-sm text-ink">{toast.message}</p>
            <button
              type="button"
              onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}
              className="shrink-0 text-ink-muted transition-colors hover:text-ink"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = React.useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside <ToastProvider>');
  return context;
}

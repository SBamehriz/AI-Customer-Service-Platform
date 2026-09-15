import * as React from 'react';
import { X } from '@/components/icons';
import { cn } from '@/lib/utils';
import { Button } from './Button';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

const SIZES = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl' };

/** A centred dialog. */
export function Modal({ open, onClose, title, description, children, footer, size = 'md' }: ModalProps) {
  const panelRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/25 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={cn(
          'animate-fade-up relative w-full overflow-hidden rounded-xl border border-line',
          'bg-surface shadow-xl outline-none',
          SIZES[size],
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line-subtle px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-ink">{title}</h2>
            {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </header>
        <div className="scroll-slim max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <footer className="flex justify-end gap-2 border-t border-line-subtle bg-sunken/50 px-5 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}

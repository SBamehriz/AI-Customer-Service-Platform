import * as React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from '@/components/icons';
import { Wordmark } from '@/components/brand/Logo';

export interface AuthShellProps {
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}

/** Centred single column frame shared by sign in and registration. */
export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="relative flex min-h-dvh flex-col bg-bg">
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-50" aria-hidden="true" />

      <header className="relative flex h-14 items-center justify-between px-4 sm:px-6">
        <Link to="/">
          <Wordmark />
        </Link>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </Link>
      </header>

      <main className="relative flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-semibold text-ink">{title}</h1>
            {subtitle ? <p className="mt-2 text-base text-ink-secondary">{subtitle}</p> : null}
          </div>
          <div className="rounded-xl border border-line bg-surface p-5 shadow-md sm:p-6">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}

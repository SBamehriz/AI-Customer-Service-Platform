import * as React from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Headphones, ShieldCheck, UserCog } from '@/components/icons';
import { Button, Field, Input, useToast } from '@/components/ui';
import { AuthShell } from './AuthShell';
import { useSession } from '@/app/session';
import { cn } from '@/lib/utils';

const DEMO_ROLES = [
  {
    role: 'supervisor' as const,
    name: 'Priya Raman',
    title: 'Supervisor',
    blurb: 'The full operations view, analytics, knowledge, routing and SLAs.',
    icon: ShieldCheck,
  },
  {
    role: 'agent' as const,
    name: 'Marcus Oyelaran',
    title: 'Agent',
    blurb: 'The daily work, queue, inbox, tickets and Tap AI.',
    icon: Headphones,
  },
  {
    role: 'owner' as const,
    name: 'Dana Whitfield',
    title: 'Owner',
    blurb: 'Everything a supervisor sees, plus workspace and API keys.',
    icon: UserCog,
  },
];

export default function LoginPage() {
  const { status, mode, demoData, configured, signIn, signInDemo } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();

  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [pending, setPending] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const destination = (location.state as { from?: string } | null)?.from ?? '/app';

  if (status === 'authenticated') return <Navigate to={destination} replace />;

  const enterAs = async (role: 'owner' | 'supervisor' | 'agent') => {
    setPending(role);
    setError(null);
    try {
      await signInDemo(role);
      navigate(destination, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in');
    } finally {
      setPending(null);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending('form');
    setError(null);
    try {
      await signIn(email, password);
      toast.success('Signed in');
      navigate(destination, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in');
    } finally {
      setPending(null);
    }
  };

  return (
    <AuthShell
      title="Sign in"
      subtitle={
        mode === 'demo'
          ? 'No backend is connected, so this runs on the sample workspace. Pick a role to look around.'
          : demoData
            ? 'Sign in, or pick a demo role to look around.'
            : 'Sign in to your workspace.'
      }
    >
      {/* Only offer the one click roles when those accounts actually exist.
          On a real install the demo is not seeded, and buttons that always
          fail are worse than no buttons. */}
      {demoData ? (
      <div className="space-y-2.5">
        {DEMO_ROLES.map(({ role, name, title, blurb, icon: Icon }) => (
          <button
            key={role}
            type="button"
            onClick={() => enterAs(role)}
            disabled={pending !== null}
            className={cn(
              'group flex w-full items-center gap-3 rounded-lg border border-line bg-surface px-3.5 py-3 text-left',
              'transition-[border-color,box-shadow,background-color] duration-150',
              'hover:border-accent-border hover:bg-accent-soft/40 disabled:opacity-60',
            )}
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
              <Icon className="h-[18px] w-[18px]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-base font-medium text-ink">
                Continue as {title}
                <span className="ml-1.5 font-normal text-ink-muted">· {name}</span>
              </span>
              <span className="block truncate text-xs text-ink-muted">{blurb}</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-ink-muted transition-transform duration-150 group-hover:translate-x-0.5" />
          </button>
        ))}
      </div>
      ) : null}

      {demoData ? (
        <div className="my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-line" />
          <span className="text-xs text-ink-muted">or use an account</span>
          <span className="h-px flex-1 bg-line" />
        </div>
      ) : null}

      <form onSubmit={submit} className="space-y-4">
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </Field>
        <Field label="Password" htmlFor="password" error={error}>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="••••••••"
          />
        </Field>
        <Button type="submit" variant="primary" className="w-full" loading={pending === 'form'}>
          Sign in
        </Button>
      </form>

      {configured ? (
        <p className="mt-6 text-center text-sm text-ink-muted">
          No workspace yet?{' '}
          <Link to="/register" className="font-medium text-accent-text hover:underline">
            Create one
          </Link>
        </p>
      ) : (
        <div className="mt-6 space-y-2.5 border-t border-line pt-5 text-center">
          <p className="text-sm text-ink-secondary">
            First time here. Nothing has been set up on this install yet.
          </p>
          <Link to="/register" className="block">
            <Button variant="secondary" className="w-full">
              Create the first workspace
            </Button>
          </Link>
        </div>
      )}
    </AuthShell>
  );
}

import * as React from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Button, Field, Input, useToast } from '@/components/ui';
import { AuthShell } from './AuthShell';
import { useSession } from '@/app/session';

export default function RegisterPage() {
  const { status, mode, signUp } = useSession();
  const navigate = useNavigate();
  const toast = useToast();

  const [form, setForm] = React.useState({
    workspaceName: '',
    name: '',
    email: '',
    password: '',
  });
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  if (status === 'authenticated') return <Navigate to="/app" replace />;

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (form.password.length < 8) {
      setError('Use at least 8 characters');
      return;
    }
    setPending(true);
    setError(null);
    try {
      await signUp(form);
      toast.success(`Created the workspace ${form.workspaceName}`);
      navigate('/app', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create the workspace');
    } finally {
      setPending(false);
    }
  };

  return (
    <AuthShell
      title="Create a workspace"
      subtitle={
        mode === 'demo'
          ? 'No backend is connected, so this walks through the flow against the sample workspace.'
          : 'You become the owner of the new workspace.'
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Company name" htmlFor="workspaceName">
          <Input
            id="workspaceName"
            required
            minLength={2}
            value={form.workspaceName}
            onChange={update('workspaceName')}
            placeholder="Meridian Outfitters"
          />
        </Field>
        <Field label="Your name" htmlFor="name">
          <Input id="name" required value={form.name} onChange={update('name')} placeholder="Dana Whitfield" />
        </Field>
        <Field label="Work email" htmlFor="email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={update('email')}
            placeholder="you@company.com"
          />
        </Field>
        <Field
          label="Password"
          htmlFor="password"
          hint="At least 8 characters."
          error={error}
        >
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={form.password}
            onChange={update('password')}
          />
        </Field>
        <Button type="submit" variant="primary" className="w-full" loading={pending}>
          Create workspace
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-muted">
        Already have one?{' '}
        <Link to="/login" className="font-medium text-accent-text hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}

import * as React from 'react';
import { Save } from '@/components/icons';
import {
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Skeleton,
  Switch,
  Textarea,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';
import type { WorkspaceSettings as Settings } from '@/lib/types';

/** Identity and AI behaviour, the two things that change what customers see. */
export function WorkspaceSettings() {
  const api = useApi();
  const toast = useToast();
  const { refreshWorkspace } = useSession();

  const workspace = useAsync(() => api.getWorkspace(), [api]);
  const [name, setName] = React.useState('');
  const [settings, setSettings] = React.useState<Settings | null>(null);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (workspace.data) {
      setName(workspace.data.name);
      setSettings(workspace.data.settings);
    }
  }, [workspace.data]);

  if (workspace.loading || !settings) {
    return <Skeleton className="h-96" />;
  }

  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setSettings((current) => (current ? { ...current, [key]: value } : current));

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateWorkspace({ name, settings });
      refreshWorkspace(updated);
      toast.success('Settings saved');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Identity" description="How the workspace introduces itself." />
        <div className="space-y-4">
          <Field label="Company name" htmlFor="ws-name">
            <Input id="ws-name" value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field
            label="Greeting"
            htmlFor="ws-greeting"
            hint="First line a customer sees in the widget and the portal."
          >
            <Input
              id="ws-greeting"
              value={settings.greeting}
              onChange={(event) => set('greeting', event.target.value)}
            />
          </Field>
          <Field
            label="Brand voice"
            htmlFor="ws-voice"
            hint="Describe the tone the way you would to a new hire."
          >
            <Textarea
              id="ws-voice"
              value={settings.brandVoice}
              onChange={(event) => set('brandVoice', event.target.value)}
            />
          </Field>
          <Field
            label="Extra instructions"
            htmlFor="ws-instructions"
            hint="Rules that apply to every reply. Kept short, they are followed more reliably."
          >
            <Textarea
              id="ws-instructions"
              value={settings.instructions}
              onChange={(event) => set('instructions', event.target.value)}
              placeholder="Always ask for the order number before promising anything."
            />
          </Field>
          <Field label="Business hours" htmlFor="ws-hours">
            <Input
              id="ws-hours"
              value={settings.businessHours}
              onChange={(event) => set('businessHours', event.target.value)}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="AI behaviour"
          description="When the assistant answers, and when it hands over."
        />
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4 rounded-lg border border-line px-3.5 py-3">
            <div className="min-w-0">
              <p className="text-base font-medium text-ink">Answer customers automatically</p>
              <p className="mt-0.5 text-sm text-ink-muted">
                When off, the assistant still drafts replies for agents but never sends one itself.
              </p>
            </div>
            <Switch
              checked={settings.aiAutoreply}
              onChange={(value) => set('aiAutoreply', value)}
              label="Answer customers automatically"
            />
          </div>

          <ThresholdField
            id="ws-suggest"
            label="Confidence needed to answer"
            hint="Below this, the conversation is handed to a human instead. Confidence measures how well your knowledge base covered the question."
            value={settings.aiSuggestThreshold}
            onChange={(value) => set('aiSuggestThreshold', value)}
          />

          <Field
            label="Escalate after this many AI replies"
            htmlFor="ws-turns"
            hint="A conversation that has gone back and forth this many times is not going to resolve itself."
          >
            <Input
              id="ws-turns"
              type="number"
              min={1}
              max={10}
              value={settings.escalateAfterAiTurns}
              onChange={(event) => set('escalateAfterAiTurns', Number(event.target.value))}
            />
          </Field>

          <Field
            label="Hand-over message"
            htmlFor="ws-fallback"
            hint="Sent when the assistant escalates."
          >
            <Input
              id="ws-fallback"
              value={settings.fallbackMessage}
              onChange={(event) => set('fallbackMessage', event.target.value)}
            />
          </Field>
        </div>
      </Card>

      <div className="flex justify-end">
        <Button variant="primary" onClick={save} loading={saving} icon={<Save className="h-4 w-4" />}>
          Save changes
        </Button>
      </div>
    </div>
  );
}

function ThresholdField({
  id,
  label,
  hint,
  value,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <div className="flex items-center gap-3">
        <input
          id={id}
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-line-strong accent-[var(--accent)]"
        />
        <span className="numeric w-12 text-right text-base font-medium text-ink">
          {Math.round(value * 100)}%
        </span>
      </div>
    </Field>
  );
}

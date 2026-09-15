import * as React from 'react';
import { Info, Zap } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Skeleton,
  Switch,
  useToast,
} from '@/components/ui';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import type { AutopilotRun, WorkspaceSettings } from '@/lib/types';

/** Working the queue without anybody watching. */
export function AutopilotCard() {
  const api = useApi();
  const toast = useToast();
  const status = useAsync(() => api.getAutopilot(), [api]);
  const workspace = useAsync(() => api.getWorkspace(), [api]);
  const [settings, setSettings] = React.useState<WorkspaceSettings | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [lastRun, setLastRun] = React.useState<AutopilotRun | null>(null);

  React.useEffect(() => {
    if (workspace.data) setSettings(workspace.data.settings);
  }, [workspace.data]);

  const onChange = <K extends keyof WorkspaceSettings>(key: K, value: WorkspaceSettings[K]) =>
    setSettings((current) => (current ? { ...current, [key]: value } : current));

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await api.updateWorkspace({ settings });
      status.reload();
      toast.success('Saved');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    setRunning(true);
    try {
      const result = await api.runAutopilot();
      setLastRun(result);
      toast.success(
        result.answered > 0
          ? `Answered ${result.answered} of ${result.lookedAt}`
          : `Looked at ${result.lookedAt}, answered none`,
      );
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not run it');
    } finally {
      setRunning(false);
    }
  };

  if (status.loading || !settings) return <Skeleton className="h-72" />;

  return (
    <Card>
      <CardHeader
        title="Autopilot"
        description="Goes back over conversations that are sitting waiting and answers the ones it can answer well."
        action={
          <Badge tone={settings.autopilotEnabled ? 'success' : 'neutral'}>
            {settings.autopilotEnabled ? 'Scheduled' : 'Off'}
          </Badge>
        }
      />

      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={run}
            disabled={running}
            icon={<Zap className="h-4 w-4" />}
          >
            {running ? 'Working the queue' : 'Run once now'}
          </Button>
          {lastRun ? (
            <p className="text-sm text-ink-secondary">
              Looked at {lastRun.lookedAt}, answered {lastRun.answered}, left{' '}
              {lastRun.escalated} for a person.
            </p>
          ) : (
            <p className="text-sm text-ink-muted">
              Try this before scheduling it, so you can see what it does.
            </p>
          )}
        </div>

        <div className="flex items-start gap-3">
          <Switch
            checked={Boolean(settings.autopilotEnabled)}
            onChange={(next) => onChange('autopilotEnabled', next)}
            label="Run on a schedule"
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">Run on a schedule</p>
            <p className="text-xs text-ink-muted">
              At the hours below, without anybody pressing anything.
            </p>
          </div>
        </div>

        <Field
          label="Hours, in UTC"
          htmlFor="autopilot-hours"
          hint="A range like 22-6 for overnight, a list like 9,13,17, or both. Leave empty and it never runs by itself."
        >
          <Input
            id="autopilot-hours"
            value={settings.autopilotHours ?? ''}
            onChange={(event) => onChange('autopilotHours', event.target.value)}
            placeholder="22-6"
            disabled={!settings.autopilotEnabled}
          />
        </Field>

        <p className="flex gap-2.5 rounded-lg bg-sunken px-3 py-2.5 text-xs leading-relaxed text-ink-secondary">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            It only answers what your articles genuinely cover, at or above{' '}
            {Math.round((status.data?.confidenceThreshold ?? 0.4) * 100)}% confidence. It never
            touches a conversation somebody has picked up, and never replies twice without the
            customer writing back. Everything it sends is marked as automatic.
            {status.data && !status.data.modelConnected
              ? ' With no model connected it answers by quoting the matching article, which still works.'
              : ''}
          </span>
        </p>

        <div className="flex justify-end">
          <Button variant="primary" size="sm" onClick={save} disabled={saving}>
            {saving ? 'Saving' : 'Save schedule'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

/** Recording calls. */
export function CallRecordingCard() {
  const api = useApi();
  const toast = useToast();
  const workspace = useAsync(() => api.getWorkspace(), [api]);
  const [settings, setSettings] = React.useState<WorkspaceSettings | null>(null);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (workspace.data) setSettings(workspace.data.settings);
  }, [workspace.data]);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await api.updateWorkspace({ settings });
      toast.success('Saved');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  if (workspace.loading || !settings) return <Skeleton className="h-56" />;

  return (
    <Card>
      <CardHeader
        title="Call recording"
        description="Keeps the audio of Twilio calls alongside the transcript and the suggestions."
        action={
          <Badge tone={settings.recordCalls ? 'success' : 'neutral'}>
            {settings.recordCalls ? 'Recording' : 'Off'}
          </Badge>
        }
      />
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <Switch
            checked={Boolean(settings.recordCalls)}
            onChange={(next) =>
              setSettings((current) => (current ? { ...current, recordCalls: next } : current))
            }
            label="Record calls"
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">Record calls</p>
            <p className="text-xs text-ink-muted">Off unless you turn it on.</p>
          </div>
        </div>

        <Field
          label="What the caller hears first"
          htmlFor="recording-notice"
          hint="Played before recording starts. There is no way to record without it."
        >
          <Input
            id="recording-notice"
            value={settings.recordingNotice ?? ''}
            onChange={(event) =>
              setSettings((current) =>
                current ? { ...current, recordingNotice: event.target.value } : current,
              )
            }
            placeholder="This call may be recorded for quality and training purposes."
            disabled={!settings.recordCalls}
          />
        </Field>

        <p className="flex gap-2.5 rounded-lg bg-sunken px-3 py-2.5 text-xs leading-relaxed text-ink-secondary">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Recording people without telling them is against the law in many places, and the rules
            differ by country and by state. Check what applies where your callers are. Recordings
            are kept with the call and counted in the calls dataset.
          </span>
        </p>

        <div className="flex justify-end">
          <Button variant="primary" size="sm" onClick={save} disabled={saving}>
            {saving ? 'Saving' : 'Save'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

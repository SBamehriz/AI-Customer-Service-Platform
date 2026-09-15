import * as React from 'react';
import { Clock, Pencil, Plus, Trash2, Zap } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Modal,
  Skeleton,
  Textarea,
  priorityTone,
  useToast,
} from '@/components/ui';
import { AutopilotCard, CallRecordingCard } from './AutopilotCard';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import { duration } from '@/lib/format';
import type { Macro } from '@/lib/types';

/** Macros, SLA policies and routing rules, the three things that automate the queue. */
export function AutomationSettings() {
  const api = useApi();
  const toast = useToast();

  const macros = useAsync(() => api.listMacros(), [api]);
  const policies = useAsync(() => api.listSlaPolicies(), [api]);
  const rules = useAsync(() => api.listRoutingRules(), [api]);
  const [editing, setEditing] = React.useState<Macro | 'new' | null>(null);

  const remove = async (macro: Macro) => {
    try {
      await api.deleteMacro(macro.id);
      macros.setData((current) => (current ?? []).filter((item) => item.id !== macro.id));
      toast.success('Macro deleted');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not delete');
    }
  };

  return (
    <div className="space-y-4">
      <AutopilotCard />
      <CallRecordingCard />

      <Card flush>
        <div className="p-4">
          <CardHeader
            title="Saved replies"
            description="The answers your team types most often."
            action={
              <Button variant="secondary" size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setEditing('new')}>
                New
              </Button>
            }
          />
        </div>
        {macros.loading ? (
          <Skeleton className="mx-4 mb-4 h-32" />
        ) : (macros.data ?? []).length === 0 ? (
          <EmptyState title="No saved replies yet" />
        ) : (
          <ul className="divide-y divide-line-subtle border-t border-line-subtle">
            {(macros.data ?? []).map((macro) => (
              <li key={macro.id} className="flex items-start gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-base font-medium text-ink">{macro.name}</p>
                  <p className="mt-0.5 line-clamp-2 text-sm text-ink-muted">{macro.body}</p>
                  {macro.tags.length ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {macro.tags.map((tag) => (
                        <Badge key={tag} tone="neutral" className="px-1.5 py-0 text-[10px]">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="icon" onClick={() => setEditing(macro)} aria-label="Edit">
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => remove(macro)} aria-label="Delete">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card flush>
        <div className="p-4">
          <CardHeader
            title="Service levels"
            description="Deadlines applied to new tickets, by priority."
            action={<Clock className="h-4 w-4 text-ink-muted" />}
          />
        </div>
        {policies.loading ? (
          <Skeleton className="mx-4 mb-4 h-24" />
        ) : (policies.data ?? []).length === 0 ? (
          <EmptyState title="No policies yet" description="Without one, tickets have no deadline." />
        ) : (
          <ul className="divide-y divide-line-subtle border-t border-line-subtle">
            {(policies.data ?? []).map((policy) => (
              <li key={policy.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-base font-medium text-ink">{policy.name}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {policy.priorities.map((priority) => (
                      <Badge key={priority} tone={priorityTone(priority)} className="px-1.5 py-0 text-[10px]">
                        {priority}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex gap-5 text-sm">
                  <span className="text-ink-muted">
                    First reply{' '}
                    <span className="numeric font-medium text-ink">
                      {duration(policy.firstResponseMinutes)}
                    </span>
                  </span>
                  <span className="text-ink-muted">
                    Resolution{' '}
                    <span className="numeric font-medium text-ink">
                      {duration(policy.resolutionMinutes)}
                    </span>
                  </span>
                </div>
                <Badge tone={policy.isActive ? 'success' : 'neutral'}>
                  {policy.isActive ? 'Active' : 'Off'}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card flush>
        <div className="p-4">
          <CardHeader
            title="Routing rules"
            description="Evaluated in order on every new ticket. Later matches win."
            action={<Zap className="h-4 w-4 text-ink-muted" />}
          />
        </div>
        {rules.loading ? (
          <Skeleton className="mx-4 mb-4 h-24" />
        ) : (rules.data ?? []).length === 0 ? (
          <EmptyState title="No routing rules" description="Every ticket keeps its default priority." />
        ) : (
          <ul className="divide-y divide-line-subtle border-t border-line-subtle">
            {(rules.data ?? []).map((rule, index) => (
              <li key={rule.id} className="flex flex-wrap items-start gap-3 px-4 py-3">
                <span className="numeric mt-0.5 w-5 shrink-0 text-xs text-ink-muted">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-base font-medium text-ink">{rule.name}</p>
                  <p className="mt-1 font-mono text-xs text-ink-muted">
                    when {describe(rule.conditions)} → {describe(rule.actions)}
                  </p>
                </div>
                <Badge tone={rule.isActive ? 'success' : 'neutral'}>
                  {rule.isActive ? 'Active' : 'Off'}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <MacroModal
        open={editing !== null}
        macro={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          macros.reload();
          toast.success('Macro saved');
        }}
      />
    </div>
  );
}

function MacroModal({
  open,
  macro,
  onClose,
  onSaved,
}: {
  open: boolean;
  macro: Macro | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const api = useApi();
  const toast = useToast();
  const [form, setForm] = React.useState({ name: '', body: '', tags: '' });
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setForm(
      macro
        ? { name: macro.name, body: macro.body, tags: macro.tags.join(', ') }
        : { name: '', body: '', tags: '' },
    );
  }, [open, macro]);

  const submit = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await api.saveMacro({
        id: macro?.id,
        name: form.name.trim(),
        body: form.body,
        tags: form.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
      });
      onSaved();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save the macro');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={macro ? 'Edit saved reply' : 'New saved reply'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={saving} disabled={!form.name.trim()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Name" htmlFor="macro-name">
          <Input
            id="macro-name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="Return started"
            autoFocus
          />
        </Field>
        <Field label="Reply" htmlFor="macro-body">
          <Textarea
            id="macro-body"
            value={form.body}
            onChange={(event) => setForm({ ...form, body: event.target.value })}
            className="min-h-[140px]"
          />
        </Field>
        <Field label="Tags" htmlFor="macro-tags" hint="Comma separated.">
          <Input
            id="macro-tags"
            value={form.tags}
            onChange={(event) => setForm({ ...form, tags: event.target.value })}
          />
        </Field>
      </div>
    </Modal>
  );
}

/** Render a rule's condition or action object as a readable clause. */
function describe(record: Record<string, unknown>): string {
  const parts = Object.entries(record).map(([key, value]) => {
    const rendered = Array.isArray(value) ? value.join(' | ') : String(value);
    return `${key.replace(/_/g, ' ')}: ${rendered}`;
  });
  return parts.length ? parts.join(', ') : 'anything';
}

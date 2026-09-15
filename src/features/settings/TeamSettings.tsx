import * as React from 'react';
import { UserPlus } from '@/components/icons';
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  Field,
  Input,
  Select,
  Modal,
  Skeleton,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';
import type { Role, User } from '@/lib/types';

const ROLES: { value: Role; label: string; blurb: string }[] = [
  { value: 'agent', label: 'Agent', blurb: 'Answers customers and drafts knowledge articles.' },
  {
    value: 'supervisor',
    label: 'Supervisor',
    blurb: 'Also publishes articles and sets SLA, routing and channels.',
  },
  { value: 'owner', label: 'Owner', blurb: 'Everything, including the team and API keys.' },
];

/** The team, and what each person may do. */
export function TeamSettings() {
  const api = useApi();
  const toast = useToast();
  const { user: me } = useSession();
  const team = useAsync(() => api.listTeam(), [api]);
  const [adding, setAdding] = React.useState(false);

  const isOwner = me?.role === 'owner';

  const change = async (member: User, patch: { role?: Role; isActive?: boolean }) => {
    try {
      const updated = await api.updateTeamMember(member.id, patch);
      team.setData((current) =>
        (current ?? []).map((row) => (row.id === updated.id ? updated : row)),
      );
      toast.success(`${updated.name} updated`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not update');
    }
  };

  if (team.error) return <ErrorState error={team.error} onRetry={team.reload} />;
  if (team.loading) return <Skeleton className="h-96" />;

  const members = team.data ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Team"
          description="Who can sign in, and what each of them is allowed to change."
          action={
            <Button
              variant="primary"
              size="sm"
              icon={<UserPlus className="h-4 w-4" />}
              onClick={() => setAdding(true)}
            >
              Add someone
            </Button>
          }
        />

        <ul className="divide-y divide-line-subtle">
          {members.map((member) => {
            const isMe = member.id === me?.id;
            const locked = isMe || (member.role === 'owner' && !isOwner);
            return (
              <li key={member.id} className="flex flex-wrap items-center gap-3 py-3">
                <Avatar name={member.name} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">
                    {member.name}
                    {isMe ? <span className="ml-2 text-2xs text-ink-muted">you</span> : null}
                  </p>
                  <p className="truncate text-2xs text-ink-muted">{member.email}</p>
                </div>

                {member.isActive ? null : <Badge tone="neutral">Switched off</Badge>}

                <Select
                  aria-label={`Role for ${member.name}`}
                  value={member.role}
                  disabled={locked}
                  onChange={(event) => change(member, { role: event.target.value as Role })}
                  className="w-36"
                >
                  {ROLES.filter((role) => role.value !== 'owner' || isOwner).map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </Select>

                <Button
                  variant="ghost"
                  size="sm"
                  disabled={locked}
                  onClick={() => change(member, { isActive: !member.isActive })}
                >
                  {member.isActive ? 'Switch off' : 'Switch on'}
                </Button>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <CardHeader title="What the roles mean" description="The server enforces all of this." />
        <dl className="space-y-2.5">
          {ROLES.map((role) => (
            <div key={role.value} className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="w-24 shrink-0 text-sm font-medium text-ink">{role.label}</dt>
              <dd className="flex-1 text-sm text-ink-secondary">{role.blurb}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {adding ? (
        <AddMember
          canMakeOwner={isOwner}
          onClose={() => setAdding(false)}
          onAdded={(member) => {
            team.setData((current) => [...(current ?? []), member]);
            setAdding(false);
          }}
        />
      ) : null}
    </div>
  );
}

function AddMember({
  canMakeOwner,
  onClose,
  onAdded,
}: {
  canMakeOwner: boolean;
  onClose: () => void;
  onAdded: (member: User) => void;
}) {
  const api = useApi();
  const toast = useToast();
  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [role, setRole] = React.useState<Role>('agent');
  const [saving, setSaving] = React.useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      onAdded(await api.addTeamMember({ name, email, password, role }));
      toast.success(`${name} can now sign in`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not add them');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Add someone to the team">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name" htmlFor="member-name">
          <Input
            id="member-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </Field>
        <Field label="Email" htmlFor="member-email">
          <Input
            id="member-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </Field>
        <Field
          label="First password"
          htmlFor="member-password"
          hint="There is no mail server here, so hand this over yourself. They can change it later."
        >
          <Input
            id="member-password"
            type="text"
            value={password}
            minLength={8}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </Field>
        <Field label="Role" htmlFor="member-role">
          <Select
            id="member-role"
            value={role}
            onChange={(event) => setRole(event.target.value as Role)}
          >
            {ROLES.filter((entry) => entry.value !== 'owner' || canMakeOwner).map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </Select>
        </Field>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Adding' : 'Add to team'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Inbox, PhoneCall, Sparkles } from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, ErrorState, SkeletonRows, priorityTone, statusTone } from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';
import { CHANNEL_LABELS, relativeTime, STATUS_LABELS, timeUntil } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Conversation, Ticket } from '@/lib/types';

/** The agent home. */
export default function AgentHome() {
  const api = useApi();
  const { user } = useSession();

  const conversations = useAsync(() => api.listConversations({ assigned: 'me' }), [api]);
  const tickets = useAsync(() => api.listTickets({ assigned: 'me' }), [api]);

  const loading = conversations.loading || tickets.loading;
  const error = conversations.error ?? tickets.error;

  const openTickets = (tickets.data ?? []).filter(
    (ticket) => ticket.status !== 'solved' && ticket.status !== 'closed',
  );
  const dueSoon = openTickets.filter((ticket) => {
    if (!ticket.slaDueAt) return false;
    const remaining = new Date(ticket.slaDueAt).getTime() - Date.now();
    return remaining < 2 * 3_600_000;
  });
  const resolvedToday = (tickets.data ?? []).filter(
    (ticket) =>
      ticket.resolvedAt && new Date(ticket.resolvedAt).toDateString() === new Date().toDateString(),
  );

  const resume = [...(conversations.data ?? [])]
    .filter((conversation) => conversation.status !== 'resolved')
    .sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime())[0];

  const queue = [...openTickets].sort((a, b) => {
    const left = a.slaDueAt ? new Date(a.slaDueAt).getTime() : Number.MAX_SAFE_INTEGER;
    const right = b.slaDueAt ? new Date(b.slaDueAt).getTime() : Number.MAX_SAFE_INTEGER;
    return left - right;
  });

  return (
    <Page className="space-y-5">
      <PageHeader
        title={`${greeting()}, ${user?.name?.split(' ')[0] ?? 'there'}`}
        description="Everything assigned to you, deadline first."
        actions={
          <Link to="/app/tap">
            <Button variant="secondary" icon={<PhoneCall className="h-4 w-4" />}>
              Start a call
            </Button>
          </Link>
        }
      />

      {error ? (
        <Card>
          <ErrorState error={error} onRetry={conversations.reload} />
        </Card>
      ) : loading ? (
        <SkeletonRows rows={4} />
      ) : (
        <>
          <ResumeCard conversation={resume} />

          <div className="grid gap-3 sm:grid-cols-3">
            <MiniStat label="Open on you" value={openTickets.length} icon={Inbox} />
            <MiniStat
              label="Due within 2 hours"
              value={dueSoon.length}
              icon={Clock}
              tone={dueSoon.length > 0 ? 'danger' : 'neutral'}
            />
            <MiniStat label="Resolved today" value={resolvedToday.length} icon={Sparkles} tone="success" />
          </div>

          <Card flush>
            <div className="px-4 pt-4">
              <CardHeader
                title="Your queue"
                description={`${queue.length} open ${queue.length === 1 ? 'ticket' : 'tickets'}, soonest deadline first`}
                action={
                  <Link to="/app/tickets?assigned=me">
                    <Button variant="ghost" size="sm">
                      View all
                    </Button>
                  </Link>
                }
              />
            </div>
            {queue.length === 0 ? (
              <EmptyState
                title="Queue is clear"
                description="Nothing assigned to you is open right now."
              />
            ) : (
              <ul className="divide-y divide-line-subtle border-t border-line-subtle">
                {queue.slice(0, 8).map((ticket) => (
                  <QueueRow key={ticket.id} ticket={ticket} />
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}

function ResumeCard({ conversation }: { conversation: Conversation | undefined }) {
  if (!conversation) {
    return (
      <Card>
        <EmptyState
          title="Nothing in progress"
          description="When a conversation is assigned to you it shows up here so you can pick straight back up."
          action={
            <Link to="/app/inbox">
              <Button variant="primary" size="sm">
                Open the inbox
              </Button>
            </Link>
          }
        />
      </Card>
    );
  }

  const latest = [...conversation.messages].reverse().find((message) => !message.isPrivate);

  return (
    <Link to={`/app/inbox?conversation=${conversation.id}`} className="block">
      <Card className="group transition-[border-color,box-shadow] duration-150 hover:border-accent-border hover:shadow-md">
        <div className="flex items-start gap-3.5">
          <Avatar name={conversation.customer?.name} size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-2xs font-semibold uppercase tracking-wide text-accent-text">
                Continue where you left off
              </p>
              <Badge tone={statusTone(conversation.status)}>
                {STATUS_LABELS[conversation.status] ?? conversation.status}
              </Badge>
            </div>
            <h2 className="mt-1 truncate text-lg font-semibold text-ink">
              {conversation.subject ?? 'Conversation'}
            </h2>
            <p className="mt-0.5 text-sm text-ink-muted">
              {conversation.customer?.name ?? 'Unknown'} · {CHANNEL_LABELS[conversation.channel]} ·{' '}
              {relativeTime(conversation.lastMessageAt)}
            </p>
            {latest ? (
              <p className="mt-2.5 line-clamp-2 rounded-md bg-sunken px-3 py-2 text-sm text-ink-secondary">
                {latest.body}
              </p>
            ) : null}
          </div>
          <ArrowRight className="mt-1 h-5 w-5 shrink-0 text-ink-muted transition-transform duration-150 group-hover:translate-x-0.5" />
        </div>
      </Card>
    </Link>
  );
}

function MiniStat({
  label,
  value,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  tone?: 'neutral' | 'danger' | 'success';
}) {
  return (
    <Card className="flex items-center gap-3">
      <span
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
          tone === 'danger'
            ? 'bg-danger-soft text-danger'
            : tone === 'success'
              ? 'bg-success-soft text-success'
              : 'bg-sunken text-ink-secondary',
        )}
      >
        <Icon className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0">
        <p className="numeric text-2xl font-semibold leading-none text-ink">{value}</p>
        <p className="mt-1 truncate text-sm text-ink-muted">{label}</p>
      </div>
    </Card>
  );
}

function QueueRow({ ticket }: { ticket: Ticket }) {
  const sla = timeUntil(ticket.slaDueAt);
  return (
    <li>
      <Link
        to={`/app/tickets?ticket=${ticket.id}`}
        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-hover"
      >
        <span className="numeric w-12 shrink-0 text-xs text-ink-muted">#{ticket.number}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-base text-ink">{ticket.subject}</span>
          <span className="block truncate text-xs text-ink-muted">
            {ticket.customer?.name ?? 'Unknown'} · {CHANNEL_LABELS[ticket.channel]}
          </span>
        </span>
        <Badge tone={priorityTone(ticket.priority)} className="hidden sm:inline-flex">
          {ticket.priority}
        </Badge>
        <span
          className={cn(
            'numeric w-16 shrink-0 text-right text-xs font-medium',
            sla.overdue ? 'text-danger' : sla.urgent ? 'text-warning' : 'text-ink-muted',
          )}
        >
          {sla.label}
        </span>
      </Link>
    </li>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

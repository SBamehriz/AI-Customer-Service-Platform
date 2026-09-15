import * as React from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Building2, Mail, Phone, Ticket } from '@/components/icons';
import { Avatar, Badge, Spinner, priorityTone, statusTone } from '@/components/ui';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import { formatDate, relativeTime, STATUS_LABELS } from '@/lib/format';
import type { Conversation, SearchHit } from '@/lib/types';

export interface ContextPanelProps {
  conversation: Conversation;
}

/** Everything an agent needs beside the thread. */
export function ContextPanel({ conversation }: ContextPanelProps) {
  const api = useApi();
  const customer = conversation.customer;

  const latestQuestion = React.useMemo(() => {
    const message = [...conversation.messages]
      .reverse()
      .find((item) => item.authorType === 'customer' && !item.isPrivate);
    return message?.body ?? conversation.subject ?? '';
  }, [conversation]);

  const suggestions = useAsync<SearchHit[]>(
    () => (latestQuestion ? api.searchKnowledge(latestQuestion) : Promise.resolve([])),
    [api, latestQuestion],
  );

  const history = useAsync(
    () => (customer ? api.customerTickets(customer.id) : Promise.resolve([])),
    [api, customer?.id],
  );

  const tickets = history.data ?? [];
  const openTickets = tickets.filter(
    (ticket) => ticket.status !== 'solved' && ticket.status !== 'closed',
  ).length;

  return (
    <aside className="scroll-slim hidden w-[300px] shrink-0 overflow-y-auto border-l border-line bg-surface xl:block">
      <section className="border-b border-line-subtle p-4">
        <div className="flex items-center gap-3">
          <Avatar name={customer?.name} size="lg" />
          <div className="min-w-0">
            <p className="truncate text-md font-semibold text-ink">{customer?.name ?? 'Unknown'}</p>
            <p className="truncate text-xs text-ink-muted">
              Seen {customer ? relativeTime(customer.lastSeenAt) : 'never'}
            </p>
          </div>
        </div>
        <dl className="mt-3.5 space-y-2 text-sm">
          {customer?.email ? (
            <Row icon={<Mail className="h-3.5 w-3.5" />} value={customer.email} />
          ) : null}
          {customer?.phone ? (
            <Row icon={<Phone className="h-3.5 w-3.5" />} value={customer.phone} />
          ) : null}
          {customer?.company ? (
            <Row icon={<Building2 className="h-3.5 w-3.5" />} value={customer.company} />
          ) : null}
        </dl>
        {customer ? (
          <div className="mt-3.5 grid grid-cols-2 gap-2">
            <Stat label="Total tickets" value={tickets.length} />
            <Stat label="Open" value={openTickets} />
          </div>
        ) : null}
      </section>

      <section className="border-b border-line-subtle p-4">
        <h3 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          <BookOpen className="h-3.5 w-3.5" />
          Suggested articles
        </h3>
        {suggestions.loading ? (
          <Spinner />
        ) : (suggestions.data ?? []).length === 0 ? (
          <p className="text-sm text-ink-muted">
            Nothing in the knowledge base matches this yet, which makes it a good candidate for
            a new article.
          </p>
        ) : (
          <ul className="space-y-2">
            {(suggestions.data ?? []).slice(0, 3).map((hit) => (
              <li key={hit.articleId}>
                <Link
                  to={`/app/knowledge?article=${hit.articleId}`}
                  className="block rounded-md border border-line px-2.5 py-2 transition-colors hover:border-accent-border hover:bg-accent-soft/40"
                >
                  <p className="truncate text-sm font-medium text-ink">{hit.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{hit.excerpt}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="p-4">
        <h3 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          <Ticket className="h-3.5 w-3.5" />
          Ticket history
        </h3>
        {history.loading ? (
          <Spinner />
        ) : tickets.length === 0 ? (
          <p className="text-sm text-ink-muted">First contact.</p>
        ) : (
          <ul className="space-y-1.5">
            {tickets.slice(0, 6).map((ticket) => (
              <li key={ticket.id}>
                <Link
                  to={`/app/tickets?ticket=${ticket.id}`}
                  className="block rounded-md px-2 py-1.5 transition-colors hover:bg-hover"
                >
                  <div className="flex items-center gap-2">
                    <span className="numeric shrink-0 text-2xs text-ink-muted">#{ticket.number}</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{ticket.subject}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Badge tone={statusTone(ticket.status)} className="px-1.5 py-0 text-[10px]">
                      {STATUS_LABELS[ticket.status] ?? ticket.status}
                    </Badge>
                    <Badge tone={priorityTone(ticket.priority)} className="px-1.5 py-0 text-[10px]">
                      {ticket.priority}
                    </Badge>
                    <span className="text-2xs text-ink-muted">{formatDate(ticket.createdAt)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

function Row({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <div className="flex items-center gap-2 text-ink-secondary">
      <span className="shrink-0 text-ink-muted">{icon}</span>
      <span className="min-w-0 truncate">{value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-sunken px-2.5 py-2">
      <p className="numeric text-lg font-semibold leading-none text-ink">{value}</p>
      <p className="mt-1 text-2xs text-ink-muted">{label}</p>
    </div>
  );
}

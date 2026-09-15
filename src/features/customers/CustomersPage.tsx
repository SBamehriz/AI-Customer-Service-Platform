import * as React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Building2, Mail, Phone, Search, Users } from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import {
  Avatar,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Input,
  SkeletonRows,
  priorityTone,
  statusTone,
} from '@/components/ui';
import { ChannelIcon } from '@/features/inbox/ChannelIcon';
import { useApi } from '@/app/session';
import { useAsync, useDebounced } from '@/hooks';
import { CHANNEL_LABELS, formatDate, relativeTime, STATUS_LABELS } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Channel, Customer } from '@/lib/types';

/** One record per person, with the channels they have used and their full history. */
export default function CustomersPage() {
  const api = useApi();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = React.useState('');
  const debounced = useDebounced(search, 250);

  const customers = useAsync(() => api.listCustomers(debounced || undefined), [api, debounced]);
  const selectedId = params.get('customer');
  const rows = customers.data ?? [];
  const selected = rows.find((customer) => customer.id === selectedId) ?? rows[0] ?? null;

  const history = useAsync(
    () => (selected ? api.customerTickets(selected.id) : Promise.resolve([])),
    [api, selected?.id],
  );

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('customer', id);
    setParams(next);
  };

  return (
    <Page className="space-y-4">
      <PageHeader
        title="Customers"
        description="Deduplicated across every channel by email and phone number."
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <Card flush className="h-fit overflow-hidden">
          <div className="border-b border-line-subtle p-3">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name, email or company"
              leading={<Search className="h-4 w-4" />}
              aria-label="Search customers"
            />
          </div>
          {customers.error ? (
            <ErrorState error={customers.error} onRetry={customers.reload} />
          ) : customers.loading ? (
            <SkeletonRows rows={7} className="p-3" />
          ) : rows.length === 0 ? (
            <EmptyState icon={<Users className="h-5 w-5" />} title="No customers match" />
          ) : (
            <ul className="scroll-slim max-h-[70vh] divide-y divide-line-subtle overflow-y-auto">
              {rows.map((customer) => (
                <li key={customer.id}>
                  <button
                    type="button"
                    onClick={() => select(customer.id)}
                    aria-current={customer.id === selected?.id}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors duration-100',
                      customer.id === selected?.id ? 'bg-accent-soft' : 'hover:bg-hover',
                    )}
                  >
                    <Avatar name={customer.name} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-base text-ink">
                        {customer.name ?? 'Unknown'}
                      </span>
                      <span className="block truncate text-xs text-ink-muted">
                        {customer.company || customer.email || customer.phone || 'No contact details'}
                      </span>
                    </span>
                    {customer.openTickets > 0 ? (
                      <Badge tone="accent" className="shrink-0">
                        {customer.openTickets}
                      </Badge>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {selected ? (
          <div className="space-y-4">
            <Card>
              <div className="flex flex-wrap items-start gap-4">
                <Avatar name={selected.name} size="lg" />
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-xl font-semibold text-ink">
                    {selected.name ?? 'Unknown'}
                  </h2>
                  <p className="mt-0.5 text-sm text-ink-muted">
                    Customer since {formatDate(selected.createdAt)} · last seen{' '}
                    {relativeTime(selected.lastSeenAt)}
                  </p>
                  <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
                    {selected.email ? (
                      <Detail icon={<Mail className="h-3.5 w-3.5" />} value={selected.email} />
                    ) : null}
                    {selected.phone ? (
                      <Detail icon={<Phone className="h-3.5 w-3.5" />} value={selected.phone} />
                    ) : null}
                    {selected.company ? (
                      <Detail icon={<Building2 className="h-3.5 w-3.5" />} value={selected.company} />
                    ) : null}
                  </dl>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="Total" value={selected.totalTickets} />
                  <Stat label="Open" value={selected.openTickets} />
                </div>
              </div>

              <ChannelChips customer={selected} />
            </Card>

            <Card flush>
              <div className="border-b border-line-subtle px-4 py-3">
                <h3 className="text-md font-semibold text-ink">Ticket history</h3>
              </div>
              {history.loading ? (
                <SkeletonRows rows={4} className="p-4" />
              ) : (history.data ?? []).length === 0 ? (
                <EmptyState title="No tickets yet" description="This customer has not raised anything." />
              ) : (
                <ul className="divide-y divide-line-subtle">
                  {(history.data ?? []).map((ticket) => (
                    <li key={ticket.id}>
                      <Link
                        to={`/app/tickets?ticket=${ticket.id}`}
                        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-hover"
                      >
                        <span className="numeric w-12 shrink-0 text-xs text-ink-muted">
                          #{ticket.number}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-base text-ink">{ticket.subject}</span>
                          <span className="block truncate text-xs text-ink-muted">
                            {CHANNEL_LABELS[ticket.channel]} · {formatDate(ticket.createdAt)}
                          </span>
                        </span>
                        <Badge tone={statusTone(ticket.status)}>
                          {STATUS_LABELS[ticket.status] ?? ticket.status}
                        </Badge>
                        <Badge tone={priorityTone(ticket.priority)} className="hidden sm:inline-flex">
                          {ticket.priority}
                        </Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        ) : null}
      </div>
    </Page>
  );
}

function ChannelChips({ customer }: { customer: Customer }) {
  const channels = Object.keys(customer.channelIds ?? {}) as Channel[];
  if (channels.length === 0) return null;

  return (
    <div className="mt-4 border-t border-line-subtle pt-3">
      <p className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
        Reachable on
      </p>
      <div className="flex flex-wrap gap-1.5">
        {channels.map((channel) => (
          <span
            key={channel}
            className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink-secondary"
          >
            <ChannelIcon channel={channel} className="h-3 w-3 text-ink-muted" />
            {CHANNEL_LABELS[channel] ?? channel}
          </span>
        ))}
      </div>
    </div>
  );
}

function Detail({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <div className="flex items-center gap-1.5 text-ink-secondary">
      <span className="text-ink-muted">{icon}</span>
      <span className="truncate">{value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-sunken px-3 py-2 text-center">
      <p className="numeric text-xl font-semibold leading-none text-ink">{value}</p>
      <p className="mt-1 text-2xs text-ink-muted">{label}</p>
    </div>
  );
}

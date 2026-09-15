import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Filter, Plus, Search, Ticket as TicketIcon } from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Field,
  Select,
  SkeletonRows,
  Textarea,
  priorityTone,
  statusTone,
  useToast,
} from '@/components/ui';
import { ChannelIcon } from '@/features/inbox/ChannelIcon';
import { TicketDetail } from './TicketDetail';
import { useApi } from '@/app/session';
import { useAsync, useDebounced, useMediaQuery } from '@/hooks';
import { CHANNEL_LABELS, formatDate, STATUS_LABELS, timeUntil } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Priority, Ticket, TicketStatus } from '@/lib/types';

const STATUSES: TicketStatus[] = ['new', 'open', 'pending', 'on_hold', 'solved', 'closed'];
const PRIORITIES: Priority[] = ['urgent', 'high', 'medium', 'low'];

export default function TicketsPage() {
  const api = useApi();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const isWide = useMediaQuery('(min-width: 1280px)');

  const [search, setSearch] = React.useState('');
  const debouncedSearch = useDebounced(search, 250);
  const [statusFilter, setStatusFilter] = React.useState<TicketStatus[]>(
    () => (params.get('status')?.split(',').filter(Boolean) as TicketStatus[]) ?? [],
  );
  const [priorityFilter, setPriorityFilter] = React.useState<Priority[]>([]);
  const [composing, setComposing] = React.useState(false);

  const assigned = params.get('assigned') ?? undefined;
  const selectedId = params.get('ticket');

  const filters = React.useMemo(
    () => ({
      status: statusFilter.length ? statusFilter : undefined,
      priority: priorityFilter.length ? priorityFilter : undefined,
      assigned,
      search: debouncedSearch || undefined,
    }),
    [statusFilter, priorityFilter, assigned, debouncedSearch],
  );

  const tickets = useAsync(() => api.listTickets(filters), [api, filters]);
  const selected = (tickets.data ?? []).find((ticket) => ticket.id === selectedId) ?? null;

  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set('ticket', id);
    else next.delete('ticket');
    setParams(next);
  };

  const toggle = <T,>(list: T[], value: T, set: (next: T[]) => void) =>
    set(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);

  const updateTicket = async (id: string, patch: Parameters<typeof api.updateTicket>[1]) => {
    try {
      const updated = await api.updateTicket(id, patch);
      tickets.setData((current) =>
        (current ?? []).map((ticket) => (ticket.id === id ? updated : ticket)),
      );
      toast.success('Ticket updated');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not update the ticket');
    }
  };

  const rows = tickets.data ?? [];

  return (
    <Page className="space-y-4">
      <PageHeader
        title="Tickets"
        description="Every request, from every channel."
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setComposing(true)}>
            New ticket
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search subject, number, customer"
          leading={<Search className="h-4 w-4" />}
          className="w-full sm:w-72"
          aria-label="Search tickets"
        />
        <FilterGroup
          label="Status"
          options={STATUSES}
          selected={statusFilter}
          format={(value) => STATUS_LABELS[value] ?? value}
          onToggle={(value) => toggle(statusFilter, value, setStatusFilter)}
        />
        <FilterGroup
          label="Priority"
          options={PRIORITIES}
          selected={priorityFilter}
          onToggle={(value) => toggle(priorityFilter, value, setPriorityFilter)}
        />
        {statusFilter.length || priorityFilter.length || assigned ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStatusFilter([]);
              setPriorityFilter([]);
              const next = new URLSearchParams(params);
              next.delete('assigned');
              setParams(next);
            }}
          >
            Clear
          </Button>
        ) : null}
        <span className="numeric ml-auto text-sm text-ink-muted">
          {rows.length} {rows.length === 1 ? 'ticket' : 'tickets'}
        </span>
      </div>

      <div className={cn('grid gap-4', isWide && selected ? 'grid-cols-[minmax(0,1fr)_380px]' : '')}>
        <Card flush className="overflow-hidden">
          {tickets.error ? (
            <ErrorState error={tickets.error} onRetry={tickets.reload} />
          ) : tickets.loading ? (
            <SkeletonRows rows={8} className="p-4" />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<TicketIcon className="h-5 w-5" />}
              title="No tickets match"
              description="Try clearing a filter, or create one to see how the flow works."
            />
          ) : (
            <ul className="divide-y divide-line-subtle">
              {rows.slice(0, 60).map((ticket) => (
                <TicketRow
                  key={ticket.id}
                  ticket={ticket}
                  selected={ticket.id === selectedId}
                  onSelect={() => select(ticket.id)}
                />
              ))}
            </ul>
          )}
        </Card>

        {selected && isWide ? (
          <TicketDetail ticket={selected} onClose={() => select(null)} onUpdate={updateTicket} />
        ) : null}
      </div>

      {selected && !isWide ? (
        <Modal open onClose={() => select(null)} title={`#${selected.number}`} size="md">
          <TicketDetail ticket={selected} onUpdate={updateTicket} embedded />
        </Modal>
      ) : null}

      <NewTicketModal
        open={composing}
        onClose={() => setComposing(false)}
        onCreated={() => {
          setComposing(false);
          tickets.reload();
        }}
      />
    </Page>
  );
}

function TicketRow({
  ticket,
  selected,
  onSelect,
}: {
  ticket: Ticket;
  selected: boolean;
  onSelect: () => void;
}) {
  const sla = timeUntil(ticket.slaDueAt);
  const closed = ticket.status === 'solved' || ticket.status === 'closed';

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected}
        className={cn(
          'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-100',
          selected ? 'bg-accent-soft' : 'hover:bg-hover',
        )}
      >
        <span className="numeric w-12 shrink-0 text-xs text-ink-muted">#{ticket.number}</span>
        <ChannelIcon channel={ticket.channel} className="hidden h-4 w-4 shrink-0 text-ink-muted sm:block" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-base text-ink">{ticket.subject}</span>
          <span className="block truncate text-xs text-ink-muted">
            {ticket.customer?.name ?? 'Unknown'} · {CHANNEL_LABELS[ticket.channel]} ·{' '}
            {formatDate(ticket.createdAt)}
          </span>
        </span>
        <Badge tone={statusTone(ticket.status)} className="hidden shrink-0 sm:inline-flex">
          {STATUS_LABELS[ticket.status] ?? ticket.status}
        </Badge>
        <Badge tone={priorityTone(ticket.priority)} className="hidden shrink-0 md:inline-flex">
          {ticket.priority}
        </Badge>
        <span
          className={cn(
            'numeric w-16 shrink-0 text-right text-xs font-medium',
            closed ? 'text-ink-muted' : sla.overdue ? 'text-danger' : sla.urgent ? 'text-warning' : 'text-ink-muted',
          )}
        >
          {closed ? 'Done' : sla.label}
        </span>
      </button>
    </li>
  );
}

function FilterGroup<T extends string>({
  label,
  options,
  selected,
  onToggle,
  format = (value: T) => value,
}: {
  label: string;
  options: T[];
  selected: T[];
  onToggle: (value: T) => void;
  format?: (value: T) => string;
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="hidden items-center gap-1 pr-1 text-xs text-ink-muted sm:inline-flex">
        <Filter className="h-3 w-3" />
        {label}
      </span>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onToggle(option)}
          className={cn(
            'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150',
            selected.includes(option)
              ? 'border-accent-border bg-accent-soft text-accent-text'
              : 'border-line text-ink-secondary hover:bg-hover',
          )}
        >
          {format(option)}
        </button>
      ))}
    </div>
  );
}

function NewTicketModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const api = useApi();
  const toast = useToast();
  const [form, setForm] = React.useState({
    subject: '',
    description: '',
    priority: 'medium' as Priority,
    customerEmail: '',
    customerName: '',
  });
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setForm({ subject: '', description: '', priority: 'medium', customerEmail: '', customerName: '' });
    }
  }, [open]);

  const submit = async () => {
    if (!form.subject.trim()) return;
    setSaving(true);
    try {
      await api.createTicket({
        subject: form.subject.trim(),
        description: form.description,
        priority: form.priority,
        customerEmail: form.customerEmail || null,
        customerName: form.customerName || null,
      });
      toast.success('Ticket created');
      onCreated();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not create the ticket');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New ticket"
      description="For requests that arrive outside a channel, such as someone walking in or a call you took yourself."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={saving} disabled={!form.subject.trim()}>
            Create ticket
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Subject" htmlFor="ticket-subject">
          <Input
            id="ticket-subject"
            value={form.subject}
            onChange={(event) => setForm({ ...form, subject: event.target.value })}
            placeholder="Refund not received"
            autoFocus
          />
        </Field>
        <Field label="Description" htmlFor="ticket-description">
          <Textarea
            id="ticket-description"
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="What happened, in the customer's words."
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Priority" htmlFor="ticket-priority">
            <Select
              id="ticket-priority"
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: event.target.value as Priority })}
            >
              {PRIORITIES.map((priority) => (
                <option key={priority} value={priority}>
                  {priority}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Customer name" htmlFor="ticket-customer">
            <Input
              id="ticket-customer"
              value={form.customerName}
              onChange={(event) => setForm({ ...form, customerName: event.target.value })}
              placeholder="Optional"
            />
          </Field>
        </div>
        <Field label="Customer email" htmlFor="ticket-email" hint="Links the ticket to an existing customer, or creates one.">
          <Input
            id="ticket-email"
            type="email"
            value={form.customerEmail}
            onChange={(event) => setForm({ ...form, customerEmail: event.target.value })}
            placeholder="Optional"
          />
        </Field>
      </div>
    </Modal>
  );
}

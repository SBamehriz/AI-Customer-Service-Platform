import { Link } from 'react-router-dom';
import { Sparkles, X } from '@/components/icons';
import { Avatar, Badge, Button, Card, Select, priorityTone, statusTone } from '@/components/ui';
import { ChannelIcon } from '@/features/inbox/ChannelIcon';
import { CHANNEL_LABELS, formatDateTime, STATUS_LABELS, timeUntil } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Priority, Ticket, TicketStatus } from '@/lib/types';

const STATUSES: TicketStatus[] = ['new', 'open', 'pending', 'on_hold', 'solved', 'closed'];
const PRIORITIES: Priority[] = ['urgent', 'high', 'medium', 'low'];

export interface TicketDetailProps {
  ticket: Ticket;
  onUpdate: (id: string, patch: { status?: TicketStatus; priority?: Priority }) => void;
  onClose?: () => void;
  /** Rendered inside a modal on narrow screens, without its own card chrome. */
  embedded?: boolean;
}

export function TicketDetail({ ticket, onUpdate, onClose, embedded }: TicketDetailProps) {
  const sla = timeUntil(ticket.slaDueAt);
  const closed = ticket.status === 'solved' || ticket.status === 'closed';

  const body = (
    <div className="space-y-4">
      {!embedded ? (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="numeric text-xs text-ink-muted">#{ticket.number}</p>
            <h2 className="mt-0.5 text-md font-semibold text-ink">{ticket.subject}</h2>
          </div>
          {onClose ? (
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
              <X className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      ) : (
        <h2 className="text-md font-semibold text-ink">{ticket.subject}</h2>
      )}

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className="text-2xs font-medium uppercase tracking-wide text-ink-muted">Status</span>
          <Select
            value={ticket.status}
            onChange={(event) => onUpdate(ticket.id, { status: event.target.value as TicketStatus })}
          >
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status] ?? status}
              </option>
            ))}
          </Select>
        </label>
        <label className="space-y-1">
          <span className="text-2xs font-medium uppercase tracking-wide text-ink-muted">Priority</span>
          <Select
            value={ticket.priority}
            onChange={(event) => onUpdate(ticket.id, { priority: event.target.value as Priority })}
          >
            {PRIORITIES.map((priority) => (
              <option key={priority} value={priority}>
                {priority}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {ticket.description ? (
        <div className="rounded-lg bg-sunken px-3 py-2.5">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-secondary">
            {ticket.description}
          </p>
        </div>
      ) : null}

      {ticket.customer ? (
        <div className="flex items-center gap-2.5 rounded-lg border border-line px-3 py-2.5">
          <Avatar name={ticket.customer.name} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{ticket.customer.name}</p>
            <p className="truncate text-xs text-ink-muted">{ticket.customer.email ?? 'No email'}</p>
          </div>
          <Link to={`/app/customers?customer=${ticket.customer.id}`}>
            <Button variant="ghost" size="sm">
              Profile
            </Button>
          </Link>
        </div>
      ) : null}

      <dl className="space-y-2 text-sm">
        <Row label="Channel">
          <span className="inline-flex items-center gap-1.5">
            <ChannelIcon channel={ticket.channel} className="h-3.5 w-3.5 text-ink-muted" />
            {CHANNEL_LABELS[ticket.channel]}
          </span>
        </Row>
        <Row label="Category">{ticket.category ?? 'None'}</Row>
        <Row label="Created">{formatDateTime(ticket.createdAt)}</Row>
        <Row label="First reply">
          {ticket.firstResponseAt ? formatDateTime(ticket.firstResponseAt) : 'Not yet answered'}
        </Row>
        <Row label="SLA">
          {closed ? (
            <span className="text-ink-muted">Closed</span>
          ) : (
            <span
              className={cn(
                'numeric font-medium',
                sla.overdue ? 'text-danger' : sla.urgent ? 'text-warning' : 'text-ink-secondary',
              )}
            >
              {sla.label}
            </span>
          )}
        </Row>
        {ticket.resolvedAt ? <Row label="Resolved">{formatDateTime(ticket.resolvedAt)}</Row> : null}
        {ticket.satisfaction ? <Row label="Rating">{'★'.repeat(ticket.satisfaction)}</Row> : null}
      </dl>

      {ticket.aiHandled ? (
        <div className="flex items-start gap-2 rounded-lg border border-accent-border bg-accent-soft px-3 py-2.5">
          <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text" />
          <p className="text-xs text-accent-text">
            Answered by AI
            {ticket.aiConfidence
              ? ` at ${Math.round(ticket.aiConfidence * 100)}% confidence`
              : ''}
            . Confidence reflects how well the knowledge base covered the question, not how sure
            the model is.
          </p>
        </div>
      ) : null}

      {ticket.tags.length ? (
        <div className="flex flex-wrap gap-1.5">
          {ticket.tags.map((tag) => (
            <Badge key={tag} tone="neutral">
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
        <Badge tone={statusTone(ticket.status)}>{STATUS_LABELS[ticket.status] ?? ticket.status}</Badge>
        <Badge tone={priorityTone(ticket.priority)}>{ticket.priority}</Badge>
        {!closed ? (
          <Button
            variant="primary"
            size="sm"
            className="ml-auto"
            onClick={() => onUpdate(ticket.id, { status: 'solved' })}
          >
            Mark solved
          </Button>
        ) : null}
      </div>
    </div>
  );

  if (embedded) return body;
  return <Card className="h-fit">{body}</Card>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="shrink-0 text-ink-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right text-ink">{children}</dd>
    </div>
  );
}

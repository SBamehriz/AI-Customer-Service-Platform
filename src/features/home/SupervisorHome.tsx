import * as React from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, BookOpen, Radio, TrendingDown, Users } from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import { BarList, DonutChart, StatTile, TrendChart } from '@/components/charts';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  SegmentedControl,
  Skeleton,
  priorityTone,
} from '@/components/ui';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import { CHANNEL_LABELS, compactNumber, duration, percent, plural, titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AnalyticsSummary, Article, MixEntry, Ticket } from '@/lib/types';

const RANGES = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
];

const PRIORITY_COLORS: Record<string, string> = {
  urgent: 'var(--danger-soft)',
  high: 'var(--warning-soft)',
  medium: 'var(--accent-soft)',
  low: 'var(--surface-sunken)',
};

/** Operations overview. Is the team healthy, and what needs acting on first. */
export default function SupervisorHome() {
  const api = useApi();
  const [range, setRange] = React.useState('30');
  const days = Number(range);

  const analytics = useAsync(() => api.analytics(days), [api, days]);
  const tickets = useAsync(() => api.listTickets(), [api]);
  const articles = useAsync(() => api.listArticles(), [api]);

  const summary = analytics.data;
  const error = analytics.error ?? tickets.error;

  return (
    <Page className="space-y-5">
      <PageHeader
        title="Operations"
        description="How the queue is moving, and where it is stuck."
        actions={
          <SegmentedControl
            aria-label="Date range"
            options={RANGES}
            value={range}
            onChange={setRange}
          />
        }
      />

      {error ? (
        <Card>
          <ErrorState error={error} onRetry={analytics.reload} />
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {analytics.loading || !summary ? (
          Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-[108px]" />)
        ) : (
          <>
            <StatTile
              label="Open tickets"
              value={compactNumber(summary.openTickets)}
              delta={summary.openDelta}
              goodWhen="down"
              hint="vs. previous period"
              trend={summary.series.map((point) => point.created)}
            />
            <StatTile
              label="SLA at risk"
              value={summary.slaAtRisk}
              goodWhen="down"
              hint={summary.slaAtRisk ? 'Unanswered, deadline near' : 'Nothing overdue'}
            />
            <StatTile
              label="AI deflection"
              value={percent(summary.aiDeflection, 1)}
              delta={summary.aiDeflectionDelta}
              hint="Resolved without a human"
            />
            <StatTile
              label="CSAT"
              value={summary.csat ? percent(summary.csat, 1) : 'None yet'}
              delta={summary.csatDelta}
              hint={
                summary.medianFirstResponseMinutes !== null
                  ? `${duration(summary.medianFirstResponseMinutes)} median first reply`
                  : undefined
              }
            />
          </>
        )}
      </div>

      <Insights summary={summary} tickets={tickets.data ?? []} articles={articles.data ?? []} />

      <Card>
        <CardHeader
          title="Created vs. resolved"
          description={`Ticket flow over the last ${days} days`}
          action={
            <Link to="/app/analytics">
              <Button variant="ghost" size="sm">
                Analytics
              </Button>
            </Link>
          }
        />
        {analytics.loading || !summary ? (
          <Skeleton className="h-[220px]" />
        ) : (
          <TrendChart data={summary.series} />
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Where work comes from" description="Share of tickets by channel" />
          {analytics.loading || !summary ? (
            <Skeleton className="h-[148px]" />
          ) : (
            <DonutChart
              data={summary.channelMix}
              centerLabel="tickets"
              formatLabel={(label) => CHANNEL_LABELS[label] ?? label}
            />
          )}
        </Card>

        <Card>
          <CardHeader title="Backlog by priority" description="Open tickets, most urgent first" />
          {analytics.loading || !summary ? (
            <Skeleton className="h-[148px]" />
          ) : (
            <BarList
              data={orderByPriority(summary.openPriorityMix)}
              formatLabel={titleCase}
              colorFor={(entry) => PRIORITY_COLORS[entry.label] ?? 'var(--accent-soft)'}
            />
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card flush>
          <div className="p-4">
            <CardHeader
              title="Top agents"
              description={`Solved in the last ${days} days`}
              action={<Users className="h-4 w-4 text-ink-muted" />}
            />
          </div>
          {analytics.loading || !summary ? (
            <Skeleton className="mx-4 mb-4 h-32" />
          ) : summary.agentLeaderboard.length === 0 ? (
            <EmptyState title="No solved tickets yet" />
          ) : (
            <ul className="divide-y divide-line-subtle border-t border-line-subtle">
              {summary.agentLeaderboard.map((row, index) => (
                <li key={row.userId} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="numeric w-5 shrink-0 text-xs text-ink-muted">{index + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-base text-ink">{row.name}</span>
                  <span className="numeric shrink-0 text-xs text-ink-muted">
                    {duration(row.medianFirstResponseMinutes)} first reply
                  </span>
                  <span className="numeric w-10 shrink-0 text-right text-base font-medium text-ink">
                    {row.solved}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <SlaRiskCard tickets={tickets.data ?? []} loading={tickets.loading} />
      </div>
    </Page>
  );
}

/** Surfaced actions, computed from the same rows as the tiles above. */
function Insights({
  summary,
  tickets,
  articles,
}: {
  summary: AnalyticsSummary | null;
  tickets: Ticket[];
  articles: Article[];
}) {
  const cards = React.useMemo(() => {
    if (!summary) return [];
    const items: { tone: 'danger' | 'warning' | 'info'; icon: React.ComponentType<{ className?: string }>; title: string; body: string; to: string }[] = [];

    if (summary.slaAtRisk > 0) {
      items.push({
        tone: 'danger',
        icon: AlertTriangle,
        title: `${summary.slaAtRisk} ticket${summary.slaAtRisk === 1 ? '' : 's'} at SLA risk`,
        body: 'Unanswered with a deadline inside two hours.',
        to: '/app/tickets?status=new',
      });
    }

    const backlogGrowing =
      summary.series.length > 6 &&
      sum(summary.series.slice(-7).map((point) => point.created)) >
        sum(summary.series.slice(-7).map((point) => point.resolved)) * 1.15;
    if (backlogGrowing) {
      items.push({
        tone: 'warning',
        icon: TrendingDown,
        title: 'Backlog is growing',
        body: 'More tickets came in than went out over the last seven days.',
        to: '/app/analytics',
      });
    }

    const unassigned = tickets.filter(
      (ticket) => !ticket.assignedUserId && ticket.status !== 'solved' && ticket.status !== 'closed',
    ).length;
    if (unassigned > 3) {
      items.push({
        tone: 'info',
        icon: Radio,
        title: `${plural(unassigned, 'ticket')} unassigned`,
        body: 'Nobody owns these yet, so the routing rules may be missing one.',
        to: '/app/tickets?assigned=unassigned',
      });
    }

    const stale = articles.filter(
      (article) =>
        article.status === 'published' &&
        Date.now() - new Date(article.updatedAt).getTime() > 90 * 86_400_000,
    ).length;
    if (stale > 0) {
      items.push({
        tone: 'info',
        icon: BookOpen,
        title: `${stale} article${stale === 1 ? '' : 's'} untouched for 90 days`,
        body: 'Stale knowledge is what makes AI answers wrong.',
        to: '/app/knowledge',
      });
    }

    return items.slice(0, 3);
  }, [summary, tickets, articles]);

  if (cards.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Link key={card.title} to={card.to}>
            <Card
              className={cn(
                'h-full border-l-2 transition-[border-color,box-shadow] duration-150 hover:shadow-md',
                card.tone === 'danger'
                  ? 'border-l-danger'
                  : card.tone === 'warning'
                    ? 'border-l-warning'
                    : 'border-l-accent',
              )}
            >
              <div className="flex gap-2.5">
                <Icon
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    card.tone === 'danger'
                      ? 'text-danger'
                      : card.tone === 'warning'
                        ? 'text-warning'
                        : 'text-accent',
                  )}
                />
                <div className="min-w-0">
                  <p className="text-base font-medium text-ink">{card.title}</p>
                  <p className="mt-0.5 text-sm text-ink-muted">{card.body}</p>
                </div>
              </div>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}

function SlaRiskCard({ tickets, loading }: { tickets: Ticket[]; loading: boolean }) {
  const atRisk = tickets
    .filter(
      (ticket) =>
        ticket.status !== 'solved' &&
        ticket.status !== 'closed' &&
        !ticket.firstResponseAt &&
        ticket.slaDueAt,
    )
    .sort((a, b) => new Date(a.slaDueAt!).getTime() - new Date(b.slaDueAt!).getTime())
    .slice(0, 6);

  return (
    <Card flush>
      <div className="p-4">
        <CardHeader
          title="Waiting on a first reply"
          description="Nobody has answered these yet"
          action={
            <Link to="/app/tickets?status=new">
              <Button variant="ghost" size="sm">
                View all
              </Button>
            </Link>
          }
        />
      </div>
      {loading ? (
        <Skeleton className="mx-4 mb-4 h-32" />
      ) : atRisk.length === 0 ? (
        <EmptyState title="Everything has been answered" description="No ticket is waiting on a first reply." />
      ) : (
        <ul className="divide-y divide-line-subtle border-t border-line-subtle">
          {atRisk.map((ticket) => (
            <li key={ticket.id}>
              <Link
                to={`/app/tickets?ticket=${ticket.id}`}
                className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-hover"
              >
                <span className="numeric w-11 shrink-0 text-xs text-ink-muted">#{ticket.number}</span>
                <span className="min-w-0 flex-1 truncate text-base text-ink">{ticket.subject}</span>
                <Badge tone={priorityTone(ticket.priority)}>{ticket.priority}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const PRIORITY_ORDER = ['urgent', 'high', 'medium', 'low'];

function orderByPriority(mix: MixEntry[]): MixEntry[] {
  return [...mix].sort(
    (a, b) => PRIORITY_ORDER.indexOf(a.label) - PRIORITY_ORDER.indexOf(b.label),
  );
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

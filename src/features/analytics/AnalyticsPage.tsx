import * as React from 'react';
import { Page, PageHeader } from '@/components/layout';
import { BarList, DonutChart, StatTile, TrendChart } from '@/components/charts';
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  SegmentedControl,
  Skeleton,
} from '@/components/ui';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import { CHANNEL_LABELS, compactNumber, duration, percent, titleCase } from '@/lib/format';
import type { MixEntry } from '@/lib/types';

const RANGES = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
];

const PRIORITY_ORDER = ['urgent', 'high', 'medium', 'low'];
const PRIORITY_COLORS: Record<string, string> = {
  urgent: 'var(--danger-soft)',
  high: 'var(--warning-soft)',
  medium: 'var(--accent-soft)',
  low: 'var(--surface-sunken)',
};

/** Every number here is computed from ticket rows at request time. */
export default function AnalyticsPage() {
  const api = useApi();
  const [range, setRange] = React.useState('30');
  const days = Number(range);

  const analytics = useAsync(() => api.analytics(days), [api, days]);
  const workload = useAsync(() => api.workload(), [api]);
  const summary = analytics.data;

  return (
    <Page className="space-y-5">
      <PageHeader
        title="Analytics"
        description="Volume, response time and where the queue is coming from."
        actions={
          <SegmentedControl aria-label="Date range" options={RANGES} value={range} onChange={setRange} />
        }
      />

      {analytics.error ? (
        <Card>
          <ErrorState error={analytics.error} onRetry={analytics.reload} />
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {analytics.loading || !summary ? (
          Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-[108px]" />)
        ) : (
          <>
            <StatTile
              label="Tickets created"
              value={compactNumber(summary.series.reduce((total, point) => total + point.created, 0))}
              hint={`Last ${days} days`}
              trend={summary.series.map((point) => point.created)}
            />
            <StatTile
              label="Median first reply"
              value={duration(summary.medianFirstResponseMinutes)}
              goodWhen="down"
              hint="Across every channel"
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
              hint="Average rating"
            />
          </>
        )}
      </div>

      <Card>
        <CardHeader title="Volume over time" description="Created against resolved, per day" />
        {analytics.loading || !summary ? (
          <Skeleton className="h-[240px]" />
        ) : (
          <TrendChart data={summary.series} height={260} />
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Channel mix" description="Where tickets originate" />
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
          <CardHeader title="Top categories" description="What people actually contact you about" />
          {analytics.loading || !summary ? (
            <Skeleton className="h-[148px]" />
          ) : summary.topCategories.length === 0 ? (
            <EmptyState title="No categorised tickets yet" />
          ) : (
            <BarList data={summary.topCategories} />
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Backlog by priority" description="Tickets raised in this window" />
          {analytics.loading || !summary ? (
            <Skeleton className="h-[148px]" />
          ) : (
            <BarList
              data={orderByPriority(summary.priorityMix)}
              formatLabel={titleCase}
              colorFor={(entry) => PRIORITY_COLORS[entry.label] ?? 'var(--accent-soft)'}
            />
          )}
        </Card>

        <Card>
          <CardHeader title="Live queue" description="Conversations open right now" />
          {workload.loading || !workload.data ? (
            <Skeleton className="h-[148px]" />
          ) : (
            <>
              <div className="mb-4 grid grid-cols-3 gap-2">
                <QueueStat label="Open" value={workload.data.openConversations} />
                <QueueStat label="Escalated" value={workload.data.escalated} tone="danger" />
                <QueueStat label="Unassigned" value={workload.data.unassigned} tone="warning" />
              </div>
              <BarList
                data={workload.data.byChannel.map((entry) => ({ ...entry, share: 0 }))}
                formatLabel={(label) => CHANNEL_LABELS[label] ?? label}
                emptyLabel="Nothing open"
              />
            </>
          )}
        </Card>
      </div>

      <Card flush>
        <div className="p-4">
          <CardHeader title="Agent performance" description={`Solved in the last ${days} days`} />
        </div>
        {analytics.loading || !summary ? (
          <Skeleton className="mx-4 mb-4 h-32" />
        ) : summary.agentLeaderboard.length === 0 ? (
          <EmptyState title="No solved tickets in this window" />
        ) : (
          <div className="scroll-slim overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="border-y border-line-subtle bg-sunken text-2xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Agent</th>
                  <th className="px-4 py-2 text-right font-medium">Solved</th>
                  <th className="px-4 py-2 text-right font-medium">Median first reply</th>
                  <th className="px-4 py-2 text-right font-medium">CSAT</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle">
                {summary.agentLeaderboard.map((row) => (
                  <tr key={row.userId}>
                    <td className="px-4 py-2.5 text-ink">{row.name}</td>
                    <td className="numeric px-4 py-2.5 text-right font-medium text-ink">{row.solved}</td>
                    <td className="numeric px-4 py-2.5 text-right text-ink-secondary">
                      {duration(row.medianFirstResponseMinutes)}
                    </td>
                    <td className="numeric px-4 py-2.5 text-right text-ink-secondary">
                      {row.csat === null ? 'None' : percent(row.csat, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </Page>
  );
}

function QueueStat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: number;
  tone?: 'neutral' | 'danger' | 'warning';
}) {
  return (
    <div className="rounded-lg bg-sunken px-3 py-2.5 text-center">
      <p
        className={
          tone === 'danger'
            ? 'numeric text-xl font-semibold leading-none text-danger'
            : tone === 'warning'
              ? 'numeric text-xl font-semibold leading-none text-warning'
              : 'numeric text-xl font-semibold leading-none text-ink'
        }
      >
        {value}
      </p>
      <p className="mt-1 text-2xs text-ink-muted">{label}</p>
    </div>
  );
}

function orderByPriority(mix: MixEntry[]): MixEntry[] {
  return [...mix].sort((a, b) => PRIORITY_ORDER.indexOf(a.label) - PRIORITY_ORDER.indexOf(b.label));
}

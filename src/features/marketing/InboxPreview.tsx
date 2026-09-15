import { Camera, Mail, MessageSquare, PhoneCall, Radio, Sparkles } from '@/components/icons';
import { Avatar, Badge } from '@/components/ui';
import { cn } from '@/lib/utils';

/** A static rendering of the agent inbox for the marketing hero. */

const THREADS = [
  { name: 'Elena Farrow', channel: Radio, preview: 'The Ridgeline shell has started delaminating', tone: 'danger' as const, label: 'Escalated', time: '4m' },
  { name: 'Nadia Osei', channel: Camera, preview: 'love the alpine 45 but im 5ft 2, will it swallow me', tone: 'accent' as const, label: 'Open', time: '18m' },
  { name: 'Maria Delgado', channel: Mail, preview: 'What does a trade account involve, and is there a minimum?', tone: 'warning' as const, label: 'Pending', time: '1h' },
  { name: 'Ben Lindqvist', channel: MessageSquare, preview: 'Box says 10.5 but the boots inside are 9.5', tone: 'accent' as const, label: 'Open', time: '3h' },
  { name: 'Camille Boucher', channel: PhoneCall, preview: 'Call summary, expedition kit for 12, April', tone: 'success' as const, label: 'Resolved', time: '6h' },
];

export function InboxPreview() {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-xl">
      {/* Window chrome */}
      <div className="flex items-center gap-2 border-b border-line bg-sunken px-3.5 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
        <span className="ml-2 text-xs text-ink-muted">Inbox · 5 conversations</span>
      </div>

      <div className="grid sm:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
        <ul className="divide-y divide-line-subtle border-b border-line sm:border-b-0 sm:border-r">
          {THREADS.map((thread, index) => {
            const Icon = thread.channel;
            return (
              <li
                key={thread.name}
                className={cn(
                  'flex gap-2.5 px-3 py-2.5',
                  index === 0 ? 'bg-accent-soft/60' : '',
                )}
              >
                <Avatar name={thread.name} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium text-ink">{thread.name}</p>
                    <span className="shrink-0 text-2xs text-ink-muted">{thread.time}</span>
                  </div>
                  <p className="truncate text-xs text-ink-muted">{thread.preview}</p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Icon className="h-3 w-3 text-ink-muted" />
                    <Badge tone={thread.tone} className="px-1.5 py-0 text-[10px]">
                      {thread.label}
                    </Badge>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>

        <div className="hidden flex-col sm:flex">
          <div className="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
            <div>
              <p className="text-sm font-medium text-ink">Rain shell delaminated after four trips</p>
              <p className="text-2xs text-ink-muted">WhatsApp · Elena Farrow · #48221</p>
            </div>
            <Badge tone="danger" dot>
              Escalated
            </Badge>
          </div>

          <div className="flex-1 space-y-3 p-4">
            <Bubble side="in" author="Elena Farrow">
              The Ridgeline shell I bought in March has started delaminating along both shoulder
              seams. I have only had it out four times.
            </Bubble>
            <Bubble side="out" author="AI Assistant" ai confidence={0.82} source="Gear warranty">
              That is covered. Seam separation on a shell is a manufacturing defect, and shells
              carry a 2 year warranty on that. Could you send photos of both shoulder seams.
            </Bubble>
            <Bubble side="in" author="Elena Farrow">
              Photos attached. I guide professionally so I need this sorted before Saturday.
            </Bubble>
            <div className="rounded-lg border border-dashed border-line px-3 py-2 text-xs text-ink-muted">
              Escalated to a human agent. Commercial use, guiding client with a hard deadline.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({
  side,
  author,
  ai,
  confidence,
  source,
  children,
}: {
  side: 'in' | 'out';
  author: string;
  ai?: boolean;
  confidence?: number;
  source?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn('flex gap-2.5', side === 'out' ? 'flex-row-reverse' : '')}>
      <Avatar name={author} size="sm" ai={ai} />
      <div className={cn('max-w-[76%]', side === 'out' ? 'text-right' : '')}>
        <div
          className={cn(
            'rounded-xl px-3 py-2 text-left text-sm',
            side === 'out'
              ? 'rounded-tr-sm bg-accent-soft text-ink'
              : 'rounded-tl-sm border border-line bg-sunken text-ink',
          )}
        >
          {children}
        </div>
        {ai ? (
          <p className="mt-1 inline-flex items-center gap-1 text-2xs text-ink-muted">
            <Sparkles className="h-3 w-3" />
            {Math.round((confidence ?? 0) * 100)}% confidence, grounded in {source}
          </p>
        ) : null}
      </div>
    </div>
  );
}

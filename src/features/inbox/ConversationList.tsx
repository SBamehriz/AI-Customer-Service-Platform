import { Avatar, Badge, statusTone } from '@/components/ui';
import { ChannelIcon } from './ChannelIcon';
import { CHANNEL_LABELS, relativeTime, STATUS_LABELS } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Conversation } from '@/lib/types';

export interface ConversationListProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ConversationList({ conversations, selectedId, onSelect }: ConversationListProps) {
  return (
    <ul className="divide-y divide-line-subtle">
      {conversations.map((conversation) => {
        const latest = [...conversation.messages].reverse().find((message) => !message.isPrivate);
        const selected = conversation.id === selectedId;
        return (
          <li key={conversation.id}>
            <button
              type="button"
              onClick={() => onSelect(conversation.id)}
              aria-current={selected}
              className={cn(
                'flex w-full gap-2.5 px-3 py-3 text-left transition-colors duration-100',
                selected ? 'bg-accent-soft' : 'hover:bg-hover',
              )}
            >
              <Avatar name={conversation.customer?.name} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate text-base font-medium text-ink">
                    {conversation.customer?.name ?? 'Unknown'}
                  </p>
                  <span className="shrink-0 text-2xs text-ink-muted">
                    {relativeTime(conversation.lastMessageAt)}
                  </span>
                </div>
                <p className="truncate text-sm text-ink-secondary">
                  {conversation.subject ?? 'Conversation'}
                </p>
                {latest ? (
                  <p className="mt-0.5 truncate text-xs text-ink-muted">
                    {latest.authorType === 'ai' ? 'AI: ' : latest.authorType === 'agent' ? 'You: ' : ''}
                    {latest.body}
                  </p>
                ) : null}
                <div className="mt-1.5 flex items-center gap-1.5">
                  <span
                    className="inline-flex items-center gap-1 text-2xs text-ink-muted"
                    title={CHANNEL_LABELS[conversation.channel]}
                  >
                    <ChannelIcon channel={conversation.channel} className="h-3 w-3" />
                    {CHANNEL_LABELS[conversation.channel]}
                  </span>
                  <Badge tone={statusTone(conversation.status)} className="px-1.5 py-0 text-[10px]">
                    {STATUS_LABELS[conversation.status] ?? conversation.status}
                  </Badge>
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

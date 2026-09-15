import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Filter, Inbox, Search } from '@/components/icons';
import {
  EmptyState,
  ErrorState,
  Input,
  SegmentedControl,
  SkeletonRows,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync, useDebounced, useHotkey, useMediaQuery } from '@/hooks';
import { cn } from '@/lib/utils';
import type { Conversation, ConversationStatus, Message } from '@/lib/types';
import { ConversationList } from './ConversationList';
import { ConversationThread } from './ConversationThread';
import { ContextPanel } from './ContextPanel';

type Scope = 'all' | 'mine' | 'escalated' | 'unassigned';

const SCOPES: { value: Scope; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'mine', label: 'Mine' },
  { value: 'escalated', label: 'Escalated' },
  { value: 'unassigned', label: 'Unassigned' },
];

/** The unified inbox. Three panes on a wide screen, one at a time on a phone. */
export default function InboxPage() {
  const api = useApi();
  const { user, subscribe } = useSession();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const isWide = useMediaQuery('(min-width: 1024px)');

  const [scope, setScope] = React.useState<Scope>('all');
  const [search, setSearch] = React.useState('');
  const debouncedSearch = useDebounced(search, 250);
  const selectedId = params.get('conversation');

  const filters = React.useMemo(() => {
    const base: { status?: ConversationStatus; assigned?: string; search?: string } = {};
    if (scope === 'mine') base.assigned = 'me';
    if (scope === 'escalated') base.status = 'escalated';
    if (debouncedSearch) base.search = debouncedSearch;
    return base;
  }, [scope, debouncedSearch]);

  const conversations = useAsync(() => api.listConversations(filters), [api, filters]);

  const visible = React.useMemo(() => {
    const rows = conversations.data ?? [];
    return scope === 'unassigned'
      ? rows.filter((row) => !row.assignedUserId && row.status !== 'resolved')
      : rows;
  }, [conversations.data, scope]);

  React.useEffect(() => {
    if (conversations.loading || visible.length === 0) return;
    if (selectedId && visible.some((row) => row.id === selectedId)) return;
    if (isWide) select(visible[0].id, true);
  }, [visible, conversations.loading, isWide]);

  const active = useAsync(
    () => (selectedId ? api.getConversation(selectedId) : Promise.resolve(null)),
    [api, selectedId],
  );

  // Refresh when the workspace reports activity on the open thread.
  React.useEffect(
    () =>
      subscribe((message) => {
        if (message.event === 'message.created' || message.event.startsWith('conversation.')) {
          conversations.reload();
          if (message.data?.conversationId === selectedId) active.reload();
        }
      }),
    [subscribe, selectedId],
  );

  function select(id: string, replace = false) {
    const next = new URLSearchParams(params);
    next.set('conversation', id);
    setParams(next, { replace });
  }

  const move = (direction: 1 | -1) => {
    if (visible.length === 0) return;
    const index = visible.findIndex((row) => row.id === selectedId);
    const nextIndex = Math.min(visible.length - 1, Math.max(0, (index === -1 ? 0 : index) + direction));
    select(visible[nextIndex].id);
  };

  useHotkey('j', () => move(1));
  useHotkey('k', () => move(-1));
  useHotkey('shift+r', () => {
    if (active.data) void resolve(active.data);
  });

  async function resolve(conversation: Conversation) {
    try {
      const updated = await api.updateConversation(conversation.id, { status: 'resolved' });
      active.setData(updated);
      conversations.reload();
      toast.success('Conversation resolved');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not resolve');
    }
  }

  async function assignToMe(conversation: Conversation) {
    if (!user) return;
    try {
      const updated = await api.updateConversation(conversation.id, { assignedUserId: user.id });
      active.setData(updated);
      conversations.reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not assign');
    }
  }

  async function send(body: string, isPrivate: boolean, attachmentIds: string[] = []) {
    if (!active.data) return;
    const message = await api.sendMessage(active.data.id, { body, isPrivate, attachmentIds });
    active.setData((current) =>
      current
        ? { ...current, messages: [...current.messages, message as Message] }
        : (current as never),
    );
    conversations.reload();
  }

  const showList = isWide || !selectedId;
  const showThread = isWide || Boolean(selectedId);

  return (
    <div className="flex h-full min-h-0">
      {showList ? (
        <aside
          className={cn(
            'flex min-h-0 flex-col border-r border-line bg-surface',
            isWide ? 'w-[320px] shrink-0' : 'w-full',
          )}
        >
          <div className="space-y-2.5 border-b border-line-subtle p-3">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search conversations"
              leading={<Search className="h-4 w-4" />}
              aria-label="Search conversations"
            />
            <SegmentedControl
              aria-label="Conversation filter"
              size="sm"
              options={SCOPES}
              value={scope}
              onChange={setScope}
              className="w-full"
            />
          </div>

          <div className="scroll-slim min-h-0 flex-1 overflow-y-auto">
            {conversations.error ? (
              <ErrorState error={conversations.error} onRetry={conversations.reload} />
            ) : conversations.loading ? (
              <SkeletonRows rows={7} className="p-3" />
            ) : visible.length === 0 ? (
              <EmptyState
                icon={<Filter className="h-5 w-5" />}
                title="Nothing here"
                description="No conversation matches this filter."
              />
            ) : (
              <ConversationList
                conversations={visible}
                selectedId={selectedId}
                onSelect={(id) => select(id)}
              />
            )}
          </div>
        </aside>
      ) : null}

      {showThread ? (
        <div className="flex min-h-0 min-w-0 flex-1">
          {active.loading && !active.data ? (
            <div className="flex-1 p-6">
              <SkeletonRows rows={5} />
            </div>
          ) : active.data ? (
            <>
              <ConversationThread
                conversation={active.data}
                onBack={!isWide ? () => setParams({}) : undefined}
                onResolve={() => resolve(active.data!)}
                onAssignToMe={() => assignToMe(active.data!)}
                onSend={send}
              />
              {isWide ? <ContextPanel conversation={active.data} /> : null}
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <EmptyState
                icon={<Inbox className="h-5 w-5" />}
                title="Select a conversation"
                description="Use j and k to move through the list, ⇧R to resolve."
              />
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

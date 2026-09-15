import * as React from 'react';
import {
  ArrowLeft,
  Check,
  Paperclip,
  Send,
  Sparkles,
  StickyNote,
  UserPlus,
  WandSparkles,
  X,
} from '@/components/icons';
import { Avatar, Badge, Button, statusTone, useToast } from '@/components/ui';
import { AttachmentList } from '@/components/AttachmentList';
import { ChannelIcon } from './ChannelIcon';
import { useApi, useSession } from '@/app/session';
import { CHANNEL_LABELS, dayLabel, formatTime, STATUS_LABELS } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Attachment, Conversation, Message } from '@/lib/types';

export interface ConversationThreadProps {
  conversation: Conversation;
  onBack?: () => void;
  onResolve: () => void;
  onAssignToMe: () => void;
  onSend: (body: string, isPrivate: boolean, attachmentIds: string[]) => Promise<void>;
}

export function ConversationThread({
  conversation,
  onBack,
  onResolve,
  onAssignToMe,
  onSend,
}: ConversationThreadProps) {
  const api = useApi();
  const { user } = useSession();
  const toast = useToast();

  const [draft, setDraft] = React.useState('');
  const [isPrivate, setIsPrivate] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [drafting, setDrafting] = React.useState(false);
  // Files are uploaded as they are picked, so sending is just ids.
  const [pending, setPending] = React.useState<Attachment[]>([]);
  const [uploading, setUploading] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  const composerRef = React.useRef<HTMLTextAreaElement>(null);

  // Jump to the newest message whenever the thread changes or grows.
  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [conversation.id, conversation.messages.length]);

  React.useEffect(() => {
    setDraft('');
    setIsPrivate(false);
    setPending([]);
  }, [conversation.id]);

  const submit = async () => {
    const body = draft.trim();
    // A file on its own is a message, so either one is enough to send.
    if ((!body && pending.length === 0) || sending) return;
    setSending(true);
    try {
      await onSend(body, isPrivate, pending.map((file) => file.id));
      setDraft('');
      setIsPrivate(false);
      setPending([]);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not send');
    } finally {
      setSending(false);
    }
  };

  const pickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const uploaded = await api.uploadAttachment(file);
        setPending((current) => [...current, uploaded]);
      }
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not upload that file');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const suggest = async () => {
    setDrafting(true);
    try {
      const suggestion = await api.draftReply(conversation.id);
      if (!suggestion.text) {
        toast.info('The knowledge base has nothing on this yet.');
        return;
      }
      setDraft(suggestion.text);
      setIsPrivate(false);
      composerRef.current?.focus();
      if (suggestion.shouldEscalate) {
        toast.info('Low confidence, so read this one carefully before you send it.');
      }
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not draft a reply');
    } finally {
      setDrafting(false);
    }
  };

  const mine = conversation.assignedUserId === user?.id;
  const resolved = conversation.status === 'resolved';

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-bg">
      <header className="veil sticky top-0 z-10 flex items-center gap-2.5 border-b border-line px-3 py-2.5 sm:px-4">
        {onBack ? (
          <Button variant="ghost" size="icon" onClick={onBack} aria-label="Back to list">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        ) : null}
        <Avatar name={conversation.customer?.name} size="sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-medium text-ink">
            {conversation.subject ?? 'Conversation'}
          </p>
          <p className="flex items-center gap-1.5 truncate text-xs text-ink-muted">
            <ChannelIcon channel={conversation.channel} className="h-3 w-3" />
            {CHANNEL_LABELS[conversation.channel]} · {conversation.customer?.name ?? 'Unknown'}
          </p>
        </div>
        <Badge tone={statusTone(conversation.status)}>
          {STATUS_LABELS[conversation.status] ?? conversation.status}
        </Badge>
        {!mine && !resolved ? (
          <Button variant="secondary" size="sm" onClick={onAssignToMe} icon={<UserPlus className="h-3.5 w-3.5" />}>
            <span className="hidden sm:inline">Assign to me</span>
          </Button>
        ) : null}
        {!resolved ? (
          <Button variant="secondary" size="sm" onClick={onResolve} icon={<Check className="h-3.5 w-3.5" />}>
            <span className="hidden sm:inline">Resolve</span>
          </Button>
        ) : null}
      </header>

      <div className="scroll-slim min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:px-6">
        {groupByDay(conversation.messages).map(([day, messages]) => (
          <div key={day} className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="h-px flex-1 bg-line-subtle" />
              <span className="text-2xs font-medium uppercase tracking-wide text-ink-muted">{day}</span>
              <span className="h-px flex-1 bg-line-subtle" />
            </div>
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <footer className="border-t border-line bg-surface p-3 sm:p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <Button
            variant={isPrivate ? 'ghost' : 'secondary'}
            size="sm"
            onClick={() => setIsPrivate(false)}
            className={cn(!isPrivate && 'border-accent-border bg-accent-soft text-accent-text')}
          >
            Reply
          </Button>
          <Button
            variant={isPrivate ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setIsPrivate(true)}
            icon={<StickyNote className="h-3.5 w-3.5" />}
            className={cn(isPrivate && 'border-warning/40 bg-warning-soft text-warning')}
          >
            Internal note
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={suggest}
            loading={drafting}
            icon={<WandSparkles className="h-3.5 w-3.5" />}
            className="ml-auto"
          >
            Draft with AI
          </Button>
        </div>

        <div
          className={cn(
            'rounded-lg border bg-surface transition-colors',
            isPrivate ? 'border-warning/40 bg-warning-soft/40' : 'border-line',
          )}
        >
          <textarea
            ref={composerRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends. Shift and Enter, or the command key, insert a newline.
              if (event.key === 'Enter' && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
                event.preventDefault();
                void submit();
              }
            }}
            rows={3}
            placeholder={
              isPrivate
                ? 'Internal note, the customer never sees this'
                : `Reply on ${CHANNEL_LABELS[conversation.channel]}`
            }
            className="scroll-slim w-full resize-none bg-transparent px-3 py-2.5 text-base text-ink outline-none placeholder:text-ink-muted"
          />
          {pending.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 border-t border-line-subtle px-3 py-2">
              {pending.map((file) => (
                <span
                  key={file.id}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-line bg-sunken py-1 pl-2 pr-1 text-2xs text-ink"
                >
                  <Paperclip className="h-3 w-3 shrink-0 text-ink-muted" />
                  <span className="truncate">{file.filename}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${file.filename}`}
                    onClick={() => setPending((current) => current.filter((f) => f.id !== file.id))}
                    className="rounded p-0.5 text-ink-muted transition-colors hover:bg-hover hover:text-ink"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-line-subtle px-3 py-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <input
                ref={fileRef}
                type="file"
                multiple
                hidden
                onChange={(event) => void pickFiles(event.target.files)}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Attach a file"
                onClick={() => fileRef.current?.click()}
                loading={uploading}
              >
                <Paperclip className="h-4 w-4" />
              </Button>
              <p className="hidden text-2xs text-ink-muted sm:block">
                <kbd className="rounded border border-line bg-sunken px-1">Enter</kbd> to send ·{' '}
                <kbd className="rounded border border-line bg-sunken px-1">⇧Enter</kbd> for a new line
              </p>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={submit}
              disabled={!draft.trim() && pending.length === 0}
              loading={sending}
              icon={<Send className="h-3.5 w-3.5" />}
            >
              {isPrivate ? 'Save note' : 'Send'}
            </Button>
          </div>
        </div>
      </footer>
    </section>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const outbound = message.authorType === 'agent' || message.authorType === 'ai';

  if (message.authorType === 'system') {
    return (
      <p className="mx-auto max-w-lg rounded-md border border-dashed border-line px-3 py-1.5 text-center text-xs text-ink-muted">
        {message.body}
      </p>
    );
  }

  const confidence = typeof message.meta.confidence === 'number' ? message.meta.confidence : null;
  const citations = Array.isArray(message.meta.citations) ? message.meta.citations : [];

  return (
    <div className={cn('flex gap-2.5', outbound && 'flex-row-reverse')}>
      <Avatar name={message.authorName} size="sm" ai={message.authorType === 'ai'} />
      <div className={cn('min-w-0 max-w-[min(78%,42rem)]', outbound && 'items-end text-right')}>
        <div className="mb-1 flex items-center gap-2 text-2xs text-ink-muted">
          {outbound ? null : <span className="font-medium">{message.authorName}</span>}
          <span>{formatTime(message.createdAt)}</span>
          {outbound ? <span className="font-medium">{message.authorName}</span> : null}
        </div>
        {message.body ? (
          <div
            className={cn(
              'rounded-xl px-3.5 py-2.5 text-left text-base leading-relaxed whitespace-pre-wrap',
              message.isPrivate
                ? 'border border-warning/40 bg-warning-soft text-ink'
                : outbound
                  ? 'rounded-tr-sm bg-accent-soft text-ink'
                  : 'rounded-tl-sm border border-line bg-surface text-ink',
            )}
          >
            {message.body}
          </div>
        ) : null}

        {/* A photo of the damaged item is often the whole message. */}
        <AttachmentList attachments={message.attachments ?? []} className={cn(outbound && 'flex flex-col items-end')} />

        {message.isPrivate ? (
          <p className="mt-1 text-2xs font-medium text-warning">Internal note, not sent</p>
        ) : null}

        {confidence !== null ? (
          <div className={cn('mt-1.5 flex flex-wrap items-center gap-1.5', outbound && 'justify-end')}>
            <span className="inline-flex items-center gap-1 text-2xs text-ink-muted">
              <Sparkles className="h-3 w-3" />
              {Math.round(confidence * 100)}% confidence
            </span>
            {citations.slice(0, 2).map((citation) => (
              <Badge key={citation.articleId} tone="neutral" className="text-[10px]">
                {citation.title}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Group messages into day buckets, preserving order. */
function groupByDay(messages: Message[]): [string, Message[]][] {
  const groups = new Map<string, Message[]>();
  for (const message of messages) {
    const key = dayLabel(message.createdAt);
    const bucket = groups.get(key);
    if (bucket) bucket.push(message);
    else groups.set(key, [message]);
  }
  return [...groups.entries()];
}

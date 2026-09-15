import * as React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, Paperclip, Send, Sparkles } from '@/components/icons';
import { AttachmentList } from '@/components/AttachmentList';
import { LogoMark } from '@/components/brand/Logo';
import { Avatar, Button, ErrorState, Spinner } from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync, useLocalStorage } from '@/hooks';
import { formatTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Attachment, Message } from '@/lib/types';

const SUGGESTIONS = [
  'How long do I have to return something',
  'Where is my order',
  'Is the jacket covered by warranty',
];

/** The chat customers use. */
export default function PortalPage() {
  const api = useApi();
  const { mode } = useSession();
  const [params] = useSearchParams();

  const config = useAsync(() => api.portalConfig(params.get('key') ?? undefined), [api, params]);

  const [sessionId, setSessionId] = useLocalStorage<string | null>('ucsp.portal-session', null);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [draft, setDraft] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const [pending, setPending] = React.useState<Attachment[]>([]);
  const previews = React.useRef(new Map<string, string>());
  const [uploading, setUploading] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [escalated, setEscalated] = React.useState(false);
  const [loadingHistory, setLoadingHistory] = React.useState(Boolean(sessionId));
  const endRef = React.useRef<HTMLDivElement>(null);
  const ownSessions = React.useRef(new Set<string>());

  const publicKey = config.data?.publicKey ?? '';

  /** Files load through the visitor's own session, since nobody is signed in here. */
  const fileUrl = React.useCallback(
    (file: Attachment) => {
      const local = previews.current.get(file.id);
      if (local) return local;
      return sessionId
        ? `/api/v1/widget/${publicKey}/sessions/${encodeURIComponent(sessionId)}/attachments/${file.id}`
        : file.url;
    },
    [publicKey, sessionId],
  );

  // Object URLs hold the file in memory until they are released.
  React.useEffect(() => {
    const held = previews.current;
    return () => {
      held.forEach((url) => URL.revokeObjectURL(url));
      held.clear();
    };
  }, []);
  const greeting = config.data?.greeting ?? '';
  const companyName = config.data?.workspaceName ?? '';

  React.useEffect(() => {
    if (!sessionId || !publicKey) {
      setLoadingHistory(false);
      return;
    }
    if (ownSessions.current.has(sessionId)) {
      setLoadingHistory(false);
      return;
    }
    let active = true;
    api
      .portalHistory(publicKey, sessionId)
      .then((history) => {
        if (active) setMessages((current) => merge(current, history));
      })
      .catch(() => {
        /* A missing history just starts a fresh conversation. */
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => {
      active = false;
    };
  }, [api, sessionId, publicKey]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, sending]);

  const pickFile = async (files: FileList | null) => {
    if (!files || files.length === 0 || !publicKey) return;
    setUploading(true);
    let session = sessionId;
    try {
      for (const file of Array.from(files)) {
        const uploaded = await api.portalUpload(publicKey, file, session ?? undefined);
        if (!session) {
          session = uploaded.sessionId;
          ownSessions.current.add(uploaded.sessionId);
          setSessionId(uploaded.sessionId);
        }
        previews.current.set(uploaded.id, URL.createObjectURL(file));
        setPending((current) => [...current, uploaded]);
      }
    } catch {
      setMessages((current) => [
        ...current,
        systemLine('That file could not be attached. It may be too large, or a type we do not accept.'),
      ]);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const send = async (text: string) => {
    const body = text.trim();
    // A photo on its own is a normal way to ask for help.
    if ((!body && pending.length === 0) || sending || !publicKey) return;

    // Show the message straight away. The round trip only adds the reply.
    const attachmentIds = pending.map((file) => file.id);
    const optimistic: Message = {
      id: `local-${Date.now()}`,
      conversationId: 'pending',
      authorType: 'customer',
      authorName: 'You',
      body,
      isPrivate: false,
      meta: {},
      createdAt: new Date().toISOString(),
      attachments: pending,
    };
    setMessages((current) => [...current, optimistic]);
    setDraft('');
    setPending([]);
    setSending(true);

    try {
      const result = await api.portalSend({
        publicKey,
        sessionId: sessionId ?? undefined,
        body,
        attachmentIds,
      });
      if (!sessionId) {
        ownSessions.current.add(result.sessionId);
        setSessionId(result.sessionId);
      }
      setEscalated(result.escalated);
      if (result.reply) setMessages((current) => [...current, result.reply as Message]);
    } catch {
      setMessages((current) => [
        ...current,
        systemLine('That message did not go through. Please try again.'),
      ]);
    } finally {
      setSending(false);
    }
  };

  if (config.loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  if (config.error || !publicKey) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg p-6">
        <ErrorState
          error={
            config.error ??
            new Error('No workspace is set up for this portal yet. Add a workspace key to the URL.')
          }
          onRetry={config.reload}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="veil sticky top-0 z-10 border-b border-line">
        <div className="mx-auto flex h-14 max-w-2xl items-center gap-3 px-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-soft">
            <LogoMark size={18} className="text-accent" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold text-ink">{companyName}</p>
            <p className="truncate text-2xs text-ink-muted">
              We reply as soon as we can
            </p>
          </div>
          <Link to="/">
            <Button variant="ghost" size="sm" icon={<ArrowLeft className="h-3.5 w-3.5" />}>
              <span className="hidden sm:inline">Back to site</span>
            </Button>
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4">
        <div className="flex-1 space-y-4 py-6">
          <div className="flex gap-2.5">
            <Avatar name="Assistant" size="sm" ai />
            <div className="rounded-xl rounded-tl-sm border border-line bg-surface px-3.5 py-2.5 text-base text-ink">
              {greeting}
            </div>
          </div>

          {loadingHistory ? <Spinner className="mx-auto" /> : null}

          {messages.map((message) => (
            <PortalMessage key={message.id} message={message} fileUrl={fileUrl} />
          ))}

          {sending ? (
            <div className="flex gap-2.5">
              <Avatar name="Assistant" size="sm" ai />
              <div className="flex items-center gap-1.5 rounded-xl rounded-tl-sm border border-line bg-surface px-3.5 py-3">
                <Dot delay="0ms" />
                <Dot delay="140ms" />
                <Dot delay="280ms" />
              </div>
            </div>
          ) : null}

          {escalated && !sending ? (
            <p className="mx-auto max-w-md rounded-lg border border-dashed border-line px-3 py-2 text-center text-sm text-ink-muted">
              A teammate is picking this up and will reply here shortly.
            </p>
          ) : null}

          <div ref={endRef} />
        </div>

        {messages.length === 0 && !loadingHistory ? (
          <div className="mb-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => send(suggestion)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:border-accent-border hover:bg-accent-soft hover:text-accent-text"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}
      </main>

      <footer className="sticky bottom-0 border-t border-line bg-surface">
        <div className="mx-auto max-w-2xl p-3 sm:p-4">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void send(draft);
            }}
            className="flex items-end gap-2"
          >
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send(draft);
                }
              }}
              rows={1}
              placeholder="Type your message"
              aria-label="Your message"
              className={cn(
                'scroll-slim max-h-32 min-h-[40px] flex-1 resize-none rounded-lg border border-line bg-surface',
                'px-3.5 py-2.5 text-base text-ink outline-none transition-colors',
                'placeholder:text-ink-muted focus:border-accent focus:ring-2 focus:ring-accent/25',
              )}
            />
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              onChange={(event) => void pickFile(event.target.files)}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Attach a file"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="icon"
              disabled={(!draft.trim() && pending.length === 0) || sending}
              aria-label="Send"
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
          <p className="mt-2 text-center text-2xs text-ink-muted">
            {mode === 'demo'
              ? 'Demo mode. Answers come from the sample knowledge base, in your browser.'
              : 'Answers are drawn from our published help articles. We hand over to a person when they do not cover your question.'}
          </p>
        </div>
      </footer>
    </div>
  );
}

/** Fold a server transcript into what is already on screen. */
function merge(current: Message[], history: Message[]): Message[] {
  const known = new Set(history.map((message) => message.id));
  const sent = new Set(
    history.filter((message) => message.authorType === 'customer').map((message) => message.body),
  );
  const localOnly = current.filter(
    (message) =>
      !known.has(message.id) && !(message.authorType === 'customer' && sent.has(message.body)),
  );
  return [...history, ...localOnly].sort(
    (a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt),
  );
}

/** A grey line in the transcript that is from us, not from anyone. */
function systemLine(body: string): Message {
  return {
    id: `system-${Date.now()}`,
    conversationId: 'pending',
    authorType: 'system',
    authorName: 'System',
    body,
    isPrivate: false,
    meta: {},
    createdAt: new Date().toISOString(),
  };
}

function PortalMessage({
  message,
  fileUrl,
}: {
  message: Message;
  fileUrl: (file: Attachment) => string;
}) {
  if (message.authorType === 'system') {
    return (
      <p className="mx-auto max-w-md rounded-lg border border-dashed border-line px-3 py-2 text-center text-sm text-ink-muted">
        {message.body}
      </p>
    );
  }

  const mine = message.authorType === 'customer';
  const citations = Array.isArray(message.meta.citations) ? message.meta.citations : [];

  return (
    <div className={cn('flex gap-2.5', mine && 'flex-row-reverse')}>
      <Avatar
        name={message.authorName}
        size="sm"
        ai={message.authorType === 'ai'}
      />
      <div className={cn('max-w-[80%]', mine && 'text-right')}>
        <div
          className={cn(
            'whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-left text-base leading-relaxed',
            mine
              ? 'rounded-tr-sm bg-accent text-white'
              : 'rounded-tl-sm border border-line bg-surface text-ink',
          )}
        >
          {message.body}
        </div>
        <AttachmentList
          attachments={message.attachments ?? []}
          className={cn(mine && 'flex flex-col items-end')}
          resolveUrl={fileUrl}
        />
        <p className={cn('mt-1 text-2xs text-ink-muted', mine && 'text-right')}>
          {formatTime(message.createdAt)}
        </p>
        {citations.length ? (
          <p className="mt-0.5 inline-flex items-center gap-1 text-2xs text-ink-muted">
            <BookOpen className="h-3 w-3" />
            From {citations.map((citation) => citation.title).join(', ')}
          </p>
        ) : null}
        {message.authorType === 'ai' ? (
          <p className="mt-0.5 inline-flex items-center gap-1 text-2xs text-ink-muted">
            <Sparkles className="h-3 w-3" />
            Answered from our help articles
          </p>
        ) : null}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-muted"
      style={{ animationDelay: delay, animationDuration: '1s' }}
    />
  );
}

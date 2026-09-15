import * as React from 'react';
import {
  AlertTriangle,
  BookOpen,
  Check,
  Copy,
  Info,
  Mic,
  MicOff,
  PhoneCall,
  Play,
  Send,
  Sparkles,
  StopCircle,
} from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  Spinner,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';
import { formatDateTime, formatTime, plural, relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { TapSession, TapSuggestion } from '@/lib/types';
import { createSpeechListener, speechRecognitionSupported, type SpeechListener } from './speech';

/** A scripted caller, so the feature can be demonstrated without a microphone. */
const SCRIPT = [
  'Hi, I ordered a jacket about six weeks ago and I want to send it back, it still has the tags on.',
  'It was ninety pounds so I would rather have the money back than store credit.',
  'One more thing, the sleeping bag I bought at the same time arrived squashed into a tiny sack.',
  'Honestly if this is difficult I would rather just speak to a manager about it.',
];

const KIND_STYLE: Record<TapSuggestion['kind'], { tone: 'accent' | 'success' | 'warning' | 'info'; border: string }> = {
  answer: { tone: 'accent', border: 'border-l-accent' },
  action: { tone: 'success', border: 'border-l-success' },
  warning: { tone: 'warning', border: 'border-l-warning' },
  question: { tone: 'info', border: 'border-l-info' },
};

/** Tap AI, live call assistance. */
export default function TapPage() {
  const api = useApi();
  const { aiEnabled, mode } = useSession();
  const toast = useToast();

  const history = useAsync(() => api.listTapSessions(), [api]);
  const [session, setSession] = React.useState<TapSession | null>(null);
  const [listening, setListening] = React.useState(false);
  const [interim, setInterim] = React.useState('');
  const [typed, setTyped] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [scriptIndex, setScriptIndex] = React.useState(0);

  const listenerRef = React.useRef<SpeechListener | null>(null);
  const transcriptEndRef = React.useRef<HTMLDivElement>(null);
  const supported = React.useMemo(speechRecognitionSupported, []);

  React.useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: 'end' });
  }, [session?.transcript.length, interim]);

  // Stop the microphone if the page closes while a call is running.
  React.useEffect(() => () => listenerRef.current?.stop(), []);

  const sessionRef = React.useRef<TapSession | null>(null);
  sessionRef.current = session;

  const pushUtterance = React.useCallback(
    async (speaker: 'customer' | 'agent', text: string) => {
      const current = sessionRef.current;
      if (!current || !text.trim()) return;
      setBusy(true);
      try {
        setSession(await api.addUtterance(current.id, { speaker, text: text.trim() }));
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : 'Could not send that line');
      } finally {
        setBusy(false);
      }
    },
    [api, toast],
  );

  const start = async () => {
    try {
      const started = await api.startTapSession('Live call');
      setSession(started);
      setScriptIndex(0);
      history.reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not start the session');
    }
  };

  const end = async () => {
    if (!session) return;
    stopListening();
    try {
      const ended = await api.endTapSession(session.id);
      setSession(ended);
      history.reload();
      toast.success('Call ended');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not end the session');
    }
  };

  const startListening = () => {
    const listener = createSpeechListener({
      onFinal: (text) => {
        setInterim('');
        void pushUtterance('customer', text);
      },
      onInterim: setInterim,
      onError: (message) => toast.error(`Microphone: ${message}`),
    });
    if (!listener) {
      toast.error('This browser does not support speech recognition');
      return;
    }
    listenerRef.current = listener;
    listener.start();
    setListening(true);
  };

  const stopListening = () => {
    listenerRef.current?.stop();
    listenerRef.current = null;
    setListening(false);
    setInterim('');
  };

  const playScriptLine = () => {
    if (scriptIndex >= SCRIPT.length) {
      toast.info('That is the end of the sample call.');
      return;
    }
    void pushUtterance('customer', SCRIPT[scriptIndex]);
    setScriptIndex((index) => index + 1);
  };

  const live = session?.status === 'live';

  return (
    <Page className="space-y-4">
      <PageHeader
        title="Tap AI"
        description="Listens to a call in progress and puts the next move in front of you. It never speaks to the customer."
        actions={
          live ? (
            <Button variant="danger" onClick={end} icon={<StopCircle className="h-4 w-4" />}>
              End call
            </Button>
          ) : (
            <Button variant="primary" onClick={start} icon={<PhoneCall className="h-4 w-4" />}>
              Start a call
            </Button>
          )
        }
      />

      {!aiEnabled ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-line bg-surface px-3.5 py-3">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
          <p className="text-sm text-ink-secondary">
            {mode === 'demo'
              ? 'Running on the sample workspace. Suggestions come from retrieval over the demo knowledge base, the same path a self hosted install takes before an LLM key is added.'
              : 'No language model is configured, so suggestions are retrieved passages rather than written coaching. Set LLM_PROVIDER to enable the full behaviour.'}
          </p>
        </div>
      ) : null}

      {!session ? (
        <Card>
          <EmptyState
            icon={<PhoneCall className="h-5 w-5" />}
            title="No call in progress"
            description="Start a session, then either speak into your microphone or play the sample call to watch suggestions arrive."
            action={
              <Button variant="primary" onClick={start}>
                Start a call
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
          <Card flush className="flex min-h-[440px] flex-col">
            <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-3">
              {live ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-danger">
                  <span className="animate-pulse-ring h-2 w-2 rounded-full bg-danger" />
                  Live
                </span>
              ) : (
                <Badge tone="neutral">Ended</Badge>
              )}
              <span className="text-sm text-ink-muted">
                {session.customerLabel} · started {relativeTime(session.createdAt)}
              </span>

              {live ? (
                <div className="ml-auto flex items-center gap-1.5">
                  {supported ? (
                    <Button
                      variant={listening ? 'danger' : 'secondary'}
                      size="sm"
                      onClick={listening ? stopListening : startListening}
                      icon={
                        listening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />
                      }
                    >
                      {listening ? 'Stop mic' : 'Use microphone'}
                    </Button>
                  ) : null}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={playScriptLine}
                    icon={<Play className="h-3.5 w-3.5" />}
                  >
                    Play sample line
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="scroll-slim min-h-0 flex-1 space-y-2.5 overflow-y-auto p-4">
              {session.transcript.length === 0 ? (
                <p className="py-10 text-center text-sm text-ink-muted">
                  {supported
                    ? 'Turn on the microphone, or play a sample line to see how it works.'
                    : 'This browser has no speech recognition. Type what the caller says below, or play the sample call.'}
                </p>
              ) : (
                session.transcript.map((line) => (
                  <div
                    key={line.id}
                    className={cn(
                      'rounded-lg px-3 py-2',
                      line.speaker === 'customer'
                        ? 'border border-line bg-surface'
                        : 'ml-8 bg-accent-soft',
                    )}
                  >
                    <p className="mb-0.5 flex items-center justify-between gap-2 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
                      <span>{line.speaker === 'customer' ? 'Caller' : 'You'}</span>
                      <span className="font-normal normal-case tracking-normal">
                        {formatTime(line.at)}
                      </span>
                    </p>
                    <p className="text-sm text-ink">{line.text}</p>
                  </div>
                ))
              )}
              {interim ? (
                <div className="rounded-lg border border-dashed border-line px-3 py-2">
                  <p className="text-sm italic text-ink-muted">{interim}</p>
                </div>
              ) : null}
              <div ref={transcriptEndRef} />
            </div>

            {live ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void pushUtterance('customer', typed);
                  setTyped('');
                }}
                className="flex gap-2 border-t border-line-subtle p-3"
              >
                <Input
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  placeholder="Type what the caller said"
                  aria-label="Transcript entry"
                />
                <Button
                  type="submit"
                  variant="secondary"
                  disabled={!typed.trim()}
                  loading={busy}
                  icon={<Send className="h-3.5 w-3.5" />}
                >
                  Add
                </Button>
              </form>
            ) : null}
          </Card>

          <div className="space-y-4">
            <Card flush className="flex max-h-[440px] flex-col">
              <div className="border-b border-line-subtle px-4 py-3">
                <CardHeader
                  className="mb-0"
                  title="Suggestions"
                  description="Grounded in your knowledge base"
                  action={busy ? <Spinner /> : <Sparkles className="h-4 w-4 text-ink-muted" />}
                />
              </div>
              <div className="scroll-slim min-h-0 flex-1 space-y-2.5 overflow-y-auto p-3">
                {session.suggestions.length === 0 ? (
                  <p className="py-10 text-center text-sm text-ink-muted">
                    Suggestions appear as soon as the caller says something the knowledge base covers.
                  </p>
                ) : (
                  [...session.suggestions].reverse().map((suggestion) => (
                    <SuggestionCard key={suggestion.id} suggestion={suggestion} />
                  ))
                )}
              </div>
            </Card>

            {session.summary ? (
              <Card>
                <CardHeader title="Call summary" description={formatDateTime(session.createdAt)} />
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-secondary">
                  {session.summary}
                </p>
              </Card>
            ) : null}
          </div>
        </div>
      )}

      <Card flush>
        <div className="p-4">
          <CardHeader title="Recent calls" description="Transcripts and summaries are kept with the workspace" />
        </div>
        {history.loading ? (
          <div className="px-4 pb-4">
            <Spinner />
          </div>
        ) : (history.data ?? []).length === 0 ? (
          <EmptyState title="No calls yet" />
        ) : (
          <ul className="divide-y divide-line-subtle border-t border-line-subtle">
            {(history.data ?? []).slice(0, 8).map((row) => {
              const item = row.id === session?.id ? session : row;
              return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setSession(item)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-hover"
                >
                  <PhoneCall className="h-4 w-4 shrink-0 text-ink-muted" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-base text-ink">{item.customerLabel}</span>
                    <span className="block truncate text-xs text-ink-muted">
                      {plural(item.transcript.length, 'line')} · {plural(item.suggestions.length, 'suggestion')} ·{' '}
                      {formatDateTime(item.createdAt)}
                    </span>
                  </span>
                  <Badge tone={item.status === 'live' ? 'danger' : 'neutral'}>{item.status}</Badge>
                </button>
              </li>
              );
            })}
          </ul>
        )}
      </Card>
    </Page>
  );
}

function SuggestionCard({ suggestion }: { suggestion: TapSuggestion }) {
  const [copied, setCopied] = React.useState(false);
  const style = KIND_STYLE[suggestion.kind] ?? KIND_STYLE.answer;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(suggestion.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be denied. The text is on screen either way.
    }
  };

  return (
    <article
      className={cn('animate-fade-up rounded-lg border border-l-2 border-line bg-surface p-3', style.border)}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <Badge tone={style.tone} className="text-[10px] uppercase">
          {suggestion.kind}
        </Badge>
        <span className="numeric text-2xs text-ink-muted">
          {Math.round(suggestion.confidence * 100)}%
        </span>
        <button
          type="button"
          onClick={copy}
          className="ml-auto text-ink-muted transition-colors hover:text-ink"
          aria-label="Copy suggestion"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <p className="text-sm leading-relaxed text-ink">{suggestion.text}</p>
      {suggestion.citations?.length ? (
        <p className="mt-2 inline-flex items-center gap-1 text-2xs text-ink-muted">
          <BookOpen className="h-3 w-3" />
          {suggestion.citations.map((citation) => citation.title).join(' · ')}
        </p>
      ) : null}
      {suggestion.kind === 'warning' ? (
        <p className="mt-2 inline-flex items-center gap-1 text-2xs text-warning">
          <AlertTriangle className="h-3 w-3" />
          Say this before committing to anything
        </p>
      ) : null}
    </article>
  );
}

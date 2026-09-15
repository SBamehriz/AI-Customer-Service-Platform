import * as React from 'react';
import { AlertTriangle, BookOpen, Sparkles } from '@/components/icons';
import { Badge, Button, Card, CardHeader, Input, Spinner } from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import type { Draft } from '@/lib/types';

export interface AssistantPanelProps {
  initialQuestion?: string;
}

/** Ask the assistant a question and see what it would answer, with its sources. */
export function AssistantPanel({ initialQuestion = '' }: AssistantPanelProps) {
  const api = useApi();
  const { mode, aiEnabled } = useSession();
  const [question, setQuestion] = React.useState(initialQuestion);
  const [draft, setDraft] = React.useState<Draft | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const ask = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      try {
        setDraft(await api.askAssistant(trimmed));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Could not reach the assistant');
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  // Deep links from the command palette arrive with the question prefilled.
  React.useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
      void ask(initialQuestion);
    }
  }, [initialQuestion, ask]);

  const retrievalOnly = mode === 'demo' || !aiEnabled;

  return (
    <Card>
      <CardHeader
        title="Test the assistant"
        description="Ask what a customer would ask."
        action={<Sparkles className="h-4 w-4 text-ink-muted" />}
      />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
        className="flex gap-2"
      >
        <Input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="How long do I have to return something?"
          aria-label="Question for the assistant"
        />
        <Button type="submit" variant="secondary" loading={loading} disabled={!question.trim()}>
          Ask
        </Button>
      </form>

      {retrievalOnly ? (
        <p className="mt-2.5 text-xs text-ink-muted">
          No language model is configured, so answers come straight from retrieval. Set{' '}
          <code className="rounded bg-sunken px-1 font-mono text-[11px]">LLM_PROVIDER</code> to get
          written replies.
        </p>
      ) : null}

      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}

      {loading && !draft ? <Spinner className="mt-4" /> : null}

      {draft ? (
        <div className="mt-4 space-y-3 border-t border-line-subtle pt-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={draft.confidence >= 0.5 ? 'success' : 'warning'}>
              {Math.round(draft.confidence * 100)}% confidence
            </Badge>
            <Badge tone="neutral">{draft.engine}</Badge>
            {draft.shouldEscalate ? (
              <Badge tone="danger" dot>
                Would escalate
              </Badge>
            ) : null}
          </div>

          <p className="whitespace-pre-wrap rounded-lg bg-sunken px-3 py-2.5 text-sm leading-relaxed text-ink">
            {draft.text}
          </p>

          {draft.shouldEscalate ? (
            <p className="flex items-start gap-2 text-xs text-warning">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              The knowledge base does not cover this well. A customer asking it would be handed to a
              human, which is the right outcome, though an article would be better.
            </p>
          ) : null}

          {draft.citations.length ? (
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
                <BookOpen className="h-3 w-3" />
                Grounded in
              </p>
              <ul className="space-y-1.5">
                {draft.citations.map((citation) => (
                  <li
                    key={citation.articleId}
                    className="rounded-md border border-line px-2.5 py-2 text-xs"
                  >
                    <p className="font-medium text-ink">{citation.title}</p>
                    <p className="mt-0.5 line-clamp-2 text-ink-muted">{citation.excerpt}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

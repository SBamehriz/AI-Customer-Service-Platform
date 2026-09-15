import * as React from 'react';
import { Check, Code, Copy, Eye, EyeOff, KeyRound, RefreshCw } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  SegmentedControl,
  Skeleton,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';

/** API access and the integration surface, for people wiring this into their own stack. */
export function DeveloperSettings() {
  const api = useApi();
  const toast = useToast();
  const { mode, aiEnabled } = useSession();
  const workspace = useAsync(() => api.getWorkspace(), [api]);
  const [apiKey, setApiKey] = React.useState<string | null>(null);
  const [rotating, setRotating] = React.useState(false);

  const rotate = async () => {
    setRotating(true);
    try {
      const key = await api.rotateApiKey();
      setApiKey(key);
      toast.success('New API key issued, the previous one no longer works');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not issue a key');
    } finally {
      setRotating(false);
    }
  };

  if (workspace.loading) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Workspace keys"
          description="The public key identifies the workspace to the widget. The secret key authenticates server to server calls."
        />
        <div className="space-y-3">
          <KeyRow label="Public key" value={workspace.data?.publicKey ?? ''} />

          <div className="rounded-lg border border-line px-3.5 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-ink-muted" />
                <span className="text-base font-medium text-ink">Secret API key</span>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={rotate}
                loading={rotating}
                icon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                {apiKey ? 'Rotate again' : 'Issue a key'}
              </Button>
            </div>
            {apiKey ? (
              <div className="mt-2.5">
                <KeyRow label="" value={apiKey} secret />
                <p className="mt-1.5 text-xs text-warning">
                  Copy this now. Only its hash is stored, so it cannot be shown again.
                </p>
              </div>
            ) : (
              <p className="mt-1.5 text-xs text-ink-muted">
                Issuing a key invalidates the previous one immediately.
              </p>
            )}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Runtime" description="What this instance is actually configured with." />
        <dl className="space-y-2.5 text-sm">
          <StatusRow label="Mode">
            <Badge tone={mode === 'live' ? 'success' : 'warning'}>
              {mode === 'live' ? 'Connected to a backend' : 'Demo, sample data in your browser'}
            </Badge>
          </StatusRow>
          <StatusRow label="Language model">
            <Badge tone={aiEnabled ? 'success' : 'neutral'}>
              {aiEnabled ? 'Configured' : 'Retrieval only'}
            </Badge>
          </StatusRow>
          <StatusRow label="Knowledge retrieval">
            <span className="text-ink">BM25 over published articles, embeddings optional</span>
          </StatusRow>
        </dl>
        {!aiEnabled ? (
          <p className="mt-3.5 rounded-lg bg-sunken px-3 py-2.5 text-xs leading-relaxed text-ink-secondary">
            Without a model the platform still retrieves and cites the right article, it just
            quotes it instead of rewriting it. Add a key below to turn on written replies.
          </p>
        ) : null}
      </Card>

      <ConnectAModel aiEnabled={aiEnabled} />

      <Card>
        <CardHeader
          title="Push a message in from your own code"
          description="Authenticate with the secret key. The message goes through the same ingest path as every channel."
          action={<Code className="h-4 w-4 text-ink-muted" />}
        />
        <pre className="scroll-slim overflow-x-auto rounded-lg border border-line bg-sunken px-3.5 py-3 font-mono text-xs leading-relaxed text-ink">
{`curl -X POST https://your-domain.example/api/v1/tickets \\
  -H "Authorization: Bearer sk_your_secret_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "subject": "Order MO-48221 never arrived",
    "description": "Tracking has not moved in four days.",
    "priority": "high",
    "channel": "api",
    "customerEmail": "customer@example.com"
  }'`}
        </pre>
        <p className="mt-2.5 text-xs text-ink-muted">
          The full OpenAPI schema is served at <code className="font-mono">/docs</code> on the backend.
        </p>
      </Card>
    </div>
  );
}

function KeyRow({ label, value, secret }: { label: string; value: string; secret?: boolean }) {
  const [revealed, setRevealed] = React.useState(!secret);

  return (
    <div className="flex items-center gap-2">
      {label ? <span className="w-24 shrink-0 text-sm text-ink-muted">{label}</span> : null}
      <code className="scroll-slim min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-md border border-line bg-sunken px-2.5 py-1.5 font-mono text-xs text-ink">
        {revealed ? value : '•'.repeat(Math.min(44, value.length))}
      </code>
      {secret ? (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setRevealed(!revealed)}
          aria-label={revealed ? 'Hide' : 'Reveal'}
        >
          {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </Button>
      ) : null}
      <CopyButton value={value} />
    </div>
  );
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard denied. The value can still be selected.
    }
  };

  return (
    <Button variant="ghost" size="icon" onClick={copy} aria-label="Copy">
      {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
    </Button>
  );
}

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}


interface ProviderRecipe {
  id: string;
  label: string;
  blurb: string;
  keyUrl?: string;
  env: string;
}

/** Every provider this build speaks, as lines you can paste. */
const RECIPES: ProviderRecipe[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    blurb: 'Also the setting for Groq, Together, OpenRouter, Mistral and vLLM.',
    keyUrl: 'https://platform.openai.com/api-keys',
    env: ['LLM_PROVIDER=openai', 'LLM_API_KEY=sk-your-key', 'LLM_MODEL=gpt-4o-mini'].join('\n'),
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    blurb: 'Claude models, called directly.',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    env: [
      'LLM_PROVIDER=anthropic',
      'LLM_API_KEY=sk-ant-your-key',
      'LLM_MODEL=claude-sonnet-4-5',
    ].join('\n'),
  },
  {
    id: 'gemini',
    label: 'Gemini',
    blurb: 'Google AI Studio keys.',
    keyUrl: 'https://aistudio.google.com/apikey',
    env: [
      'LLM_PROVIDER=gemini',
      'LLM_API_KEY=your-key',
      'LLM_MODEL=gemini-2.0-flash',
    ].join('\n'),
  },
  {
    id: 'ollama',
    label: 'Local, Ollama',
    blurb: 'Runs on your own machine. No key, and nothing leaves the network.',
    env: [
      'LLM_PROVIDER=openai',
      'LLM_BASE_URL=http://localhost:11434/v1',
      'LLM_API_KEY=ollama',
      'LLM_MODEL=llama3.1',
    ].join('\n'),
  },
];

function ConnectAModel({ aiEnabled }: { aiEnabled: boolean }) {
  const [picked, setPicked] = React.useState(RECIPES[0].id);
  const recipe = RECIPES.find((entry) => entry.id === picked) ?? RECIPES[0];

  return (
    <Card>
      <CardHeader
        title="Connect a language model"
        description="Put these in your .env and restart the backend. Keys stay on the server and are never sent to the browser."
        action={
          <Badge tone={aiEnabled ? 'success' : 'neutral'}>
            {aiEnabled ? 'Connected' : 'Not connected'}
          </Badge>
        }
      />

      <SegmentedControl
        aria-label="Model provider"
        size="sm"
        options={RECIPES.map((entry) => ({ value: entry.id, label: entry.label }))}
        value={picked}
        onChange={setPicked}
        className="mb-3 w-full"
      />

      <p className="mb-2.5 text-sm text-ink-secondary">{recipe.blurb}</p>

      <div className="relative">
        <pre className="scroll-slim overflow-x-auto rounded-lg border border-line bg-sunken px-3.5 py-3 pr-12 font-mono text-xs leading-relaxed text-ink">
          {recipe.env}
        </pre>
        <span className="absolute right-1.5 top-1.5">
          <CopyButton value={recipe.env} />
        </span>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-secondary">
        {recipe.keyUrl ? (
          <>
            Get a key from{' '}
            <a
              href={recipe.keyUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-accent-text hover:underline"
            >
              {new URL(recipe.keyUrl).hostname}
            </a>
            .{' '}
          </>
        ) : null}
        Optional, set <code className="font-mono">EMBEDDING_MODEL</code> as well to add semantic
        retrieval alongside the keyword search. Everything works without any of this, answers are
        quoted from your articles rather than written.
      </p>
    </Card>
  );
}

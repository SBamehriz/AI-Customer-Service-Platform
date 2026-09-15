import * as React from 'react';
import { Check, Info, Sparkles, Zap } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  Field,
  Input,
  SegmentedControl,
  Skeleton,
  useToast,
} from '@/components/ui';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import type { AiConfig } from '@/lib/types';

type Provider = AiConfig['provider'];

interface Recipe {
  value: Provider;
  label: string;
  blurb: string;
  keyUrl?: string;
  keyHint: string;
  models: string[];
  baseUrl?: string;
}

/** What each provider needs, so nobody has to go and look it up. */
const RECIPES: Recipe[] = [
  {
    value: 'openai',
    label: 'OpenAI',
    blurb: 'Also the setting for Groq, Together, OpenRouter, vLLM and a local Ollama. Point the base URL at them.',
    keyUrl: 'https://platform.openai.com/api-keys',
    keyHint: 'Starts with sk-',
    models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'],
  },
  {
    value: 'anthropic',
    label: 'Anthropic',
    blurb: 'Claude models, called directly.',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    keyHint: 'Starts with sk-ant-',
    models: ['claude-sonnet-4-5', 'claude-haiku-4-5'],
  },
  {
    value: 'gemini',
    label: 'Gemini',
    blurb: 'Google AI Studio keys.',
    keyUrl: 'https://aistudio.google.com/apikey',
    keyHint: 'From AI Studio',
    models: ['gemini-2.0-flash', 'gemini-2.5-flash'],
  },
];

const LOCAL_BASE_URL = 'http://localhost:11434/v1';

/** Bring your own model, from the interface. */
export function AiSettings() {
  const api = useApi();
  const toast = useToast();
  const config = useAsync(() => api.getAiConfig(), [api]);

  const [provider, setProvider] = React.useState<Provider>('none');
  const [model, setModel] = React.useState('');
  const [baseUrl, setBaseUrl] = React.useState('');
  const [embeddingModel, setEmbeddingModel] = React.useState('');
  const [apiKey, setApiKey] = React.useState('');
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [result, setResult] = React.useState<{ ok: boolean; detail: string } | null>(null);

  React.useEffect(() => {
    if (!config.data) return;
    setProvider(config.data.provider);
    setModel(config.data.model);
    setBaseUrl(config.data.baseUrl);
    setEmbeddingModel(config.data.embeddingModel);
    setApiKey('');
    setResult(null);
  }, [config.data]);

  if (config.error) return <ErrorState error={config.error} onRetry={config.reload} />;
  if (config.loading || !config.data) return <Skeleton className="h-96" />;

  const current = config.data;
  const recipe = RECIPES.find((entry) => entry.value === provider);
  const locked = current.managedByEnv;

  const save = async () => {
    setSaving(true);
    setResult(null);
    try {
      const updated = await api.saveAiConfig({
        provider,
        model,
        baseUrl,
        embeddingModel,
        // Only send a key when one was typed, so a save never clears it.
        ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
      });
      config.setData(updated);
      setApiKey('');
      toast.success(provider === 'none' ? 'Model disconnected' : 'Saved');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await api.testAiConfig());
    } catch (cause) {
      setResult({ ok: false, detail: cause instanceof Error ? cause.message : 'Test failed' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Language model"
          description="Optional. Without one the platform still answers, by quoting the right article instead of writing a reply."
          action={
            <Badge tone={current.active ? 'success' : 'neutral'}>
              {current.active ? 'Connected' : 'Retrieval only'}
            </Badge>
          }
        />

        {locked ? (
          <p className="flex gap-2.5 rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-secondary">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              This server sets the provider through environment variables, so it is the same for
              everyone and cannot be changed here. Clear <code className="font-mono">LLM_PROVIDER</code>{' '}
              on the server to manage it from this page instead.
            </span>
          </p>
        ) : null}

        {!locked && !current.encryptionAvailable ? (
          <p className="flex gap-2.5 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2.5 text-sm text-ink">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              This server cannot encrypt stored credentials, so a key saved here would sit in the
              database as you typed it. Install the cryptography package, or set the key through an
              environment variable instead.
            </span>
          </p>
        ) : null}

        <fieldset disabled={locked} className="mt-3.5 space-y-4 disabled:opacity-60">
          {/* A segmented control is a group of buttons rather than one input,
              so the group carries the name and the label is not pointed at a
              single element. */}
          <Field label="Provider" hint="Pick none to stay on retrieval only.">
            <SegmentedControl
              aria-label="Provider"
              size="sm"
              className="w-full"
              options={[
                { value: 'none', label: 'None' },
                ...RECIPES.map((entry) => ({ value: entry.value, label: entry.label })),
              ]}
              value={provider}
              onChange={(next) => {
                setProvider(next as Provider);
                setModel('');
              }}
            />
          </Field>

          {recipe ? (
            <>
              <p className="text-sm text-ink-secondary">{recipe.blurb}</p>
              <p className="text-sm text-ink-secondary">
                Paste your key and save. Everything below it is optional.
              </p>

              <Field
                label="API key"
                htmlFor="ai-key"
                hint={
                  current.hasKey
                    ? 'A key is stored. Leave this empty to keep it, or type a new one to replace it.'
                    : recipe.keyHint
                }
              >
                <Input
                  id="ai-key"
                  type="password"
                  value={apiKey}
                  autoComplete="off"
                  placeholder={current.hasKey ? 'Stored, hidden' : 'Paste your key'}
                  onChange={(event) => setApiKey(event.target.value)}
                />
              </Field>

              {recipe.keyUrl ? (
                <p className="text-xs text-ink-muted">
                  Keys come from{' '}
                  <a
                    href={recipe.keyUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="font-medium text-accent-text hover:underline"
                  >
                    {new URL(recipe.keyUrl).hostname}
                  </a>
                  . It is encrypted on the server and never sent back to this page.
                </p>
              ) : null}

              <Field
                label="Model"
                htmlFor="ai-model"
                hint={
                  model
                    ? 'Leave this empty to go back to the default.'
                    : `Optional. Without one this uses ${current.defaultModel || recipe.models[0]}, which is the cheap fast model most support answers want.`
                }
              >
                <Input
                  id="ai-model"
                  value={model}
                  list="ai-model-options"
                  onChange={(event) => setModel(event.target.value)}
                  placeholder={current.defaultModel || recipe.models[0]}
                />
                <datalist id="ai-model-options">
                  {recipe.models.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              </Field>

              {provider === 'openai' ? (
                <Field
                  label="Base URL"
                  htmlFor="ai-base"
                  hint="Leave empty for OpenAI itself. Set it to reach anything that speaks the same protocol."
                >
                  <div className="flex gap-2">
                    <Input
                      id="ai-base"
                      value={baseUrl}
                      onChange={(event) => setBaseUrl(event.target.value)}
                      placeholder="https://api.openai.com/v1"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => setBaseUrl(LOCAL_BASE_URL)}
                    >
                      Use local Ollama
                    </Button>
                  </div>
                </Field>
              ) : null}

              <Field
                label="Embedding model"
                htmlFor="ai-embed"
                hint="Optional. Adds meaning based search next to the keyword search. Vectors are cached on the article, so there is still no vector database."
              >
                <Input
                  id="ai-embed"
                  value={embeddingModel}
                  onChange={(event) => setEmbeddingModel(event.target.value)}
                  placeholder="text-embedding-3-small"
                />
              </Field>
            </>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={save} disabled={saving} icon={<Check className="h-4 w-4" />}>
              {saving ? 'Saving' : 'Save'}
            </Button>
            {current.active ? (
              <Button variant="secondary" onClick={test} disabled={testing} icon={<Zap className="h-4 w-4" />}>
                {testing ? 'Testing' : 'Send a test question'}
              </Button>
            ) : null}
          </div>

          {result ? (
            <p
              className={
                result.ok
                  ? 'rounded-lg border border-success/40 bg-success-soft px-3 py-2.5 text-sm text-ink'
                  : 'rounded-lg border border-danger/40 bg-danger-soft px-3 py-2.5 text-sm text-ink'
              }
            >
              {result.detail}
            </p>
          ) : null}
        </fieldset>
      </Card>

      <Card>
        <CardHeader
          title="What changes when a model is connected"
          description="Everything below already works without one."
          action={<Sparkles className="h-4 w-4 text-ink-muted" />}
        />
        <dl className="space-y-2.5 text-sm">
          {[
            ['Replies', 'Written in your brand voice instead of quoted from the article.'],
            ['Tap AI', 'Coaching lines during a call instead of the matching passage.'],
            ['Drafting', 'Agents get a suggested reply they can edit before sending.'],
            ['Grounding', 'Unchanged. Answers still come from your articles and still cite them.'],
          ].map(([term, detail]) => (
            <div key={term} className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="w-28 shrink-0 font-medium text-ink">{term}</dt>
              <dd className="flex-1 text-ink-secondary">{detail}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

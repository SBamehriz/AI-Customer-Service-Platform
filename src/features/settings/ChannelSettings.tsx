import * as React from 'react';
import { Check, Copy, ExternalLink, ListChecks, Lock, Webhook } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  Modal,
  Skeleton,
  useToast,
} from '@/components/ui';
import { ChannelIcon } from '@/features/inbox/ChannelIcon';
import { useApi } from '@/app/session';
import { useAsync } from '@/hooks';
import { relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ChannelCatalogEntry, ChannelConnection } from '@/lib/types';

/** Human labels and setup notes for each credential a provider needs. */
const KEY_HELP: Record<string, { label: string; hint?: string; secret?: boolean }> = {
  app_secret: { label: 'App secret', hint: 'Signs every webhook delivery.', secret: true },
  verify_token: { label: 'Verify token', hint: 'Any string you like, pasted into the provider as well.' },
  access_token: { label: 'Access token', secret: true },
  phone_number_id: { label: 'Phone number ID' },
  page_id: { label: 'Page ID' },
  account_sid: { label: 'Account SID' },
  auth_token: { label: 'Auth token', secret: true },
  from_number: { label: 'From number', hint: 'In E.164 format, e.g. +15550100.' },
  smtp_host: { label: 'SMTP host' },
  smtp_port: { label: 'SMTP port', hint: '587 for STARTTLS, 465 for implicit TLS.' },
  smtp_user: { label: 'SMTP username' },
  smtp_password: { label: 'SMTP password', secret: true },
  from_address: { label: 'From address' },
  imap_host: { label: 'IMAP host', hint: 'Optional, turns on polling a shared mailbox.' },
  imap_user: { label: 'IMAP username' },
  imap_password: { label: 'IMAP password', secret: true },
  webhook_secret: { label: 'Inbound webhook secret', secret: true },
};

/** Who you go to for each channel, named so nobody has to guess. */
const PROVIDER_NAME: Record<string, string> = {
  email: 'your mail host',
  whatsapp: 'Meta',
  instagram: 'Meta',
  sms: 'Twilio',
  voice: 'Twilio',
};

const PROVIDER_DOCS: Record<string, string> = {
  whatsapp: 'https://developers.facebook.com/docs/whatsapp/cloud-api/get-started',
  instagram: 'https://developers.facebook.com/docs/messenger-platform/instagram',
  sms: 'https://www.twilio.com/docs/messaging/quickstart',
  voice: 'https://www.twilio.com/docs/voice',
};

/** The steps at the provider, in order. */
const SETUP_STEPS: Record<string, string[] | undefined> = {
  voice: [
    'Buy a number in the Twilio console, under Phone Numbers, Manage, Buy a number. Tick Voice.',
    'Open that number and find Voice Configuration.',
    'Set A call comes in to Webhook, paste the URL below, and set the method to HTTP POST.',
    'Save. Twilio signs every request, and the platform rejects anything whose signature does not match your auth token.',
    'Your PUBLIC_URL has to be the address Twilio actually calls, because the signature is checked against it. Behind a tunnel or a proxy, set it to the public address.',
    'Call the number. The transcript appears under Tap AI while the call is live.',
  ],
  sms: [
    'Buy a number in the Twilio console, under Phone Numbers, Manage, Buy a number. Tick SMS.',
    'Open that number and find Messaging Configuration.',
    'Set A message comes in to Webhook, paste the URL below, and set the method to HTTP POST.',
    'Copy the Account SID and Auth Token from the console home page into the fields below.',
    'Save, then text the number. It lands in the inbox like any other channel.',
  ],
  whatsapp: [
    'Create an app at developers.facebook.com and add the WhatsApp product.',
    'Under WhatsApp, Configuration, set the callback URL to the one below and pick any verify token, then put that same token in the field below.',
    'Subscribe the app to the messages field, or nothing will be delivered.',
    'Copy the app secret, the permanent access token and the phone number id into the fields below.',
  ],
  instagram: [
    'Use the same Meta app, and connect the Instagram account to a Facebook page.',
    'Under Messenger, Instagram settings, set the callback URL to the one below with your verify token.',
    'Subscribe to the messages field.',
    'Copy the app secret, the page access token and the page id into the fields below.',
  ],
  email: [
    'Point the SMTP fields at your mail host. Most providers give you a host, a port and an app password.',
    'To receive mail, either fill in the IMAP fields and the platform polls the mailbox, or have your provider POST to the webhook URL below.',
    'If you use the webhook, set a shared secret so the endpoint is not open to anyone who finds the URL.',
  ],
};

const OPTIONAL_KEYS: Record<string, string[]> = {
  email: ['smtp_user', 'smtp_password', 'imap_host', 'imap_user', 'imap_password', 'webhook_secret'],
};

export function ChannelSettings() {
  const api = useApi();
  const toast = useToast();
  const channels = useAsync(() => api.listChannels(), [api]);
  const catalog = useAsync(() => api.channelCatalog(), [api]);
  const [editing, setEditing] = React.useState<ChannelConnection | null>(null);

  if (channels.loading || catalog.loading) return <Skeleton className="h-96" />;

  const entries = catalog.data ?? [];
  const connections = channels.data ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Connected channels"
          description="Everything here lands in the same inbox, on the same conversation and ticket records."
        />
        <ul className="space-y-2">
          {connections.map((connection) => {
            const entry = entries.find((item) => item.channel === connection.channel);
            const ready = connection.missingKeys.length === 0;
            return (
              <li
                key={connection.channel}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-3.5 py-3"
              >
                <span
                  className={cn(
                    'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                    connection.isActive ? 'bg-success-soft text-success' : 'bg-sunken text-ink-muted',
                  )}
                >
                  <ChannelIcon channel={connection.channel} className="h-[18px] w-[18px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-base font-medium text-ink">
                    {connection.displayName}
                    {connection.isActive ? (
                      <Badge tone="success" dot>
                        Active
                      </Badge>
                    ) : ready ? (
                      <Badge tone="warning">Ready, not enabled</Badge>
                    ) : (
                      <Badge tone="neutral">Not connected</Badge>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-ink-muted">
                    {entry?.requiredKeys.length === 0
                      ? 'Built in, no credentials needed.'
                      : connection.missingKeys.length
                        ? `Needs ${connection.missingKeys.map((key) => KEY_HELP[key]?.label ?? key).join(', ')}`
                        : connection.lastEventAt
                          ? `Last message ${relativeTime(connection.lastEventAt)}`
                          : 'Credentials saved.'}
                  </p>
                </div>
                {entry && entry.requiredKeys.length > 0 ? (
                  <Button variant="secondary" size="sm" onClick={() => setEditing(connection)}>
                    {ready ? 'Manage' : 'Connect'}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <CardHeader
          title="Embed the web widget"
          description="One script tag puts a chat box on any page. Messages land in the same inbox."
        />
        <EmbedSnippet />
      </Card>

      {editing ? (
        <ChannelModal
          connection={editing}
          entry={entries.find((item) => item.channel === editing.channel)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            channels.reload();
            toast.success('Channel updated');
          }}
        />
      ) : null}
    </div>
  );
}

function ChannelModal({
  connection,
  entry,
  onClose,
  onSaved,
}: {
  connection: ChannelConnection;
  entry: ChannelCatalogEntry | undefined;
  onClose: () => void;
  onSaved: () => void;
}) {
  const api = useApi();
  const toast = useToast();
  const [config, setConfig] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  const keys = [...(entry?.requiredKeys ?? []), ...(OPTIONAL_KEYS[connection.channel] ?? [])];

  const save = async (activate: boolean) => {
    setSaving(true);
    try {
      await api.saveChannel(connection.channel, { isActive: activate, config });
      onSaved();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save the channel');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Connect ${connection.displayName}`}
      description="Credentials are stored on the server and never returned by the API. You only ever see the names of the keys you have set."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="secondary" onClick={() => save(false)} loading={saving}>
            Save only
          </Button>
          <Button variant="primary" onClick={() => save(true)} loading={saving}>
            Save and activate
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {SETUP_STEPS[connection.channel] ? (
          <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
            <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
              <ListChecks className="h-3 w-3" />
              What to do at {PROVIDER_NAME[connection.channel] ?? 'the provider'}
            </p>
            <ol className="ml-4 list-decimal space-y-1 text-xs leading-relaxed text-ink-secondary">
              {SETUP_STEPS[connection.channel]!.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            {PROVIDER_DOCS[connection.channel] ? (
              <a
                href={PROVIDER_DOCS[connection.channel]}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-2 inline-block text-xs font-medium text-accent-text hover:underline"
              >
                Open the {PROVIDER_NAME[connection.channel]} docs
              </a>
            ) : null}
          </div>
        ) : null}

        {connection.webhookUrl ? (
          <div className="rounded-lg border border-line bg-sunken px-3 py-2.5">
            <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
              <Webhook className="h-3 w-3" />
              Webhook URL
            </p>
            <CopyRow value={connection.webhookUrl} />
            <p className="mt-1.5 text-xs text-ink-muted">
              Paste this into the dashboard of the provider. Deliveries are rejected unless the
              signature matches the secret below.
            </p>
          </div>
        ) : null}

        {keys.map((key) => {
          const help = KEY_HELP[key] ?? { label: key };
          const configured = connection.configuredKeys.includes(key);
          const optional = (OPTIONAL_KEYS[connection.channel] ?? []).includes(key);
          return (
            <Field
              key={key}
              label={`${help.label}${optional ? ' (optional)' : ''}`}
              htmlFor={`channel-${key}`}
              hint={
                configured
                  ? `Already set, leave this blank to keep it. ${help.hint ?? ''}`.trim()
                  : help.hint
              }
            >
              <Input
                id={`channel-${key}`}
                type={help.secret ? 'password' : 'text'}
                value={config[key] ?? ''}
                onChange={(event) => setConfig({ ...config, [key]: event.target.value })}
                placeholder={configured ? '••••••••' : ''}
                leading={help.secret ? <Lock className="h-3.5 w-3.5" /> : undefined}
                autoComplete="off"
              />
            </Field>
          );
        })}
      </div>
    </Modal>
  );
}

function EmbedSnippet() {
  const api = useApi();
  const workspace = useAsync(() => api.getWorkspace(), [api]);
  const publicKey = workspace.data?.publicKey ?? 'pk_your_key';
  const snippet = `<script
  src="https://your-domain.example/widget.js"
  data-key="${publicKey}"
  data-api="https://your-domain.example"
  defer
></script>`;

  return (
    <div className="space-y-2.5">
      <pre className="scroll-slim overflow-x-auto rounded-lg border border-line bg-sunken px-3.5 py-3 font-mono text-xs leading-relaxed text-ink">
        {snippet}
      </pre>
      <div className="flex flex-wrap items-center gap-2">
        <CopyButton value={snippet} label="Copy snippet" />
        <a href="/portal" target="_blank" rel="noreferrer">
          <Button variant="ghost" size="sm" icon={<ExternalLink className="h-3.5 w-3.5" />}>
            Preview the customer view
          </Button>
        </a>
      </div>
    </div>
  );
}

function CopyRow({ value }: { value: string }) {
  return (
    <div className="flex items-center gap-2">
      <code className="scroll-slim min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded bg-surface px-2 py-1 font-mono text-xs text-ink">
        {value}
      </code>
      <CopyButton value={value} />
    </div>
  );
}

function CopyButton({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <Button
      variant="secondary"
      size="sm"
      icon={copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {
          // Clipboard permission denied. The value is selectable on screen.
        }
      }}
    >
      {label ?? (copied ? 'Copied' : 'Copy')}
    </Button>
  );
}

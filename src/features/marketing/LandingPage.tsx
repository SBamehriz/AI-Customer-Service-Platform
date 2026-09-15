import * as React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  Check,
  Database,
  Code,
  Inbox,
  Camera,
  Mail,
  MessageSquare,
  PhoneCall,
  Plug,
  Radio,
  Shield,
  Sparkles,
  Ticket,
} from '@/components/icons';
import { LogoMark, Wordmark } from '@/components/brand/Logo';
import { ThemeToggle } from '@/components/layout';
import { Badge, Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import { REPO_URL } from '@/lib/config';
import { InboxPreview } from './InboxPreview';

const CHANNELS = [
  { icon: MessageSquare, label: 'Web chat & widget' },
  { icon: Mail, label: 'Email' },
  { icon: Radio, label: 'WhatsApp' },
  { icon: Camera, label: 'Instagram' },
  { icon: MessageSquare, label: 'SMS' },
  { icon: PhoneCall, label: 'Voice' },
];

const FEATURES = [
  {
    icon: Inbox,
    title: 'One inbox, every channel',
    body: 'Web widget, email, WhatsApp, Instagram, SMS and voice all normalise into the same conversation, ticket and customer record. An agent learns one screen, not six.',
  },
  {
    icon: Sparkles,
    title: 'AI that cites its sources',
    body: 'Replies are drafted only from your knowledge base, with the passages they came from attached. When retrieval comes up short, the thread goes to a human instead of improvising.',
  },
  {
    icon: PhoneCall,
    title: 'Tap AI on live calls',
    body: 'Tap listens to a call as it happens and whispers the next move to the agent. The exact policy line, the risk to avoid, the question to ask. It never speaks to the customer.',
  },
  {
    icon: Ticket,
    title: 'Ticketing that keeps up',
    body: 'Every conversation opens a ticket with SLA clocks, routing rules, priorities and a full customer history, deduplicated across channels by email and phone.',
  },
  {
    icon: Database,
    title: 'SQLite by default',
    body: 'No Postgres, no Redis, no vector database. Clone it, run two commands, and you have a working platform. Point DATABASE_URL at PostgreSQL when you outgrow a single file.',
  },
  {
    icon: Plug,
    title: 'Bring your own model',
    body: 'OpenAI, Anthropic, Gemini, or anything that speaks the OpenAI protocol, including Ollama and vLLM. With no key at all it still answers from retrieval alone.',
  },
];

const STATUS_ROWS: { area: string; state: 'Implemented' | 'Needs credentials' | 'Prototype'; note: string }[] = [
  { area: 'Unified inbox, tickets, customers, knowledge base', state: 'Implemented', note: 'Full CRUD, covered by the test suite' },
  { area: 'Web chat, embeddable widget, hosted portal', state: 'Implemented', note: 'No third party involved' },
  { area: 'Grounded AI drafting and retrieval', state: 'Implemented', note: 'BM25 retrieval, embeddings optional' },
  { area: 'Tap AI live call assist', state: 'Implemented', note: 'Browser speech or telephony transcript' },
  { area: 'WhatsApp, Instagram, SMS, voice, email', state: 'Needs credentials', note: 'Adapters and webhooks are built, add provider keys to run one' },
  { area: 'Analytics and SLA reporting', state: 'Implemented', note: 'Computed live from ticket rows' },
  { area: 'Multi-node realtime', state: 'Prototype', note: 'In process pub sub, sized for one API node' },
];

/** The page everyone lands on first. */
export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-bg">
      <SiteHeader />
      <Hero />
      <ChannelStrip />
      <HowToUse />
      <FeatureGrid />
      <TapSection />
      <DataSection />
      <StatusSection />
      <SiteFooter />
    </div>
  );
}

function SiteHeader() {
  return (
    <header className="veil sticky top-0 z-40 border-b border-line">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Wordmark />
        <nav className="flex items-center gap-1">
          <a href="#how-to-use" className="hidden sm:inline-flex">
            <Button variant="ghost" size="sm">
              How to use it
            </Button>
          </a>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hidden sm:inline-flex">
            <Button variant="ghost" size="sm" icon={<Code className="h-4 w-4" />}>
              Source
            </Button>
          </a>
          {/* Readable at night without signing in first. */}
          <ThemeToggle />
          <Link to="/login">
            <Button variant="primary" size="sm">
              Open the workspace
            </Button>
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line">
      <div className="dot-grid absolute inset-0 opacity-60" aria-hidden="true" />
      <div
        className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-accent-soft to-transparent opacity-70"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pb-20 sm:pt-24">
        <div className="mx-auto max-w-3xl text-center">
          <Badge tone="accent" className="mb-5">
            Free to use, source available
          </Badge>
          <h1 className="text-4xl font-semibold text-ink sm:text-5xl lg:text-6xl">
            Every customer conversation,
            <br className="hidden sm:block" /> in one place.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-ink-secondary">
            A unified customer service platform for small and medium businesses. Web chat, email,
            WhatsApp, Instagram, SMS and phone calls land in a single inbox, with AI that drafts
            from your own knowledge base and hands over the moment it is out of its depth.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <a href="#how-to-use">
              <Button variant="primary" size="lg" icon={<ArrowRight className="h-4 w-4" />}>
                How to use it
              </Button>
            </a>
            <Link to="/login">
              <Button variant="secondary" size="lg">
                Look around the demo
              </Button>
            </Link>
          </div>
          <p className="mt-3 text-sm text-ink-muted">
            Free for any business to run, on your own machine or your own server, and the
            data stays there.
          </p>
        </div>

        <div className="mx-auto mt-14 max-w-5xl">
          <InboxPreview />
        </div>
      </div>
    </section>
  );
}

function ChannelStrip() {
  return (
    <section className="border-b border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <p className="mb-5 text-center text-xs font-medium uppercase tracking-wider text-ink-muted">
          One conversation model across
        </p>
        <ul className="flex flex-wrap items-center justify-center gap-2.5">
          {CHANNELS.map(({ icon: Icon, label }) => (
            <li
              key={label}
              className="inline-flex items-center gap-2 rounded-full border border-line bg-bg px-3.5 py-1.5 text-sm text-ink-secondary"
            >
              <Icon className="h-3.5 w-3.5 text-ink-muted" />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function FeatureGrid() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold text-ink">Built for a team of five, not five hundred</h2>
          <p className="mt-3 text-md text-ink-secondary">
            Enterprise helpdesks assume a dedicated admin. This one assumes whoever answers the
            phone is also the person who set it up.
          </p>
        </div>
        <div className="mt-10 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <article key={title} className="bg-surface p-6">
              <div className="mb-3.5 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
                <Icon className="h-[18px] w-[18px]" />
              </div>
              <h3 className="text-md font-semibold text-ink">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-secondary">{body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function TapSection() {
  return (
    <section className="border-b border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-2 lg:items-center">
        <div>
          <Badge tone="info" className="mb-4">
            Tap AI
          </Badge>
          <h2 className="text-3xl font-semibold text-ink">
            The answer, while the caller is still talking
          </h2>
          <p className="mt-4 text-md leading-relaxed text-ink-secondary">
            Phone support is where knowledge bases fail, because nobody can search while holding a
            conversation. Tap reads the live transcript, retrieves the passage that applies, and
            puts it in front of the agent, with the policy risk called out before it gets promised
            away.
          </p>
          <ul className="mt-6 space-y-3">
            {[
              'Transcript from the browser speech recognition, or from your telephony provider',
              'Suggestions tagged as answer, action, warning or question',
              'Every suggestion carries the article it came from',
              'A written call summary when the call ends',
            ].map((item) => (
              <li key={item} className="flex gap-2.5 text-sm text-ink-secondary">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-line bg-bg p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-xs text-ink-muted">
            <span className="animate-pulse-ring h-2 w-2 rounded-full bg-danger" />
            Live call · 04:12
          </div>
          <div className="space-y-2.5">
            <TranscriptLine speaker="Caller">
              Last time we ordered down bags they arrived jammed into tiny stuff sacks and two of
              them never fully lofted again.
            </TranscriptLine>
            <SuggestionCard kind="warning" source="Caring for technical fabrics">
              Down stored compressed loses loft permanently and that is not covered by the
              warranty. Say so now, not after.
            </SuggestionCard>
            <SuggestionCard kind="answer" source="Caring for technical fabrics">
              Down bags should ship and store uncompressed in a large cotton sack.
            </SuggestionCard>
          </div>
        </div>
      </div>
    </section>
  );
}

function TranscriptLine({ speaker, children }: { speaker: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
      <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-muted">{speaker}</p>
      <p className="text-sm text-ink">{children}</p>
    </div>
  );
}

function SuggestionCard({
  kind,
  source,
  children,
}: {
  kind: 'warning' | 'answer';
  source: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border-l-2 bg-surface px-3 py-2.5 shadow-xs',
        kind === 'warning' ? 'border-l-warning' : 'border-l-accent',
      )}
    >
      <p
        className={cn(
          'mb-1 text-2xs font-semibold uppercase tracking-wide',
          kind === 'warning' ? 'text-warning' : 'text-accent-text',
        )}
      >
        {kind}
      </p>
      <p className="text-sm text-ink">{children}</p>
      <p className="mt-1.5 inline-flex items-center gap-1 text-2xs text-ink-muted">
        <BookOpen className="h-3 w-3" />
        {source}
      </p>
    </div>
  );
}

function StatusSection() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="mb-8 flex items-start gap-3">
          <Shield className="mt-1 h-5 w-5 shrink-0 text-ink-muted" />
          <div>
            <h2 className="text-2xl font-semibold text-ink">What actually works today</h2>
            <p className="mt-2 text-md text-ink-secondary">
              This is a real working platform, not a mockup. It is also not a product with a
              support contract. Here is the honest state of each part.
            </p>
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Area</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle bg-surface">
              {STATUS_ROWS.map((row) => (
                <tr key={row.area}>
                  <td className="px-4 py-3 text-ink">{row.area}</td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={
                        row.state === 'Implemented'
                          ? 'success'
                          : row.state === 'Needs credentials'
                            ? 'warning'
                            : 'neutral'
                      }
                    >
                      {row.state}
                    </Badge>
                  </td>
                  <td className="hidden px-4 py-3 text-ink-muted sm:table-cell">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

interface Step {
  title: string;
  body: string;
  code?: string;
  note?: string;
}

const STEPS: Step[] = [
  {
    title: 'Start it',
    body: 'Two commands. Python 3.11 and Node 20 are the only things you need installed. No database server, no cache, no vector store.',
    code: 'cd backend\npip install -r requirements.txt\nuvicorn app.main:app\n\nnpm install && npm run dev',
    note: 'Then open localhost:3000. Add SEED_DEMO_DATA=true to the first command if you would rather look at a workspace with sample data in it.',
  },
  {
    title: 'Create your workspace',
    body: 'The first person to sign up becomes the owner. Name the workspace after your business, pick an accent colour, and write the greeting customers see.',
    note: 'Everything after this happens in Settings. You never have to edit a config file to run the platform.',
  },
  {
    title: 'Add your team',
    body: 'Settings, Team. Agents answer customers and draft knowledge articles. Supervisors publish those articles and configure the workspace. Owners also manage the team and the keys.',
    note: 'There is no mail server in the box, so you set each person a first password and hand it over. They can change it later.',
  },
  {
    title: 'Write what you know',
    body: 'Settings aside, the knowledge base is the part that matters most. Every answer the assistant gives is quoted from it and cites which article it came from, so nothing is invented.',
    note: 'Start with the five questions you answer most. That is usually enough to be useful on day one.',
  },
  {
    title: 'Connect a model, or do not',
    body: 'Settings, AI. Paste a key from OpenAI, Anthropic or Gemini, or point it at a local Ollama so nothing leaves your network. There is a button that sends a test question so you know it works.',
    note: 'Optional. Without a key the platform still finds the right article and quotes it, it just does not rewrite it in your voice.',
  },
  {
    title: 'Connect your channels',
    body: 'Settings, Channels. Each one shows the steps to follow at the provider and the webhook address to paste in. Twilio for phone numbers and SMS, Meta for WhatsApp and Instagram, any SMTP host for email.',
    note: 'Web chat needs nothing at all. Drop one script tag on your site and messages start arriving.',
  },
];

function HowToUse() {
  return (
    <section id="how-to-use" className="scroll-mt-16 border-b border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold text-ink">How to use it</h2>
          <p className="mt-3 text-lg text-ink-secondary">
            Start to finish, roughly twenty minutes. Nothing here needs a credit card and nothing
            phones home.
          </p>
        </div>

        <ol className="mt-10 grid gap-6 lg:grid-cols-2">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-text">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-semibold text-ink">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-secondary">{step.body}</p>
                {step.code ? (
                  <pre className="mt-3 whitespace-pre-wrap break-words rounded-lg border border-line bg-sunken px-3.5 py-3 font-mono text-xs leading-relaxed text-ink">
                    {step.code}
                  </pre>
                ) : null}
                {step.note ? (
                  <p className="mt-2 text-xs leading-relaxed text-ink-muted">{step.note}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-10 flex flex-wrap items-center gap-3">
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            <Button variant="primary" icon={<Code className="h-4 w-4" />}>
              Get the code
            </Button>
          </a>
          <Link to="/setup">
            <Button variant="secondary" icon={<BookOpen className="h-4 w-4" />}>
              Full setup guide
            </Button>
          </Link>
          <Link to="/portal">
            <Button variant="ghost">See the customer side</Button>
          </Link>
        </div>
      </div>
    </section>
  );
}

const DATA_POINTS = [
  {
    icon: Database,
    title: 'One file you can copy',
    body: 'Everything lives in a single SQLite database. Backing up is copying a file, and the platform takes timed snapshots for you and keeps the recent ones.',
  },
  {
    icon: Shield,
    title: 'Keys are encrypted',
    body: 'Provider keys and channel credentials are encrypted before they are written, so a copy of the database, or a backup that goes astray, does not hand them over.',
  },
  {
    icon: ArrowRight,
    title: 'Leaving is easy',
    body: 'Export the whole workspace as plain JSON whenever you like. Customers, conversations, tickets and articles, in a shape anything can read, with no secrets inside.',
  },
];

function DataSection() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold text-ink">Your data stays yours</h2>
          <p className="mt-3 text-lg text-ink-secondary">
            There is no account and no service behind this. The data sits on your disk, and you can
            take it out again at any point.
          </p>
        </div>
        <div className="mt-10 grid gap-6 sm:grid-cols-3">
          {DATA_POINTS.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-5">
              <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <h3 className="text-base font-semibold text-ink">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-secondary">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SiteFooter() {
  return (
    <footer className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <LogoMark size={22} className="text-ink-muted" />
          <p className="text-sm text-ink-muted">
            Unified Customer Service Platform, free to use, not to resell
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-ink-muted">
          <a href="#how-to-use" className="transition-colors hover:text-ink">
            How to use it
          </a>
          <Link to="/setup" className="transition-colors hover:text-ink">
            Setup guide
          </Link>

          <Link to="/portal" className="transition-colors hover:text-ink">
            Customer portal
          </Link>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="transition-colors hover:text-ink"
          >
            GitHub
          </a>
          <ThemeToggle side="top" />
        </div>
      </div>
    </footer>
  );
}

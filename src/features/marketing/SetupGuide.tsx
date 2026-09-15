import { Link } from 'react-router-dom';
import { ArrowLeft, Code } from '@/components/icons';
import { LogoMark, Wordmark } from '@/components/brand/Logo';
import { Button } from '@/components/ui';
import { ThemeToggle } from '@/components/layout';
import { REPO_URL } from '@/lib/config';

interface Section {
  id: string;
  title: string;
  intro: string;
  steps?: string[];
  code?: string;
  note?: string;
}

/** Everything somebody needs to go from nothing to a working support desk. */
const SECTIONS: Section[] = [
  {
    id: 'install',
    title: 'Install and start it',
    intro:
      'Python 3.11 and Node 20 are the only things you need. No database server, no cache, no vector store. The database is a single file the backend creates for you.',
    code: [
      'git clone ' + '<repository>',
      'cd <folder>',
      '',
      '# Backend, on port 8000',
      'cd backend',
      'pip install -r requirements.txt',
      'uvicorn app.main:app',
      '',
      '# Frontend, on port 3000, in a second terminal',
      'npm install',
      'npm run dev',
    ].join('\n'),
    note: 'Open localhost:3000. The dev server passes API calls through to the backend, so there is nothing to configure and no CORS to fight.',
  },
  {
    id: 'production',
    title: 'Run it for real',
    intro:
      'The backend serves the built frontend, so production is one process on one port. Set SECRET_KEY to something stable first, because it signs sessions and encrypts the credentials you store.',
    code: [
      'npm install && npm run build',
      'cd backend && pip install -r requirements.txt',
      'SECRET_KEY="$(openssl rand -hex 32)" uvicorn app.main:app --host 0.0.0.0 --port 8000',
      '',
      '# Or with Docker',
      'cp .env.example .env      # set SECRET_KEY',
      'docker compose up --build',
    ].join('\n'),
    note: 'Behind a reverse proxy, set PUBLIC_URL to the address the outside world uses and FORWARDED_ALLOW_IPS to your proxy, or provider webhooks will be rejected and every visitor will look like one address.',
  },
  {
    id: 'workspace',
    title: 'Create your company',
    intro:
      'The first person to sign up becomes the owner. Name the workspace after your business, pick an accent colour and write the greeting customers see.',
    steps: [
      'Open the app and choose Create the first workspace.',
      'Fill in your company name, your name, your email and a password.',
      'You are now the owner, and everything else happens in Settings.',
    ],
    note: 'If you started with SEED_DEMO_DATA=true to look around, Settings, Data, Clear this workspace removes the sample company and leaves you with an empty one. It takes a snapshot first, so it is undoable.',
  },
  {
    id: 'team',
    title: 'Add your team',
    intro:
      'Settings, Team. Three roles, and the server enforces them rather than the interface just hiding buttons.',
    steps: [
      'Agent answers customers, opens tickets and writes knowledge drafts.',
      'Supervisor also publishes articles, deletes tickets and configures channels, SLA and routing.',
      'Owner also manages the team and issues API keys.',
      'There is no mail server in the box, so you set each person a first password and hand it over. They can change it later.',
    ],
  },
  {
    id: 'knowledge',
    title: 'Write what you know',
    intro:
      'This is the part that matters most. Every answer the assistant gives is quoted from your articles and cites which one it came from, so nothing is invented.',
    steps: [
      'Knowledge, New article. Start with the five questions you answer most.',
      'Publish them. Only published articles are searched.',
      'Mark an article internal if it is guidance for agents rather than something a customer should be told.',
    ],
    note: 'Five good articles is enough to be useful on day one. The assistant will say it does not know rather than guess, so a small base is safe.',
  },
  {
    id: 'model',
    title: 'Connect a language model',
    intro:
      'Optional. Without one the platform still finds the right article and quotes it. With one, it writes the answer in your voice instead.',
    steps: [
      'Settings, AI. Pick your provider and paste the key. That is the only required field.',
      'The model name is optional. Left empty it uses a sensible default for that provider.',
      'Press Send a test question. A wrong key otherwise shows up days later as answers that quietly fell back to quoting.',
      'For a local model, pick OpenAI and set the base URL to http://localhost:11434/v1 for Ollama. Nothing leaves your network.',
    ],
    note: 'The key is encrypted before it is stored, and it is never sent back to the browser. If you would rather it never touched the database, set LLM_PROVIDER and LLM_API_KEY in the environment instead and this page becomes read only.',
  },
  {
    id: 'widget',
    title: 'Put the chat box on your website',
    intro:
      'One script tag, on any site. It works on WordPress, Shopify, Webflow, Squarespace, a React app, plain HTML, anything that lets you add a script.',
    code: [
      '<script',
      '  src="https://your-domain.example/widget.js"',
      '  data-key="pk_your_workspace_public_key"',
      '  defer',
      '></script>',
    ].join('\n'),
    steps: [
      'Copy your public key from Settings, Developer.',
      'Paste the tag before the closing body tag of your site.',
      'That is it. Messages arrive in the inbox under Web chat straight away.',
    ],
    note: 'It renders inside a shadow root, so your styles and the widget cannot affect each other. It is about 13 kB and loads nothing else. Customers can attach photos and documents, and those appear in the conversation.',
  },
  {
    id: 'channels',
    title: 'Connect your other channels',
    intro:
      'Settings, Channels. Each one shows the steps to follow at the provider and the exact webhook address to paste in, so you should not need to leave the screen.',
    steps: [
      'Email, point the SMTP fields at your mail host. To receive, either fill in IMAP and it polls, or have your host post to the webhook.',
      'WhatsApp and Instagram, a Meta app with the app secret, a verify token you choose, a permanent access token and the phone number or page id.',
      'SMS and voice, Twilio, with the account SID, auth token and the number itself.',
      'Photos sent on WhatsApp, attachments on an email and pictures on an MMS are downloaded and shown in the conversation.',
    ],
    note: 'Two things account for most channels that do not work. PUBLIC_URL has to match what the provider actually calls, because signatures are checked against it. And a Twilio number bought for SMS only will not ring for voice.',
  },
  {
    id: 'calls',
    title: 'Take phone calls',
    intro:
      'Tap AI listens to a live call and puts the next line in front of the agent. It never speaks to the customer.',
    steps: [
      'Buy a Twilio number with the Voice capability.',
      'Set its A call comes in webhook to the address shown in Settings, Channels, Voice, method POST.',
      'Call the number. The transcript appears under Tap AI while the call is still going.',
      'Recording is off by default. Turning it on plays a notice to the caller first, and the audio is kept with the transcript.',
    ],
  },
  {
    id: 'autopilot',
    title: 'Let it work the queue',
    intro:
      'Autopilot goes back over conversations that are sitting waiting and answers the ones it can answer well. Useful overnight and at weekends.',
    steps: [
      'Settings, Automation. Run it once to see what it would do.',
      'Then set the hours it should run by itself. Overnight ranges like 22-6 work.',
      'It only answers what retrieval genuinely covers, never touches a conversation somebody has picked up, and never takes two turns without a reply in between.',
    ],
  },
  {
    id: 'data',
    title: 'Keep and export your data',
    intro:
      'Everything is one SQLite file, so a backup is a file copy and an export is plain text.',
    steps: [
      'Settings, Data. Snapshots are taken on a timer and the recent ones are kept on disk.',
      'Download the workspace as JSON at any time. It reads without this software, and carries no passwords or keys.',
      'Six CSV tables, customers, tickets, conversations, messages, agents and calls, for a spreadsheet or a warehouse.',
      'Back up SECRET_KEY separately from the database. Together they are the stored credentials, apart neither is enough.',
    ],
  },
];

export default function SetupGuide() {
  return (
    <div className="min-h-dvh bg-bg">
      <header className="veil sticky top-0 z-40 border-b border-line">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Wordmark />
          </Link>
          <div className="flex items-center gap-1">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hidden sm:inline-flex">
              <Button variant="ghost" size="sm" icon={<Code className="h-4 w-4" />}>
                Source
              </Button>
            </a>
            <ThemeToggle />
            <Link to="/">
              <Button variant="ghost" size="sm" icon={<ArrowLeft className="h-3.5 w-3.5" />}>
                Back
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-semibold text-ink">Setup guide</h1>
          <p className="mt-3 text-lg text-ink-secondary">
            From nothing to a working support desk. Each part stands on its own, so skip to the
            one you need.
          </p>
        </div>

        <nav aria-label="Sections" className="mt-8 flex flex-wrap gap-2">
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:border-accent-border hover:bg-accent-soft hover:text-accent-text"
            >
              {section.title}
            </a>
          ))}
        </nav>

        <div className="mt-12 space-y-12">
          {SECTIONS.map((section, index) => (
            <section key={section.id} id={section.id} className="scroll-mt-20">
              <div className="flex items-baseline gap-3">
                <span className="text-sm font-semibold text-ink-muted">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h2 className="text-2xl font-semibold text-ink">{section.title}</h2>
              </div>
              <p className="mt-2.5 max-w-3xl text-base leading-relaxed text-ink-secondary">
                {section.intro}
              </p>

              {section.steps ? (
                <ul className="mt-4 max-w-3xl space-y-2">
                  {section.steps.map((step) => (
                    <li key={step} className="flex gap-2.5 text-sm leading-relaxed text-ink">
                      <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-muted" />
                      <span>{step}</span>
                    </li>
                  ))}
                </ul>
              ) : null}

              {section.code ? (
                <pre className="scroll-slim mt-4 max-w-3xl overflow-x-auto rounded-lg border border-line bg-sunken px-4 py-3.5 font-mono text-xs leading-relaxed text-ink">
                  {section.code}
                </pre>
              ) : null}

              {section.note ? (
                <p className="mt-3 max-w-3xl rounded-lg bg-sunken px-3.5 py-2.5 text-sm leading-relaxed text-ink-secondary">
                  {section.note}
                </p>
              ) : null}
            </section>
          ))}
        </div>

        <footer className="mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-8">
          <div className="flex items-center gap-2.5">
            <LogoMark size={20} className="text-ink-muted" />
            <p className="text-sm text-ink-muted">Free to use, not to resell.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link to="/login">
              <Button variant="primary" size="sm">
                Open the workspace
              </Button>
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm" icon={<Code className="h-4 w-4" />}>
                Source
              </Button>
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}

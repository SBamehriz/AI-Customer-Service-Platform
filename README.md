# Unified Customer Service Platform

A free customer service platform for small and medium businesses. Web chat,
email, WhatsApp, Instagram, SMS and phone calls all arrive in one inbox, with
AI that drafts replies from your own help articles and hands over to a person
when it does not know the answer.

It runs on SQLite with no other services. Two commands and it works.

```bash
# one terminal
cd backend && pip install -r requirements.txt && SEED_DEMO_DATA=true uvicorn app.main:app

# another terminal
npm install && npm run dev
```

Open http://localhost:3000. The setup guide is at http://localhost:3000/setup.

`SEED_DEMO_DATA=true` fills the workspace with a sample outdoor retailer so
there is something to look at, and the sign in screen offers one click roles.
To sign in by hand use `dana@meridian.example` and `demo1234`.

Leave that variable out for a real install. It is off by default, so you get an
empty database and the sign in screen asks you to create the first workspace.
The demo accounts share a published password, so they do not belong anywhere
real.

![The unified inbox](docs/screenshots/inbox.png)

## What it does

**One inbox for every channel.** A web widget, email, WhatsApp, Instagram, SMS
and voice all become the same conversation, ticket and customer record.
Customers are matched across channels by email and phone, so the person who
messaged on WhatsApp last month is the same record when they email today.

**AI that shows its sources.** Replies are drafted only from your help
articles, and every answer carries the passages it came from. When retrieval
comes up short the thread goes to a person instead of guessing.

**Tap AI on live calls.** Tap listens to a call in progress and puts the next
move in front of the agent: the policy line, the risk to avoid, the question to
ask. It never speaks to the customer.

**Ticketing that keeps up.** SLA clocks, routing rules, priorities, saved
replies and a full history for each customer.

**Roles that mean something.** Help articles are the policy the assistant
quotes to customers, so agents write drafts and supervisors decide what goes
live. Deleting a ticket, changing SLA targets and connecting a channel are
supervisor work too. All of it is checked on the server, not just hidden in the
interface.

**An embeddable widget.** One script tag puts a chat box on any site. It is
13.7 kB, 4.5 kB gzipped, has no dependencies, and renders inside a shadow root
so it cannot clash with the page around it.

**Bring your own model.** OpenAI, Anthropic, Gemini, or anything that speaks
the OpenAI protocol, including Ollama and vLLM. Paste the key into Settings and
it is encrypted before it is stored, or set it in the environment if you would
rather it never reached the database. With no key at all it still answers from
retrieval.

**Your data stays yours.** One SQLite file with your uploaded files beside it,
copied on a timer, and a one click export of the whole workspace as plain JSON
that needs none of this code to read. Six CSV tables for a spreadsheet or a
warehouse. Leaving is as easy as arriving.

**Files, not just words.** A photo on WhatsApp, a PDF on an email, a picture on
an MMS, or something dragged into the web chat. They arrive as real files and
show up in the conversation.

**It can work the queue on its own.** Autopilot answers the waiting
conversations your articles genuinely cover, on a button or on a schedule you
set. It never touches one somebody has picked up, and never guesses.

### Help articles are the policy

Articles are what the assistant is allowed to say, so they are treated as
policy rather than content. Agents write drafts, supervisors publish, and a
published article is locked to supervisors because it is already being quoted
to customers.

![The knowledge base](docs/screenshots/knowledge.png)

### Tap AI, mid call

Suggestions arrive while the caller is still talking, each one tagged and
carrying the article it came from.

![Tap AI during a live call](docs/screenshots/tap-ai.png)

### The supervisor view

Every figure is worked out from the ticket rows when you ask for it, so there
is nothing to schedule and nothing to keep in sync.

![Operations dashboard](docs/screenshots/home.png)

Analytics goes a level deeper, with volume by channel, resolution trends and
how much of the load the AI absorbed.

![Analytics](docs/screenshots/analytics.png)

### Bring your own model

Paste a key from any provider, or point it at a local Ollama so nothing leaves
your network. It is encrypted before it is stored, and there is a button that
sends a test question so you find out now rather than later.

![Connecting a language model](docs/screenshots/settings-ai.png)

### Who can change what

Agents answer customers and write article drafts. Supervisors decide what the
assistant is allowed to repeat. The server enforces it, and the interface just
stops offering buttons that would be refused.

![Roles and team management](docs/screenshots/roles.png)

### Dark mode, and the customer side

Dark mode is the same components with the colour tokens repointed, not a second
stylesheet. The hosted portal runs the same code as the widget.

<p>
  <img src="docs/screenshots/tickets-dark.png" alt="Tickets in dark mode" width="60%">
  <img src="docs/screenshots/portal-mobile.png" alt="The customer portal on a phone" width="27%">
</p>

## Status

This is a working platform. It is not a product with a support contract. Here
is the honest state of each part.

| Area | Status | Notes |
|---|---|---|
| Unified inbox, tickets, customers, help articles | **Implemented** | Full CRUD, covered by the test suite |
| Web chat, embeddable widget, hosted portal | **Implemented** | No third party involved |
| Grounded AI drafting and retrieval | **Implemented** | BM25 retrieval, embeddings optional |
| Tap AI live call assist | **Implemented** | Browser speech recognition, or a telephony transcript webhook |
| Analytics and SLA reporting | **Implemented** | Worked out live from ticket rows. First response deadlines are enforced. Resolution targets and business hours are stored but not acted on yet |
| API keys for server to server calls | **Implemented** | Scoped to one workspace, shown once |
| Roles and team management | **Implemented** | Agent, supervisor, owner. Agents write article drafts, supervisors publish them |
| Bring your own model from Settings | **Implemented** | Key stored encrypted, with a button that sends a test question |
| Snapshots and JSON export | **Implemented** | Timed database copies, and the whole workspace as plain JSON. A reset archives the files it clears, so it can be undone |
| Files on every channel | **Implemented** | Photos and documents in, out, and shown in the conversation |
| CSV datasets for reporting | **Implemented** | Customers, tickets, conversations, messages, agents, calls |
| Autopilot | **Implemented** | Works the waiting queue on a button or on a schedule |
| Call recording | **Needs credentials** | Twilio. Off by default, and it plays a notice before it starts |
| WhatsApp, Instagram, SMS, voice, email | **Needs credentials** | Adapters, signature checks and webhooks are built. Add provider keys to run one |
| Realtime across several API nodes | **Prototype** | Publish and subscribe inside one process, sized for one node |
| Migrations | **Partial** | Tables are created, and a missing nullable column is added at startup. Anything beyond that wants a migration tool |

It is not production hardened. There is no audit log and no SSO. Read
[`docs/security.md`](docs/security.md) before you put it on the internet.

## Running it

There are two choices to make, and they are separate.

**How you run it.** Straight from source with Python and Node, or as one Docker
container. Same application either way.

**Where the data goes.** SQLite, which is a single file the app creates for
itself, or PostgreSQL, which is a database server you run separately. Same
schema either way, and the whole test suite runs against both.

Most people want source plus SQLite to try it, and Docker plus SQLite to keep
it. Reach for PostgreSQL when you outgrow one machine, and not before.

| | SQLite, the default | PostgreSQL |
|---|---|---|
| **From source** | Nothing to install. Good for trying it and for developing. | Set `DATABASE_URL`, `pip install asyncpg` |
| **Docker** | One container. Good for actually running it. | Point `DATABASE_URL` at your server |

### Requirements

Python 3.11 or newer, and Node 20 or newer. Nothing else. No PostgreSQL, no
Redis, no vector database, unless you choose them.

### From source, for development

```bash
# Backend on port 8000, with API docs at /docs
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Frontend on port 3000
npm install
npm run dev
```

The dev server passes `/api`, `/health` and `/ws` through to the backend, so
there is no CORS setup and nothing to configure. The database file appears at
`backend/data/ucsp.db` the first time it starts.

Set `SEED_DEMO_DATA=true` and the backend fills an empty database from
[`fixtures/demo.json`](fixtures/demo.json): five team members, twelve
customers, fourteen help articles, ninety days of ticket history and one
finished Tap AI call. It is off by default, because those accounts share one
published password.

### From source, as one process

The backend serves the built frontend when `dist/` exists, so there is no
second server and no reverse proxy to configure.

```bash
npm install && npm run build          # builds the app and the widget
cd backend && pip install -r requirements.txt
SECRET_KEY="$(openssl rand -hex 32)" uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### With Docker

The image does the two build steps above for you, so this is the same thing
packaged. One container, one port, SQLite in a named volume.

```bash
cp .env.example .env      # set SECRET_KEY at minimum
docker compose up --build # http://localhost:8000
```

That starts empty. Add `SEED_DEMO_DATA=true` to `.env` if you want the sample
workspace to look around first.

### With PostgreSQL instead of SQLite

Works with either of the two above. Nothing else changes, there is no migration
step, and the tables are created on the first start.

```bash
pip install asyncpg   # already in the Docker image
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/ucsp
```

Snapshots are the one thing that differs. They copy the SQLite file, so on
PostgreSQL the platform says so and asks you to use your own database tooling.
See [`docs/data.md`](docs/data.md).

### With no backend at all

`npm run dev` on its own works too. When nothing answers on `/health` the
frontend falls back to a demo that runs in the browser, built from the same
fixture, with real retrieval and real ticket aggregation and no network. That
is what makes the hosted demo work, and it is why the sign in screen offers one
click roles.

## Configuration

Everything is optional except `SECRET_KEY` in production. See
[`.env.example`](.env.example) for the full list, and
[`docs/configuration.md`](docs/configuration.md) for what each one changes.

```bash
SECRET_KEY=...                        # required in production, sessions break without a stable value
DATABASE_URL=sqlite+aiosqlite:///...  # the default, point it at PostgreSQL to scale out

LLM_PROVIDER=openai                   # none, openai, anthropic or gemini
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=                         # set this for Ollama, vLLM, Groq, OpenRouter
EMBEDDING_MODEL=                      # optional, turns on semantic retrieval
```

With `LLM_PROVIDER=none`, which is the default, every AI feature still works. It
returns the best matching passage with its source instead of a written reply,
and labels itself `grounded-fallback`.

## Connecting channels

Each channel is set up per workspace under Settings, Channels, which also shows
the webhook URL to paste into the provider dashboard. Signature checks are
required, so a delivery that does not match the configured secret is rejected.

| Channel | Provider | Credentials |
|---|---|---|
| Web chat and widget | built in | none |
| Email | any SMTP host, with IMAP polling or an inbound webhook | `smtp_host`, `smtp_port`, `from_address` |
| WhatsApp | Meta Cloud API | `app_secret`, `verify_token`, `access_token`, `phone_number_id` |
| Instagram | Meta Graph API | `app_secret`, `verify_token`, `access_token`, `page_id` |
| SMS and voice | Twilio | `account_sid`, `auth_token`, `from_number` |
| API | built in | a workspace secret key |

See [`docs/channels.md`](docs/channels.md) for step by step setup, and for how
to add a new channel in one file.

### The widget

```html
<script
  src="https://your-domain.example/widget.js"
  data-key="pk_your_workspace_public_key"
  defer
></script>
```

Your public key is under Settings, Developer. `public/widget-demo.html` is a
test page you can open against a local install.

### The API

```bash
curl -X POST https://your-domain.example/api/v1/tickets \
  -H "Authorization: Bearer sk_your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Order never arrived","priority":"high","customerEmail":"a@example.com"}'
```

A workspace key acts with owner rights on that workspace and reaches nothing
else. The full OpenAPI schema is served at `/docs`.

## Architecture

```
React and Vite, TypeScript                FastAPI, Python
   ├── demo mode, fixture in the browser    ├── channels/   normalise every provider
   └── live mode, HTTP and WebSocket ─────> ├── ai/         retrieval and provider adapters
                                            ├── services/   one ingest path for all channels
                                            └── SQLite, or PostgreSQL
```

Everything that comes in, whether that is a widget message, a WhatsApp webhook
or an email, becomes an `InboundMessage` and takes one path: match the customer,
match or open the conversation, append the message, apply routing and the SLA
clock, optionally answer with AI, then broadcast to connected agents. That is
what makes the inbox genuinely unified, and it is why adding a channel touches
one file.

More in [`docs/architecture.md`](docs/architecture.md).

### Decisions worth explaining

**One ingest path.** A widget message, a WhatsApp webhook and an inbound email
are three different shapes. Each adapter turns its own into an `InboundMessage`
and that is the last time the difference matters. Nothing above
`services/ingest.py` branches on channel, so routing, SLA clocks, customer
matching, AI drafting and the live broadcast are written once.

**Every AI feature falls back to retrieval.** `LLM_PROVIDER=none` is the
default and it is also the test configuration, so no feature is allowed to fail
outright without a model. Without one the assistant answers by quoting the
passage that matches, labelled `grounded-fallback`. That constraint is why the
test suite needs no network and no keys.

**Confidence is retrieval coverage, not how sure the model sounds.** A model
asked how sure it is will say ninety percent about something it made up.
Coverage measures how much of the question the best article actually contains,
weighted by how rare each matched word is, then flattened towards one. It is
comparable between questions, which is what makes it usable for deciding when
to hand over. Questions nothing covers score zero and go to a person.

**Retrieval quality is measured, not asserted.**
[`backend/tests/test_retrieval_quality.py`](backend/tests/test_retrieval_quality.py)
runs a set of help articles written the way a shop writes them against
questions written the way a customer asks them, neither tuned for the other,
and pins the accuracy. A ranking change has to prove it is not a step
backwards.

**Portable SQL, on purpose.** String ids, plain `JSON` columns, string enums
and naive UTC datetimes throughout, so the same schema runs on SQLite and
PostgreSQL with nothing swapped. That is what lets the default install be a
single file and the scaled one be a connection string.

**Secrets never leave the server.** Channel credentials and model keys are
sealed by `crypto.py` on the way in and read back only through
`ChannelAccount.live_config`, so no call site can forget to decrypt or
accidentally serialise one. The API returns which keys are set, never a value.

**Permission is a server concern.** `is_manager` and the `Manager` dependency
in `security.py` are the check. The interface not offering a button is a
courtesy to the person using it, never the thing standing between an agent and
a supervisor action.

**One token layer, two themes.** Components only ever name semantic tokens such
as `bg-surface` and `text-ink`, with no raw colours anywhere. Dark mode is the
same components with the tokens repointed, so it cannot drift out of date.

**The widget is its own build.** `vite.widget.config.ts` emits a single file
with no dependencies that renders inside a shadow root, so it cannot inherit or
clash with the styles of whatever site it is pasted into.

**Stack.** React 19, Vite, Tailwind v4 and TypeScript on the frontend. FastAPI,
SQLAlchemy 2 and SQLite on the backend. Six runtime npm dependencies and ten
Python ones. Passwords and tokens use only the standard library, so there is no
bcrypt or PyJWT build step. The one native dependency is cryptography, which
encrypts the API keys and channel credentials you store.

## Development

```bash
npm run typecheck        # tsc --noEmit
npm test                 # 39 frontend tests
npm run build            # app and widget

cd backend
ruff check .             # linting
pytest                   # 237 tests, no services required
```

The backend suite runs against in memory SQLite with no LLM provider, which is
the same path a fresh install takes before any credentials are added. It also
runs against PostgreSQL unchanged, which is what keeps the portable schema
honest.

CI does all of that on every push: lint and test the backend on both databases,
typecheck, test and build the frontend, then build the Docker image and check
the container starts, serves and does not run as root.

## Documentation

- [`docs/architecture.md`](docs/architecture.md), how the pieces fit together
- [`docs/configuration.md`](docs/configuration.md), every environment variable
- [`docs/channels.md`](docs/channels.md), connecting and adding channels
- The setup guide at `/setup` in the running app, install to export
- [`docs/data.md`](docs/data.md), where the data lives, backups and export
- [`docs/security.md`](docs/security.md), what is handled and what is not
- [`CONTRIBUTING.md`](CONTRIBUTING.md), how to work in this repository
- [`SECURITY.md`](SECURITY.md), how to report a vulnerability

## License

Functional Source License 1.1, with an MIT future grant. See
[`LICENSE`](LICENSE).

In plain words: anyone can run this for free, including a business using it for
their own customer service. You can read it, change it, and share your changes.
What you cannot do is sell it, or offer it to other people as a paid product or
a paid hosted service that competes with it.

Two years after each version is published, that version becomes MIT licensed,
so the restriction lifts by itself and nothing is locked up forever.

This is fair source rather than open source in the strict sense, because open
source as the Open Source Initiative defines it cannot restrict how you use the
software. Saying so plainly seems better than borrowing a label that does not
fit.

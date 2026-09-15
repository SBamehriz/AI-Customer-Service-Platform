# Architecture

## The shape of it

```
┌─────────────────────────────┐        ┌──────────────────────────────────────┐
│ React and Vite, TypeScript  │        │ FastAPI, Python                      │
│                             │        │                                      │
│  app/       routing,session │ HTTP   │  api/        routers                  │
│  features/  one per surface │◄──────►│  channels/   provider adapters        │
│  components/ design system  │  WS    │  ai/         retrieval, LLM adapters  │
│  lib/api    client contract │        │  services/   ingest pipeline          │
│  lib/demo   in browser stub │        │  models.py   the whole schema         │
│  widget/    embeddable chat │        │                                      │
└─────────────────────────────┘        └───────────────┬──────────────────────┘
                                                       │
                                        SQLite by default, PostgreSQL optional
```

## The one idea

Everything that comes in becomes an `InboundMessage` and takes exactly one
path, in `backend/app/services/ingest.py`.

```
InboundMessage
  → resolve_customer   match on email, then phone, then channel id
  → find_conversation  continue an open thread on the same provider thread id
  → append Message
  → _ensure_ticket     open a ticket, run routing rules, start the SLA clock
  → _auto_reply        draft from the knowledge base, or escalate
  → hub.publish        push the change to connected agents
```

A WhatsApp webhook, an email and a widget message all produce the same rows and
the same agent experience. That is what unified means here, and it is why a new
channel is one adapter file plus one line in the registry. Nothing above this
layer changes.

## Channels

Every adapter in `backend/app/channels/` implements two operations.

```python
parse_inbound(payload, config) -> list[InboundMessage]   # provider to us
send(config, to=..., body=...) -> str | None             # us to provider
```

There is also `verify_signature`, which is required for anything with a
webhook. One route handles them all.

```
POST /api/v1/webhooks/{channel}/{workspace_id}
```

It looks up that workspace's credentials, verifies the signature, hands the raw
body to the adapter, and pushes whatever comes back through ingest. Voice is
the exception. A call has no message body, so speech callbacks are routed into
the live Tap AI session instead of the inbox.

Signatures are verified against the URL built from `PUBLIC_URL`, not the URL
this process happens to see. Twilio signs the exact address it called, and
behind a proxy that terminates TLS the two are different.

## AI

Three layers, in `backend/app/ai/`.

`providers.py` holds LLM adapters over plain `httpx`, with no vendor SDKs.
Three protocols cover the market. OpenAI chat completions, which also covers
Groq, Together, OpenRouter, Mistral, vLLM and Ollama through `LLM_BASE_URL`.
Anthropic messages. Google generative language. Setting `LLM_PROVIDER=none`
selects a null provider that reports itself unavailable.

`retrieval.py` scores the workspace's published articles with BM25, computed in
Python. There is no vector database. When `EMBEDDING_MODEL` is set, cached
vectors in the `articles.embedding` column add a semantic score, weighted
sixty to forty in favour of lexical, because support questions usually share
vocabulary with the article that answers them.

`assist.py` is the grounded layer. Retrieval runs first, the model only ever
sees the passages it is handed, and confidence comes from the retrieval score
rather than the model's own view of itself. A fluent answer over weak passages
is exactly the dangerous case, so it scores low and escalates.

With no provider configured the same retrieval runs and returns the best
passage as written, labelled `grounded-fallback`. The feature degrades, it does
not disappear.

## Data

One module, `backend/app/models.py`, thirteen tables. Deliberately portable.

| Instead of | We use | Why |
|---|---|---|
| `UUID` columns | 32 character hex strings | Works on SQLite and PostgreSQL unchanged |
| `JSONB` | generic `JSON` | Same |
| `ARRAY` | JSON arrays | Same |
| native enums | plain strings | Adding a status never needs a migration |
| aware datetimes | naive UTC | SQLite has no timezone storage, and mixing the two is the usual source of subtraction bugs |

The whole test suite runs against both SQLite and PostgreSQL, so the table
above is checked rather than asserted.

`init_db` runs `create_all`, which adds missing tables but never alters
existing ones, then adds any nullable column the models have gained since. That
is enough to upgrade a single file SQLite install in place. It is explicitly not
enough for a renamed column, a changed type, or PostgreSQL in production. Put a
migration tool in front of those.

## Realtime

`backend/app/realtime.py` is an in process hub. One process holds the sockets,
so there is no broker to run. That is correct for a single node. Several API
replicas would need a shared bus behind the same `publish` call. Clients
reconnect with backoff, in `src/lib/realtime.ts`.

## Frontend

Pages talk to an `ApiClient` interface in `src/lib/api.ts`, never to `fetch`.
There are two implementations.

`createHttpClient` talks to the real backend. `createDemoClient` is an in
memory implementation over the same fixture the backend seeds from, including
real BM25 retrieval and real ticket aggregation.

At boot the app probes `/health` and picks one. Because the choice lives behind
the interface, no component contains a demo branch. The demo client loads
through a dynamic import, so a live install never downloads the sample data.

The API speaks camelCase, so responses are used as they arrive with no mapping
layer. That mapping layer is the class of code that made the previous version
hard to change.

## Design system

`src/styles/globals.css` has two layers. A fixed palette, then semantic roles
like `--surface`, `--ink` and `--accent` that point at it and are repointed for
dark mode. Components only use the semantic layer, so the whole product
rethemes from about thirty lines. Tailwind reads them through `@theme inline`,
which emits `var()` references rather than baking in light mode values.

Base element styles live in `@layer base`. This matters. Unlayered rules
outrank every layered one, so an unlayered `p { text-wrap: pretty }` silently
defeats `truncate` everywhere.

Typography is the native system stack. SF on Apple platforms, Segoe on Windows,
Inter or Cantarell on Linux. No webfont request, nothing to self host.

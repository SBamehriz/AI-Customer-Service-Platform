# Contributing

## Setup

```bash
npm install
cd backend && pip install -r requirements-dev.txt
```

Run both halves in separate terminals.

```bash
cd backend && uvicorn app.main:app --reload    # port 8000
npm run dev                                    # port 3000, passes through to 8000
```

## Before you push

```bash
npm run typecheck        # has to be clean
npm test                 # has to be green
npm run build            # app and widget
npm run audit            # npm and pip advisories

cd backend
ruff check .             # has to be clean
pytest                   # has to be green
```

The tests run against in memory SQLite with no LLM provider configured, which
is the same path a fresh install takes. If a change only works with an API key,
it needs a fallback.

## Where things go

| What | Where |
|---|---|
| A new channel | `backend/app/channels/` plus one line in its `__init__.py` |
| A new API route | `backend/app/api/`, then include it in `api/__init__.py` |
| Schema change | `backend/app/models.py`, one module on purpose |
| A new page | `src/features/<name>/`, imported lazily in `src/app/App.tsx` |
| Shared UI | `src/components/ui/`, check it does not already exist |
| Design tokens | `src/styles/globals.css` |
| Icons | `src/components/icons.ts`, never import `lucide-react` directly |
| Demo data | `fixtures/demo.json`, read by the backend seed and by demo mode |
| A frontend test | next to what it tests, in a `__tests__` folder |

## House rules

**Portability.** The backend has to run on SQLite and PostgreSQL unchanged, so
no column types specific to one dialect and no raw SQL that only one of them
understands. CI runs the whole suite against both. To check locally:

```bash
pip install asyncpg
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ucsp pytest
```

**Degrade, never disappear.** Every AI feature has to work with
`LLM_PROVIDER=none`. Retrieval on its own is the floor, not an error state.

**Ground everything.** No AI output reaches a user without the passages it came
from. Confidence tracks retrieval quality, not what the model thinks of itself.

**One conversation model.** Anything specific to a channel belongs in an
adapter. If something above `services/ingest.py` needs to know which channel a
message came from, that is a sign the design has slipped.

**Semantic tokens only.** Use `bg-surface`, `text-ink` and `border-line`, never
a raw hex value and never a palette step directly. That is what keeps dark mode
working without a second stylesheet.

**Base CSS goes in `@layer base`.** Unlayered rules outrank every Tailwind
utility, so an element selector outside a layer quietly breaks utilities across
the whole app.

**Demo mode mirrors the backend.** `src/lib/demo/retrieval.ts` is a port of
`backend/app/ai/retrieval.py`, so a change to one belongs in the other. The
stopword list and the scoring constants are checked against each other by a
test, because they had quietly drifted apart once already.

**Be honest in the docs.** If something needs credentials to work, say so. The
status table in `README.md` is part of the deliverable.

## Style

TypeScript and Python only. Keep the dependency list short, because every
addition is something a self hoster has to install and you have to keep
patched.

Comments are for the things the code cannot say. Most files need very few. Skip
anything that restates the line below it.

Prose here stays plain. Commas, full stops and colons do the work, and a long
clause becomes two sentences rather than being stitched together with dashes.
That covers comments, documentation and anything a person reads in the
interface. Names keep their own punctuation, so a header such as
`X-Twilio-Signature` and a value such as `grounded-fallback` are written the way
the wire writes them.

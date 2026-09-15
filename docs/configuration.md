# Configuration

Every setting has a working default. An empty environment starts a SQLite
database, generates a development signing key, and runs with no LLM provider.
`SECRET_KEY` is the only value that genuinely has to be set before you deploy.

Settings are read from the environment, then `backend/.env`, then `.env` at the
repository root. See [`.env.example`](../.env.example).

## Core

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | generated per process | Set this in production. A generated key is different in every process, so sessions break on restart and every token is rejected as soon as there is more than one worker. The server logs a warning when it has generated one. |
| `DATABASE_URL` | `sqlite+aiosqlite:///backend/data/ucsp.db` | For PostgreSQL, install asyncpg and set `postgresql+asyncpg://user:pass@host/db`. |
| `DEBUG` | `false` | Turns on SQL echo and debug logging. |
| `ACCESS_TOKEN_TTL_MINUTES` | `720` | How long a sign in lasts. |
| `SEED_DEMO_DATA` | `false` | Loads the sample workspace into an empty database so you can look around. Leave it off for anything real, because the demo accounts share one password and that password is in the README. |
| `PUBLIC_URL` | `http://localhost:8000` | The origin providers actually call. It builds the webhook addresses shown in Settings, and every signature check is verified against it, so a delivery signed for your real domain is rejected while this still says localhost. Startup warns while it is unset, and a rejected delivery logs the address it was checked against so the two can be compared. Web chat and email do not use it. |
| `CORS_ORIGINS` | `localhost:3000,localhost:5173` | Comma separated, or a JSON array. |
| `WIDGET_ALLOW_ANY_ORIGIN` | `true` | The widget runs on sites you do not control, so its public endpoints accept any origin. They are scoped by workspace public key and can only create or read one conversation. Set it to false if you do not use the widget. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Read by uvicorn. The address your reverse proxy connects from, so `X-Forwarded-For` is trusted and visitors keep their real address. Without it the per address rate limit sees every visitor as the proxy. |
| `BACKUP_INTERVAL_HOURS` | `24` | How often the database is copied into `backend/data/backups/`. The newest fourteen are kept. Set 0 to turn the timer off, for instance when something outside already backs the volume up. See [`data.md`](data.md). |

## Rate limits

Ceilings on the routes anyone can reach without signing in. The defaults suit a
small business install and most people never touch them. Set one to 0 to turn
that ceiling off, which is only sensible when a reverse proxy is already doing
the job. Counting is per process, so several workers each get their own
allowance.

| Variable | Default | Notes |
|---|---|---|
| `RATE_LIMIT_SIGN_IN_PER_ADDRESS` | `60` | Sign in attempts allowed from one network address per window. Checking a password is a deliberately slow hash, so this bounds how much of the server's time one source can spend. Raise it if a whole office behind one address is being throttled by its own people. |
| `RATE_LIMIT_SIGN_IN_PER_ACCOUNT` | `10` | Sign in attempts allowed against one account per window, whichever addresses they come from. This is what makes guessing one person's password impractical. |
| `RATE_LIMIT_SIGN_IN_WINDOW_SECONDS` | `300` | The window both sign in ceilings are measured over. |
| `RATE_LIMIT_REGISTRATIONS` | `10` | New workspaces one address can create per window. Creating one is cheap for the caller and permanent for the server. Raise it if you open a workspace per client. |
| `RATE_LIMIT_REGISTRATIONS_WINDOW_SECONDS` | `3600` | The window registrations are measured over. |

## Build time

Read by Vite when the frontend is built, not by the backend, so changing one
means building again.

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_URL` | empty | Where the frontend calls the API. Empty means the same origin it was served from, which is what the single process and Docker setups want. |
| `VITE_REPO_URL` | the project repository | Where the Source links on the landing page and the setup guide point. Set this if you host the code somewhere else. |

## AI

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `none` | One of none, openai, anthropic, gemini. Setting it here pins the provider for everyone and makes Settings, AI read only. Leave it unset to let each workspace bring its own key through the interface, stored encrypted. |
| `LLM_API_KEY` | empty | |
| `LLM_MODEL` | provider default | For example `gpt-4o-mini`, `claude-sonnet-4-5`, `gemini-2.0-flash`. |
| `LLM_BASE_URL` | provider default | Point `openai` at any compatible server. |
| `LLM_TIMEOUT_SECONDS` | `30` | |
| `EMBEDDING_MODEL` | empty | Adds semantic retrieval alongside BM25. Vectors are cached on the article row, so there is still no vector database. |

With `LLM_PROVIDER=none` every AI feature still works. It returns the best
matching knowledge passage with its citation, labelled `grounded-fallback`.

### Local models

```bash
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1   # Ollama
LLM_MODEL=llama3.1
LLM_API_KEY=ollama                       # ignored, but the header has to exist
```

The same shape works for vLLM, LM Studio, Groq, Together and OpenRouter.

## Per workspace settings

Anything that varies by workspace lives in the database rather than the
environment. Brand voice, greeting, escalation thresholds, channel credentials.
Edit them under Settings, or with `PATCH /api/v1/workspace`.

| Setting | Default | Effect |
|---|---|---|
| `greeting` | a friendly line | The first thing the widget and the portal show. |
| `aiAutoreply` | `true` | When off, the assistant still drafts for agents but never sends anything itself. |
| `aiSuggestThreshold` | `0.3` | Answer without a person at or above this, hand over below it. Confidence is retrieval coverage, so a question sharing one distinctive word with the article that answers it lands around 0.27 to 0.35, two words around 0.52, and a question nothing covers lands at 0. Autopilot reads the same number. |
| `escalateAfterAiTurns` | `4` | Hard ceiling on AI turns in one conversation. |
| `brandVoice` | `Warm, direct and specific. Never guess.` | Added to the system prompt. |
| `instructions` | empty | Extra rules applied to every reply. Short ones are followed more reliably. |
| `fallbackMessage` | a line offering a teammate | Sent when the assistant escalates. |
| `autopilotEnabled` | `false` | Lets the schedule work the waiting queue on its own. The button in Settings runs a pass either way. |
| `autopilotHours` | empty | Hours of the day in UTC when the schedule runs. A range such as `22-6` wraps midnight, and a list such as `9,10,11` also works. Empty means the schedule never fires. During an allowed hour a pass runs every fifteen minutes, and it never answers a thread twice without a customer reply in between. |
| `recordCalls` | `false` | Records calls through Twilio. It cannot be turned on without a notice, see below. |
| `recordingNotice` | a spoken notice | Played before recording starts. Saving `recordCalls` on with this blank is refused, because recording somebody without telling them is illegal in a lot of places. |

Confidence measures how well your knowledge base covered the question, not how
sure the model is. Raising the threshold escalates more, it does not make
answers more accurate.

### Stored but not yet enforced

Two settings and one SLA field are saved, exported and shown in the interface,
and nothing reads them to make a decision yet. They are listed here rather than
left to be discovered.

| Setting | State |
|---|---|
| `aiAutoresolveThreshold` | Stored only. Nothing closes a conversation on its own. |
| `businessHours` | Stored only. SLA deadlines are not paused outside them. |
| `resolutionMinutes` on an SLA policy | Stored only. The first response deadline is enforced, the resolution target is not. |

### Validation

The settings above are the ones the platform itself reads, so they are checked
when they are saved. Text has to be text, a flag has to be true or false, a
threshold has to be a number between 0 and 1, and the AI turn ceiling has to be
a whole number that is not negative. A value of the wrong shape is refused with
a 422 that names the field, rather than being stored and failing later on a
customer message. Any other key you add is stored as it is.

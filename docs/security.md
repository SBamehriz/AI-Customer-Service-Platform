# Security

An honest account of what is handled and what is not. This project has not had
a third party security review.

## What is handled

Passwords use `hashlib.scrypt` with N of 16384, r of 8 and p of 1, a fresh salt
each time, and a constant time comparison. Sign in runs a verification even when
the account does not exist, so a missing account and a wrong password take the
same time.

Tokens are HS256 JWTs signed with `SECRET_KEY` and verified with
`hmac.compare_digest`. A tampered payload, a forged signature and an expired
token are all rejected the same way. Auth uses only the standard library, so
there is no cryptography or bcrypt build to keep patched.

Workspace isolation. Every query is scoped by workspace id, and the scope comes
from the token rather than from anything the client sends. Cross workspace
access is covered by tests, for both session tokens and API keys.

API keys are shown once and stored only as a SHA256 hash. Issuing a new one
invalidates the previous one immediately. A key acts with owner rights on its
own workspace and reaches nothing else.

Webhook signatures are required and provider correct. HMAC SHA256 over the raw
body for Meta, HMAC SHA1 over the full URL plus sorted parameters for Twilio,
verified against `PUBLIC_URL` so a TLS terminating proxy does not break it. A
Meta channel with no app secret refuses every delivery rather than accepting
unsigned writes.

Redelivery is idempotent, per workspace. Providers retry, and a repeated
provider message id does not post twice in the same workspace. The check is
scoped, because a provider message id is only unique to that provider account
and two workspaces can be sent the same message.

Socket handshakes load the account, not just the claims in the token. A token
is signed before an account is switched off, so reading the claims alone would
let a disabled account reconnect and keep writing to a live call transcript.

Uploaded files are checked three ways. The content type has to be one of a
short allowlist, the name must not be an extension that makes it a program, and
the first bytes must not look like one either. The type comes from whoever is
uploading, so it cannot be the only check. Files are served with `nosniff` and a
sandboxing content security policy, and only images, audio and video are shown
in place.

A file waiting to be attached belongs to whoever uploaded it. An upload sits
with no message on it between being sent and the message going out, so it
carries a key naming the agent or the visitor session that may attach it. Files
on an internal note are not reachable from a customer's session, the same as
the note itself.

Channel credentials never leave the server. The channels endpoint returns the
names of configured keys, not the values, and a test asserts the secret does not
appear in the response body.

Rate limiting on the widget endpoints, which are the only place anyone can write
without signing in. Twenty messages a minute per visitor per workspace, sixty a
minute per network address, and twelve uploads every five minutes. The session
id comes from the client, so the address ceiling is what a script rotating
session ids runs into. All of them are counted in process.

The accent colour is validated as a hex colour, because the widget interpolates
it into its own stylesheet.

Roles, enforced on every route rather than hidden in the interface. There are
three. An agent answers customers, opens tickets and writes knowledge drafts. A
supervisor also publishes and deletes knowledge, deletes tickets, writes shared
macros, and sets SLA targets, routing and channel credentials. An owner also
manages the team, issues API keys and is the only role that can clear the team
when resetting a workspace.

The knowledge base is treated as policy rather than content, because every
answer the assistant gives a customer is quoted from it. An agent who could
rewrite a published article could change what every customer is told, so
publishing, editing anything already published, and deleting are all supervisor
actions.

Escalation paths are closed deliberately. A supervisor cannot create or promote
an owner, which would otherwise let them mint an account on an address they
control. A workspace API key acts with owner rights, so only an owner can issue
one, or issuing a key would be the way around the rule above. Reset keeps every
active owner, because clearing the team is otherwise a way to remove an owner
that the team endpoint refuses. Nobody can change their own role or switch off
their own account, and the last active owner cannot be stood down, so a
workspace can never be left with nobody able to configure it.

AI grounding. The model only ever sees retrieved passages and is told to answer
from them alone. Confidence comes from the retrieval score rather than the
model's self assessment, and low confidence hands over to a human. Internal only
articles are excluded from anything that answers a customer, both the immediate
reply and the scheduled Autopilot pass.

## What is not

There is no audit log, so who changed what is not recorded.

There is no SSO, no MFA and no password reset flow.

There are no CSRF tokens. Auth is a bearer token sent in a header rather than a
cookie, so the usual CSRF vector does not apply, but do not move to cookie auth
without adding them. The token is kept in `localStorage` so a reload does not
sign you out, which means anything that can run script in the page can read it.

Widget endpoints accept any origin by design, because the widget runs on sites
you do not control. They are scoped to one conversation by public key. Set
`WIDGET_ALLOW_ANY_ORIGIN=false` if you do not use the widget.

The database file itself is not encrypted. Stored credentials inside it are,
with a key derived from `SECRET_KEY`, see `crypto.py` and `docs/data.md`, so a
copy of the file alone does not hand over channel or provider keys. Everything
else in it is plain, so protect the file.

There are no migrations. `create_all` adds tables, and start up adds any
nullable column the models have gained since, which is enough to upgrade a
single file install in place. Anything beyond that, a renamed column or a
changed type, needs a migration tool.

The rate limiter counts per process, so several workers each get their own
allowance. Anything larger than a single node wants a real limiter in the
reverse proxy.

The per address limit is only as good as the address the app sees. Behind a
reverse proxy, set `FORWARDED_ALLOW_IPS` to the address the proxy connects
from, otherwise every visitor arrives as the proxy and they share one
allowance.

## Before you deploy

1. Set `SECRET_KEY` to a stable random value. Without it one is generated per
   process, sessions break on restart, and with more than one worker every token
   is rejected. The server warns at startup when this applies.
2. Set `SEED_DEMO_DATA=false`, or a fresh database gets the sample workspace
   with its published credentials.
3. Set `PUBLIC_URL` to your real origin, or Twilio signature checks will fail.
4. Terminate TLS in front of the app and add rate limiting there.
5. Restrict `CORS_ORIGINS`.
6. Back up the SQLite file and the attachments directory beside it, or move to
   PostgreSQL with a migration tool and back the files up separately.

## Reporting

See [`SECURITY.md`](../SECURITY.md).

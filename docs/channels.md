# Channels

Every channel produces the same records. Connect one under Settings, Channels,
which shows the webhook URL to paste into the provider and reports exactly
which credentials are still missing.

Credentials are stored per workspace and are never returned by the API. The
channels endpoint reports the names of the keys you have set, never the values.

## Web chat and the widget

Built in, no credentials. Two surfaces share one code path.

The hosted portal lives at `/portal` and is a full page chat. The embeddable
widget is one script tag on any site.

```html
<script
  src="https://your-domain.example/widget.js"
  data-key="pk_your_workspace_public_key"
  data-api="https://your-domain.example"
  defer
></script>
```

`data-api` is optional and defaults to the origin the script came from. The
public key is under Settings, Developer. It identifies a workspace but
authorises nothing. It can start a conversation and read that one conversation
back, and nothing else.

The widget renders inside a shadow root, so it cannot collide with the host
page's styles in either direction. It is 13.7 kB minified, 4.5 kB gzipped, with
no dependencies. `public/widget-demo.html` is a test page.

On a single workspace install the portal finds its workspace on its own. With
several workspaces, pass one in the URL as `/portal?key=pk_...`.

## Email

Outbound is SMTP. Inbound works two ways, so you are not forced into a paid
relay.

IMAP polling means the platform logs into a shared mailbox every 60 seconds and
pulls unread mail, with nothing to configure at a provider. The alternative is
an inbound webhook, where Postmark, Mailgun and SendGrid payloads are detected
automatically.

| Key | Required | Notes |
|---|---|---|
| `smtp_host`, `smtp_port`, `from_address` | yes | Port 587 for STARTTLS, 465 for implicit TLS |
| `smtp_user`, `smtp_password` | no | Leave out for an unauthenticated relay |
| `imap_host`, `imap_user`, `imap_password` | no | Turns on polling |
| `webhook_secret` | no | Checked against `X-Webhook-Token` on inbound deliveries |

Threading uses the root of the `References` header, so a customer's reply lands
on the same conversation. Quoted history is stripped so agents read the new
content rather than the whole thread.

## WhatsApp Business

Meta Cloud API.

1. Create a Meta app with the WhatsApp product and get a permanent access token.
2. Under Settings, Channels, WhatsApp, enter `app_secret`, `verify_token`, which
   is any string you choose, `access_token` and `phone_number_id`. Save.
3. Copy the webhook URL shown there into Meta's webhooks configuration, using
   the same verify token. Meta calls the URL with a challenge, and the platform
   echoes it back to prove it owns the endpoint.
4. Subscribe to the `messages` field.

Every delivery has to carry a valid `X-Hub-Signature-256` computed with your app
secret. With no app secret configured the endpoint refuses everything, because
anonymous writes into a customer's inbox are not something to allow by default.

## Instagram Direct

Same Graph API and the same webhook envelope. It needs `app_secret`,
`verify_token`, `access_token` and `page_id`, with the Instagram account linked
to a Facebook page. Echoes of your own outbound messages are skipped.

## SMS and voice

Twilio, sharing `account_sid`, `auth_token` and `from_number`.

SMS is an ordinary two way channel.

Voice is different. A call has no message body until it is transcribed, so
speech callbacks become transcript lines feeding the live Tap AI session rather
than inbox messages.

### Connecting a phone number for live calls

Settings, Channels, Voice shows these steps and the exact webhook address for
your install, so you should not need this page. It is here for anyone who
prefers reading first.

1. In the Twilio console, go to Phone Numbers, Manage, Buy a number. Tick
   Voice, and buy one in the country you want to be reachable in.
2. Open the number you just bought and find Voice Configuration.
3. Set A call comes in to Webhook, paste the address below, and set the method
   to HTTP POST.

```
POST {PUBLIC_URL}/api/v1/webhooks/voice/{workspace_id}/answer
```

4. Copy Account SID and Auth Token from the console home page into Settings,
   Channels, Voice, along with the number itself in `from_number`.
5. Save and activate.
6. Call the number. The transcript appears under Tap AI while the call is
   still going, with suggestions beside it.

The endpoint returns TwiML that greets the caller and streams speech back.

Two things account for most setups that do not work.

`PUBLIC_URL` has to be the address Twilio actually calls. Twilio signs the
exact URL, and the platform checks that signature, so a mismatch means every
delivery is rejected. On a laptop behind a tunnel, set `PUBLIC_URL` to the
tunnel address, not to localhost.

This is the failure that looks like nothing at all. Everything else stays
healthy, the console shows deliveries going out, and the inbox stays empty. Two
things in the log settle it. Startup warns while `PUBLIC_URL` is still the
default, and each rejected delivery writes the address its signature was
checked against, so you can compare that line against what you pasted into the
provider.

The number needs the Voice capability. A number bought for SMS only will not
ring through, and Twilio does not warn you at the point of sale.

## API

Push messages in from your own backend with the workspace secret key.

```bash
curl -X POST https://your-domain.example/api/v1/tickets \
  -H "Authorization: Bearer sk_your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Order never arrived","priority":"high","customerEmail":"a@example.com"}'
```

Issue a key under Settings, Developer. It is shown once, and only its hash is
stored. A workspace key acts with owner rights on that workspace and reaches
nothing else.

## Adding a channel

One file and one line. Subclass `ChannelAdapter` in `backend/app/channels/`.

```python
class TelegramAdapter(ChannelAdapter):
    name = "telegram"
    label = "Telegram"
    required_keys = ("bot_token", "webhook_secret")
    has_webhook = True
    can_send = True

    def verify_signature(self, config, raw_body, headers) -> bool: ...
    def parse_inbound(self, payload, config) -> list[InboundMessage]: ...
    async def send(self, config, *, to, body, context=None) -> str | None: ...
```

Register it in `channels/__init__.py`, add the name to `CHANNELS` in
`models.py`, and to the `Channel` union in `schemas.py` and `src/lib/types.ts`.
Routing, tickets, SLA, AI, the inbox UI and the settings screen all pick it up
with no further changes.

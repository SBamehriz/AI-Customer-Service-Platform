/** The embeddable chat widget. */

interface WidgetConfig {
  workspaceName: string;
  accentColor: string;
  greeting: string;
  logoUrl: string | null;
  aiEnabled: boolean;
}

interface WidgetAttachment {
  id: string;
  filename: string;
  kind: 'image' | 'audio' | 'video' | 'file';
  sizeBytes: number;
  url: string;
}

interface WidgetMessage {
  id: string;
  authorType: 'customer' | 'agent' | 'ai' | 'system';
  authorName?: string | null;
  body: string;
  createdAt: string;
  attachments?: WidgetAttachment[];
}

interface SendResponse {
  sessionId: string;
  conversationId: string;
  reply: WidgetMessage | null;
  escalated: boolean;
}

const SESSION_STORAGE_KEY = 'ucsp.widget.session';

function readSession(): string | null {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeSession(id: string): void {
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, id);
  } catch {
    // Private browsing. The thread simply will not survive a reload.
  }
}

function styles(accent: string): string {
  return `
    :host { all: initial; }
    * { box-sizing: border-box; margin: 0; padding: 0; }

    .root {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 2147483000;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #181b23;
    }

    .launcher {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 56px;
      height: 56px;
      border: none;
      border-radius: 50%;
      background: ${accent};
      color: #fff;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(15, 17, 22, 0.18), 0 12px 32px -8px rgba(15, 17, 22, 0.24);
      transition: transform 200ms cubic-bezier(0.32, 0.72, 0, 1), box-shadow 200ms;
    }
    .launcher:hover { transform: scale(1.05); }
    .launcher:active { transform: scale(0.97); }
    .launcher:focus-visible { outline: 3px solid ${accent}55; outline-offset: 3px; }

    .panel {
      display: flex;
      flex-direction: column;
      width: 380px;
      max-width: calc(100vw - 40px);
      height: 560px;
      max-height: calc(100vh - 120px);
      background: #fff;
      border: 1px solid #dfe1e6;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 16px rgba(15, 17, 22, 0.06), 0 32px 64px -16px rgba(15, 17, 22, 0.24);
      animation: rise 240ms cubic-bezier(0.32, 0.72, 0, 1);
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(12px) scale(0.98); }
      to   { opacity: 1; transform: none; }
    }

    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 14px 16px;
      background: ${accent};
      color: #fff;
    }
    .header h1 { font-size: 15px; font-weight: 600; }
    .header p { font-size: 12px; opacity: 0.85; }
    .close {
      margin-left: auto;
      width: 28px; height: 28px;
      display: flex; align-items: center; justify-content: center;
      border: none; border-radius: 8px;
      background: rgba(255,255,255,0.15);
      color: #fff; cursor: pointer;
    }
    .close:hover { background: rgba(255,255,255,0.26); }

    .log {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px;
      overflow-y: auto;
      background: #f7f8f9;
    }

    .bubble {
      max-width: 84%;
      padding: 9px 12px;
      border-radius: 14px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .bubble.them {
      align-self: flex-start;
      border-top-left-radius: 4px;
      background: #fff;
      border: 1px solid #dfe1e6;
    }
    .bubble.me {
      align-self: flex-end;
      border-top-right-radius: 4px;
      background: ${accent};
      color: #fff;
    }
    .bubble.system {
      align-self: center;
      max-width: 92%;
      text-align: center;
      font-size: 12px;
      color: #5b616d;
      background: transparent;
      border: 1px dashed #dfe1e6;
    }

    .typing { display: flex; gap: 4px; align-self: flex-start; padding: 12px; }
    .typing span {
      width: 6px; height: 6px; border-radius: 50%;
      background: #a2a7b1;
      animation: blink 1s infinite;
    }
    .typing span:nth-child(2) { animation-delay: 150ms; }
    .typing span:nth-child(3) { animation-delay: 300ms; }
    @keyframes blink { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }

    .composer {
      display: flex;
      gap: 8px;
      padding: 12px;
      border-top: 1px solid #dfe1e6;
      background: #fff;
    }
    .composer textarea {
      flex: 1;
      min-height: 38px;
      max-height: 96px;
      padding: 9px 12px;
      border: 1px solid #dfe1e6;
      border-radius: 10px;
      font: inherit;
      resize: none;
      outline: none;
    }
    .attach {
      flex: 0 0 auto; width: 34px; height: 34px; border: 0; border-radius: 8px;
      background: transparent; color: #5b6472; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
    }
    .attach:hover { background: #eceef1; color: #181b23; }
    .bubble.attachment { padding: 6px; }
    .bubble.attachment img {
      display: block; max-width: 100%; max-height: 200px;
      border-radius: 8px; object-fit: contain;
    }
    .bubble.attachment a { color: inherit; font-size: 13px; word-break: break-all; }
    .composer textarea:focus { border-color: ${accent}; box-shadow: 0 0 0 3px ${accent}22; }
    .send {
      width: 38px; height: 38px;
      display: flex; align-items: center; justify-content: center;
      border: none; border-radius: 10px;
      background: ${accent}; color: #fff; cursor: pointer;
      align-self: flex-end;
    }
    .send:disabled { opacity: 0.45; cursor: not-allowed; }

    .footnote {
      padding: 0 12px 10px;
      font-size: 11px;
      color: #787e8a;
      text-align: center;
      background: #fff;
    }

    @media (prefers-color-scheme: dark) {
      .panel { background: #0f1116; border-color: #262a33; }
      .log { background: #08090c; }
      .bubble.them { background: #181b23; border-color: #262a33; color: #f2f4f7; }
      .bubble.system { color: #a2a7b1; border-color: #262a33; }
      .composer { background: #0f1116; border-color: #262a33; }
      .composer textarea { background: #181b23; border-color: #262a33; color: #f2f4f7; }
      .attach { color: #8a94a6; }
      .attach:hover { background: #262a33; color: #f2f4f7; }
      .footnote { background: #0f1116; color: #787e8a; }
    }

    @media (max-width: 460px) {
      .root { right: 12px; bottom: 12px; left: 12px; }
      .panel { width: 100%; height: min(560px, calc(100vh - 96px)); }
    }
  `;
}

const CHAT_ICON =
  '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
const CLOSE_ICON =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
const SEND_ICON =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>';
const CLIP_ICON =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.234 20.252 21 12.3"/><path d="m16 6-8.414 8.586a2 2 0 0 0 2.829 2.829l8.414-8.586a4 4 0 1 0-5.657-5.657l-8.379 8.551a6 6 0 1 0 8.485 8.485l8.379-8.551"/></svg>';

class ChatWidget {
  private readonly host: HTMLElement;
  private readonly shadow: ShadowRoot;
  private readonly root: HTMLDivElement;
  private config: WidgetConfig | null = null;
  private sessionId = readSession() ?? '';
  private open = false;
  private sending = false;
  private messages: WidgetMessage[] = [];
  // Files uploaded but not yet sent with a message.
  private pending: WidgetAttachment[] = [];
  private previews = new Map<string, string>();

  constructor(
    private readonly apiBase: string,
    private readonly publicKey: string,
  ) {
    this.host = document.createElement('div');
    this.host.setAttribute('data-ucsp-widget', '');
    this.shadow = this.host.attachShadow({ mode: 'open' });
    this.root = document.createElement('div');
    this.root.className = 'root';
    this.shadow.append(this.root);
    document.body.append(this.host);
  }

  async init(): Promise<void> {
    try {
      const response = await fetch(`${this.apiBase}/api/v1/widget/${this.publicKey}/config`);
      if (!response.ok) throw new Error(`config ${response.status}`);
      this.config = (await response.json()) as WidgetConfig;
    } catch {
      // A misconfigured key must not leave a broken button on someone's site.
      this.host.remove();
      return;
    }

    const sheet = document.createElement('style');
    sheet.textContent = styles(this.config.accentColor || '#2f6ff0');
    this.shadow.prepend(sheet);

    if (this.sessionId) await this.loadHistory();
    this.render();
  }

  private async loadHistory(): Promise<void> {
    try {
      const response = await fetch(
        `${this.apiBase}/api/v1/widget/${this.publicKey}/sessions/${this.sessionId}`,
      );
      if (response.ok) this.messages = (await response.json()) as WidgetMessage[];
    } catch {
      // Start fresh rather than failing to open.
    }
  }

  private render(): void {
    this.root.replaceChildren();
    this.root.append(this.open ? this.renderPanel() : this.renderLauncher());
  }

  private renderLauncher(): HTMLElement {
    const button = document.createElement('button');
    button.className = 'launcher';
    button.type = 'button';
    button.setAttribute('aria-label', `Chat with ${this.config?.workspaceName ?? 'support'}`);
    button.innerHTML = CHAT_ICON;
    button.addEventListener('click', () => {
      this.open = true;
      this.render();
    });
    return button;
  }

  private renderPanel(): HTMLElement {
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', `Chat with ${this.config?.workspaceName ?? 'support'}`);

    const header = document.createElement('div');
    header.className = 'header';
    header.innerHTML = `
      <div>
        <h1>${escapeHtml(this.config?.workspaceName ?? 'Support')}</h1>
        <p>We usually reply in a few minutes</p>
      </div>`;
    const close = document.createElement('button');
    close.className = 'close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Close chat');
    close.innerHTML = CLOSE_ICON;
    close.addEventListener('click', () => {
      this.open = false;
      this.render();
    });
    header.append(close);

    const log = document.createElement('div');
    log.className = 'log';
    log.append(bubble('them', this.config?.greeting ?? 'Hi, how can we help today.'));
    for (const message of this.messages) {
      const kind =
        message.authorType === 'customer'
          ? 'me'
          : message.authorType === 'system'
            ? 'system'
            : 'them';
      if (message.body) log.append(bubble(kind, message.body));
      for (const file of message.attachments ?? []) {
        log.append(
          attachmentNode(
            kind,
            file,
            this.apiBase,
            this.publicKey,
            this.sessionId,
            this.previews.get(file.id),
          ),
        );
      }
    }
    if (this.sending) {
      const typing = document.createElement('div');
      typing.className = 'typing';
      typing.innerHTML = '<span></span><span></span><span></span>';
      log.append(typing);
    }

    const composer = document.createElement('form');
    composer.className = 'composer';
    const input = document.createElement('textarea');
    input.rows = 1;
    input.placeholder = 'Type your message';
    input.setAttribute('aria-label', 'Your message');
    const send = document.createElement('button');
    send.className = 'send';
    send.type = 'submit';
    send.setAttribute('aria-label', 'Send');
    send.innerHTML = SEND_ICON;
    send.disabled = true;

    const picker = document.createElement('input');
    picker.type = 'file';
    picker.multiple = true;
    picker.hidden = true;
    const attach = document.createElement('button');
    attach.className = 'attach';
    attach.type = 'button';
    attach.setAttribute('aria-label', 'Attach a file');
    attach.innerHTML = CLIP_ICON;
    attach.addEventListener('click', () => picker.click());
    picker.addEventListener('change', () => {
      void this.upload(picker.files);
      picker.value = '';
    });

    send.disabled = this.pending.length === 0;
    input.addEventListener('input', () => {
      send.disabled = input.value.trim().length === 0 && this.pending.length === 0;
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        composer.requestSubmit();
      }
    });
    composer.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.send(input.value);
    });
    composer.append(picker, attach, input, send);

    const footnote = document.createElement('p');
    footnote.className = 'footnote';
    footnote.textContent = this.config?.aiEnabled
      ? 'Answers come from our help articles. We hand over to a person when they do not cover your question.'
      : 'A member of the team will reply here.';

    panel.append(header, log, composer, footnote);

    // Scroll to the newest message and focus the composer once attached.
    requestAnimationFrame(() => {
      log.scrollTop = log.scrollHeight;
      input.focus();
    });
    return panel;
  }

  /** Upload the files a visitor picked, before the message that carries them. */
  private async upload(files: FileList | null): Promise<void> {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      const form = new FormData();
      form.append('file', file);
      if (this.sessionId) form.append('sessionId', this.sessionId);
      try {
        const response = await fetch(
          `${this.apiBase}/api/v1/widget/${this.publicKey}/attachments`,
          { method: 'POST', body: form },
        );
        if (!response.ok) throw new Error(`upload ${response.status}`);
        const uploaded = (await response.json()) as WidgetAttachment & { sessionId?: string };
        if (!this.sessionId && uploaded.sessionId) {
          this.sessionId = uploaded.sessionId;
          writeSession(uploaded.sessionId);
        }
        this.previews.set(uploaded.id, URL.createObjectURL(file));
        this.pending.push(uploaded);
      } catch {
        this.messages.push({
          id: `error-${Date.now()}`,
          authorType: 'system',
          body: 'That file could not be attached.',
          createdAt: new Date().toISOString(),
        });
      }
    }
    this.render();
  }

  private async send(text: string): Promise<void> {
    const body = text.trim();
    // A photo on its own is a normal way to ask for help.
    if ((!body && this.pending.length === 0) || this.sending) return;

    const attachmentIds = this.pending.map((file) => file.id);
    this.messages.push({
      id: `local-${Date.now()}`,
      authorType: 'customer',
      body: body || 'Sent a file',
      createdAt: new Date().toISOString(),
      attachments: this.pending,
    });
    this.pending = [];
    this.sending = true;
    this.render();

    try {
      const response = await fetch(`${this.apiBase}/api/v1/widget/${this.publicKey}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: this.sessionId || undefined, body, attachmentIds }),
      });
      if (!response.ok) throw new Error(`send ${response.status}`);
      const result = (await response.json()) as SendResponse;

      if (!this.sessionId) {
        this.sessionId = result.sessionId;
        writeSession(result.sessionId);
      }
      if (result.reply) this.messages.push(result.reply);
      else if (result.escalated) {
        this.messages.push({
          id: `sys-${Date.now()}`,
          authorType: 'system',
          body: 'A teammate is picking this up and will reply here shortly.',
          createdAt: new Date().toISOString(),
        });
      }
    } catch {
      this.messages.push({
        id: `err-${Date.now()}`,
        authorType: 'system',
        body: 'That message did not go through. Please try again.',
        createdAt: new Date().toISOString(),
      });
    } finally {
      this.sending = false;
      this.render();
    }
  }
}

function bubble(kind: 'me' | 'them' | 'system', text: string): HTMLElement {
  const element = document.createElement('div');
  element.className = `bubble ${kind}`;
  element.textContent = text;
  return element;
}

/** One file in the transcript. */
function attachmentNode(
  kind: 'me' | 'them' | 'system',
  file: WidgetAttachment,
  apiBase: string,
  publicKey: string,
  sessionId: string,
  preview?: string,
): HTMLElement {
  const url =
    preview ??
    (sessionId
      ? `${apiBase}/api/v1/widget/${publicKey}/sessions/${encodeURIComponent(sessionId)}/attachments/${file.id}`
      : file.url);

  const wrapper = document.createElement('div');
  wrapper.className = `bubble ${kind} attachment`;

  if (file.kind === 'image') {
    const image = document.createElement('img');
    image.src = url;
    image.alt = file.filename;
    image.loading = 'lazy';
    wrapper.append(image);
    return wrapper;
  }

  const link = document.createElement('a');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noreferrer noopener';
  link.textContent = file.filename;
  wrapper.append(link);
  return wrapper;
}

function escapeHtml(value: string): string {
  const element = document.createElement('div');
  element.textContent = value;
  return element.innerHTML;
}

function boot(): void {
  const script =
    (document.currentScript as HTMLScriptElement | null) ??
    document.querySelector<HTMLScriptElement>('script[data-key]');
  if (!script) return;

  const publicKey = script.dataset.key ?? '';
  if (!publicKey) {
    console.warn('[support-widget] missing data-key attribute');
    return;
  }
  const apiBase = (script.dataset.api ?? new URL(script.src, window.location.href).origin).replace(
    /\/$/,
    '',
  );

  const widget = new ChatWidget(apiBase, publicKey);
  void widget.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}

/** The API client used in demo mode. */

import type { ApiClient, NewTicket } from '../api';
import { ApiError } from '../api';
import type {
  AnalyticsSummary,
  Article,
  ChannelCatalogEntry,
  ChannelConnection,
  Citation,
  Conversation,
  ConversationFilters,
  Customer,
  Draft,
  InboxStats,
  LeaderboardRow,
  Macro,
  Message,
  MetricPoint,
  MixEntry,
  PortalConfig,
  Priority,
  Session,
  TapSession,
  TapSuggestion,
  Ticket,
  TicketFilters,
  User,
  Workload,
} from '../types';
import { buildDemoStore, newId, SLA_MINUTES, type DemoStore } from './dataset';
import { excerpt, searchArticles } from './retrieval';

/** Retrieval score below which the knowledge base does not cover the question. */
const ESCALATION_FLOOR = 0.35;

/** Mirrors ai_suggest_threshold in DEFAULT_WORKSPACE_SETTINGS, backend app/models.py. */
const DEFAULT_SUGGEST_THRESHOLD = 0.3;

const ESCALATION_PHRASES = [
  'manager',
  'supervisor',
  'someone else',
  'speak to a human',
  'speak to someone',
  'talk to a human',
  'talk to a person',
  'talk to someone',
  'real person',
  'real human',
  'representative',
  'escalate',
  'this is unacceptable',
  'make a complaint',
  'file a complaint',
  'cancel my account',
  'legal action',
  'refund my',
];

const CHANNEL_CATALOG: ChannelCatalogEntry[] = [
  { channel: 'web', label: 'Web chat & widget', requiredKeys: [], hasWebhook: false, canSend: false },
  {
    channel: 'email',
    label: 'Email',
    requiredKeys: ['smtp_host', 'smtp_port', 'from_address'],
    hasWebhook: true,
    canSend: true,
  },
  {
    channel: 'whatsapp',
    label: 'WhatsApp Business',
    requiredKeys: ['app_secret', 'verify_token', 'access_token', 'phone_number_id'],
    hasWebhook: true,
    canSend: true,
  },
  {
    channel: 'instagram',
    label: 'Instagram Direct',
    requiredKeys: ['app_secret', 'verify_token', 'access_token', 'page_id'],
    hasWebhook: true,
    canSend: true,
  },
  {
    channel: 'sms',
    label: 'SMS',
    requiredKeys: ['account_sid', 'auth_token', 'from_number'],
    hasWebhook: true,
    canSend: true,
  },
  {
    channel: 'voice',
    label: 'Voice',
    requiredKeys: ['account_sid', 'auth_token', 'from_number'],
    hasWebhook: true,
    canSend: false,
  },
  { channel: 'api', label: 'API', requiredKeys: [], hasWebhook: false, canSend: false },
];

const nowIso = () => new Date().toISOString();
const delay = <T,>(value: T, ms = 90): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export function createDemoClient(): ApiClient {
  const store: DemoStore = buildDemoStore();

  const connections: ChannelConnection[] = CHANNEL_CATALOG.map((entry) => ({
    id: `chn_${entry.channel}`,
    channel: entry.channel,
    displayName: entry.label,
    isActive: entry.channel === 'web',
    configuredKeys: [],
    missingKeys: entry.requiredKeys,
    webhookUrl: entry.hasWebhook
      ? `https://your-domain.example/api/v1/webhooks/${entry.channel}/ws_demo`
      : null,
    lastEventAt: null,
  }));

  function session(user = store.currentUser): Session {
    return {
      accessToken: 'demo-token',
      tokenType: 'bearer',
      expiresIn: 43200,
      user,
      workspace: store.workspace,
    };
  }

  function citationsFor(query: string, hits: ReturnType<typeof searchArticles>): Citation[] {
    return hits.map((hit) => ({
      articleId: hit.article.id,
      title: hit.article.title,
      excerpt: excerpt(hit.article, query),
    }));
  }

  /** The retrieval only answer path, the same shape the backend returns. */
  function buildDraft(question: string, includeInternal: boolean): Draft {
    const hits = searchArticles(store.articles, question, { limit: 4, includeInternal });
    const top = hits[0]?.coverage ?? 0;
    const lowered = question.toLowerCase();
    const asksForHuman = ESCALATION_PHRASES.some((phrase) => lowered.includes(phrase));

    if (hits.length === 0) {
      return {
        text: store.workspace.settings.fallbackMessage,
        confidence: 0,
        citations: [],
        engine: 'grounded-fallback',
        shouldEscalate: true,
      };
    }

    const best = hits[0];
    return {
      text: `From the article ${best.article.title}.\n\n${excerpt(best.article, question, 420)}`,
      confidence: Number(Math.min(top, 0.6).toFixed(2)),
      citations: citationsFor(question, hits),
      engine: 'grounded-fallback',
      shouldEscalate: top < ESCALATION_FLOOR || asksForHuman,
    };
  }

  function findConversation(id: string): Conversation {
    const conversation = store.conversations.find((item) => item.id === id);
    if (!conversation) throw new ApiError('Conversation not found', 404);
    return conversation;
  }

  function addMessage(conversation: Conversation, message: Omit<Message, 'id' | 'conversationId'>) {
    const full: Message = { ...message, id: newId(), conversationId: conversation.id };
    conversation.messages.push(full);
    if (!full.isPrivate) conversation.lastMessageAt = full.createdAt;
    return full;
  }

  /** The demo equivalent of the ingest pipeline in the backend. */
  function ingestCustomerMessage(sessionId: string, body: string, name?: string, email?: string) {
    let conversation = store.conversations.find(
      (item) => item.channel === 'web' && item.id.startsWith('con_web_') && item.id.endsWith(sessionId),
    );

    if (!conversation) {
      const customer: Customer = {
        id: newId(),
        name: name ?? 'Website visitor',
        email: email ?? null,
        phone: null,
        company: null,
        notes: null,
        channelIds: { web: sessionId },
        createdAt: nowIso(),
        lastSeenAt: nowIso(),
        totalTickets: 1,
        openTickets: 1,
      };
      store.customers.unshift(customer);

      const number = Math.max(0, ...store.tickets.map((ticket) => ticket.number)) + 1;
      const ticket: Ticket = {
        id: newId(),
        number,
        subject: deriveSubject(body),
        description: body,
        status: 'new',
        priority: 'medium',
        channel: 'web',
        category: null,
        tags: [],
        customer,
        assignedUserId: null,
        aiHandled: false,
        aiConfidence: null,
        firstResponseAt: null,
        slaDueAt: new Date(Date.now() + SLA_MINUTES.medium * 60_000).toISOString(),
        slaBreached: false,
        resolvedAt: null,
        satisfaction: null,
        createdAt: nowIso(),
        updatedAt: nowIso(),
      };
      store.tickets.unshift(ticket);

      conversation = {
        id: `con_web_${sessionId}`,
        channel: 'web',
        subject: ticket.subject,
        status: 'open',
        customer,
        assignedUserId: null,
        ticketId: ticket.id,
        aiHandled: false,
        aiTurns: 0,
        lastMessageAt: nowIso(),
        createdAt: nowIso(),
        messages: [],
      };
      store.conversations.unshift(conversation);
    }

    addMessage(conversation, {
      authorType: 'customer',
      authorName: conversation.customer?.name ?? 'You',
      body,
      isPrivate: false,
      meta: { channel: 'web' },
      createdAt: nowIso(),
    });

    // Customers never see articles marked internal.
    const draft = buildDraft(body, false);
    const threshold = store.workspace.settings.aiSuggestThreshold ?? DEFAULT_SUGGEST_THRESHOLD;
    const ticket = store.tickets.find((item) => item.id === conversation!.ticketId);

    if (draft.shouldEscalate || draft.confidence < threshold) {
      conversation.status = 'escalated';
      addMessage(conversation, {
        authorType: 'system',
        authorName: 'System',
        body: 'Escalated to a human agent, because the knowledge base does not cover this.',
        isPrivate: true,
        meta: { reason: 'Below confidence threshold' },
        createdAt: nowIso(),
      });
      if (ticket) ticket.status = 'open';
      return { conversation, reply: null as Message | null };
    }

    const reply = addMessage(conversation, {
      authorType: 'ai',
      authorName: 'AI Assistant',
      body: draft.text,
      isPrivate: false,
      meta: { confidence: draft.confidence, engine: draft.engine, citations: draft.citations },
      createdAt: nowIso(),
    });
    conversation.aiHandled = true;
    conversation.aiTurns += 1;
    if (ticket) {
      ticket.aiHandled = true;
      ticket.aiConfidence = draft.confidence;
      ticket.firstResponseAt ??= nowIso();
      if (ticket.status === 'new') ticket.status = 'pending';
    }
    return { conversation, reply };
  }

  function computeAnalytics(rangeDays: number): AnalyticsSummary {
    const now = Date.now();
    const windowStart = now - rangeDays * 86_400_000;
    const previousStart = windowStart - rangeDays * 86_400_000;
    const at = (value?: string | null) => (value ? new Date(value).getTime() : 0);

    const current = store.tickets.filter((ticket) => at(ticket.createdAt) >= windowStart);
    const previous = store.tickets.filter(
      (ticket) => at(ticket.createdAt) >= previousStart && at(ticket.createdAt) < windowStart,
    );
    const openStates = new Set(['new', 'open', 'pending', 'on_hold']);
    const openNow = store.tickets.filter((ticket) => openStates.has(ticket.status));
    const openThen = store.tickets.filter(
      (ticket) =>
        at(ticket.createdAt) <= windowStart &&
        (!ticket.resolvedAt || at(ticket.resolvedAt) > windowStart),
    ).length;

    const atRisk = openNow.filter(
      (ticket) =>
        ticket.slaDueAt && !ticket.firstResponseAt && at(ticket.slaDueAt) <= now + 2 * 3_600_000,
    );

    const deflection = (rows: Ticket[]) => {
      if (!rows.length) return 0;
      const handled = rows.filter(
        (ticket) => ticket.aiHandled && (ticket.status === 'solved' || ticket.status === 'closed'),
      ).length;
      return Number(((handled / rows.length) * 100).toFixed(1));
    };
    const csat = (rows: Ticket[]) => {
      const rated = rows.map((ticket) => ticket.satisfaction).filter((n): n is number => Boolean(n));
      if (!rated.length) return 0;
      return Number((((rated.reduce((a, b) => a + b, 0) / rated.length) / 5) * 100).toFixed(1));
    };
    const change = (a: number, b: number) =>
      b === 0 ? (a === 0 ? 0 : 100) : Number((((a - b) / b) * 100).toFixed(1));

    const created = new Map<string, number>();
    const resolved = new Map<string, number>();
    for (const ticket of store.tickets) {
      if (at(ticket.createdAt) >= windowStart) {
        const key = ticket.createdAt.slice(0, 10);
        created.set(key, (created.get(key) ?? 0) + 1);
      }
      if (ticket.resolvedAt && at(ticket.resolvedAt) >= windowStart) {
        const key = ticket.resolvedAt.slice(0, 10);
        resolved.set(key, (resolved.get(key) ?? 0) + 1);
      }
    }
    const series: MetricPoint[] = Array.from({ length: rangeDays + 1 }, (_, offset) => {
      const date = new Date(windowStart + offset * 86_400_000).toISOString().slice(0, 10);
      return { date, created: created.get(date) ?? 0, resolved: resolved.get(date) ?? 0 };
    });

    const mix = (rows: Ticket[], key: (ticket: Ticket) => string): MixEntry[] => {
      const counts = new Map<string, number>();
      for (const ticket of rows) {
        const label = key(ticket);
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
      const total = rows.length || 1;
      return [...counts.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([label, value]) => ({
          label,
          value,
          share: Number(((value / total) * 100).toFixed(1)),
        }));
    };

    const median = (values: number[]) => {
      if (!values.length) return null;
      const sorted = [...values].sort((a, b) => a - b);
      const middle = Math.floor(sorted.length / 2);
      const value =
        sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
      return Number(value.toFixed(1));
    };

    const responseMinutes = (rows: Ticket[]) =>
      rows
        .filter((ticket) => ticket.firstResponseAt)
        .map((ticket) => (at(ticket.firstResponseAt) - at(ticket.createdAt)) / 60_000)
        .filter((minutes) => minutes >= 0);

    const leaderboard: LeaderboardRow[] = store.users
      .map((user) => {
        const owned = current.filter((ticket) => ticket.assignedUserId === user.id);
        const rated = owned.map((t) => t.satisfaction).filter((n): n is number => Boolean(n));
        return {
          userId: user.id,
          name: user.name,
          solved: owned.filter((ticket) => ticket.status === 'solved' || ticket.status === 'closed')
            .length,
          medianFirstResponseMinutes: median(responseMinutes(owned)),
          csat: rated.length
            ? Number((((rated.reduce((a, b) => a + b, 0) / rated.length) / 5) * 100).toFixed(1))
            : null,
        };
      })
      .filter((row) => row.solved > 0)
      .sort((a, b) => b.solved - a.solved)
      .slice(0, 8);

    return {
      rangeDays,
      openTickets: openNow.length,
      openDelta: change(openNow.length, openThen),
      slaAtRisk: atRisk.length,
      aiDeflection: deflection(current),
      aiDeflectionDelta: Number((deflection(current) - deflection(previous)).toFixed(1)),
      csat: csat(current),
      csatDelta: Number((csat(current) - csat(previous)).toFixed(1)),
      medianFirstResponseMinutes: median(responseMinutes(current)),
      series,
      channelMix: mix(current, (ticket) => ticket.channel),
      priorityMix: mix(current, (ticket) => ticket.priority),
      openPriorityMix: mix(openNow, (ticket) => ticket.priority),
      topCategories: mix(current, (ticket) => ticket.category ?? 'Uncategorised').slice(0, 6),
      agentLeaderboard: leaderboard,
    };
  }

  return {
    mode: 'demo',

    async login(email) {
      const user = store.users.find(
        (candidate) => candidate.email.toLowerCase() === email.toLowerCase(),
      );
      store.currentUser = user ?? store.users[0];
      return delay(session());
    },
    async register(input) {
      store.currentUser = { ...store.users[0], name: input.name, email: input.email };
      return delay(session(store.currentUser));
    },
    async restore() {
      return delay(session());
    },
    async rotateApiKey() {
      return delay(`sk_demo_${newId()}`);
    },

    async listConversations(filters: ConversationFilters = {}) {
      let rows = [...store.conversations];
      if (filters.status) rows = rows.filter((row) => row.status === filters.status);
      if (filters.channel) rows = rows.filter((row) => row.channel === filters.channel);
      if (filters.assigned === 'me') {
        rows = rows.filter((row) => row.assignedUserId === store.currentUser.id);
      }
      if (filters.search) {
        const needle = filters.search.toLowerCase();
        rows = rows.filter(
          (row) =>
            (row.subject ?? '').toLowerCase().includes(needle) ||
            (row.customer?.name ?? '').toLowerCase().includes(needle) ||
            row.messages.some((message) => message.body.toLowerCase().includes(needle)),
        );
      }
      return delay(clone(rows));
    },
    async getConversation(id) {
      return delay(clone(findConversation(id)));
    },
    async updateConversation(id, patch) {
      const conversation = findConversation(id);
      Object.assign(conversation, patch);
      if (patch.status === 'resolved' && conversation.ticketId) {
        const ticket = store.tickets.find((item) => item.id === conversation.ticketId);
        if (ticket && ticket.status !== 'solved') {
          ticket.status = 'solved';
          ticket.resolvedAt = nowIso();
        }
      }
      return delay(clone(conversation));
    },
    async sendMessage(conversationId, input) {
      const conversation = findConversation(conversationId);
      const message = addMessage(conversation, {
        authorType: 'agent',
        authorName: store.currentUser.name,
        body: input.body,
        isPrivate: input.isPrivate ?? false,
        meta: { delivered: true },
        createdAt: nowIso(),
      });
      if (!input.isPrivate) {
        conversation.assignedUserId ??= store.currentUser.id;
        if (conversation.status === 'escalated') conversation.status = 'open';
        const ticket = store.tickets.find((item) => item.id === conversation.ticketId);
        if (ticket) {
          ticket.firstResponseAt ??= nowIso();
          ticket.assignedUserId ??= store.currentUser.id;
          if (ticket.status === 'new') ticket.status = 'open';
        }
      }
      return delay(clone(message));
    },
    async draftReply(conversationId) {
      const conversation = findConversation(conversationId);
      const latest = [...conversation.messages]
        .reverse()
        .find((message) => message.authorType === 'customer' && !message.isPrivate);
      return delay(buildDraft(latest?.body ?? conversation.subject ?? '', true), 320);
    },
    async askAssistant(question) {
      return delay(buildDraft(question, true), 320);
    },
    async inboxStats(): Promise<InboxStats> {
      const rows = store.conversations;
      return delay({
        open: rows.filter((row) => row.status === 'open').length,
        escalated: rows.filter((row) => row.status === 'escalated').length,
        pending: rows.filter((row) => row.status === 'pending').length,
        mine: rows.filter((row) => row.assignedUserId === store.currentUser.id).length,
        unassigned: rows.filter((row) => !row.assignedUserId && row.status !== 'resolved').length,
      });
    },

    async listTickets(filters: TicketFilters = {}) {
      let rows = [...store.tickets];
      if (filters.status?.length) rows = rows.filter((row) => filters.status!.includes(row.status));
      if (filters.priority?.length) {
        rows = rows.filter((row) => filters.priority!.includes(row.priority));
      }
      if (filters.channel) rows = rows.filter((row) => row.channel === filters.channel);
      if (filters.assigned === 'me') {
        rows = rows.filter((row) => row.assignedUserId === store.currentUser.id);
      } else if (filters.assigned === 'unassigned') {
        rows = rows.filter((row) => !row.assignedUserId);
      }
      if (filters.search) {
        const needle = filters.search.toLowerCase();
        rows = rows.filter(
          (row) =>
            row.subject.toLowerCase().includes(needle) ||
            String(row.number).includes(needle) ||
            (row.customer?.name ?? '').toLowerCase().includes(needle) ||
            (row.customer?.email ?? '').toLowerCase().includes(needle),
        );
      }
      return delay(clone(rows.slice(0, 200)));
    },
    async createTicket(input: NewTicket) {
      const number = Math.max(0, ...store.tickets.map((ticket) => ticket.number)) + 1;
      const priority = (input.priority ?? 'medium') as Priority;
      const ticket: Ticket = {
        id: newId(),
        number,
        subject: input.subject,
        description: input.description ?? '',
        status: 'new',
        priority,
        channel: input.channel ?? 'web',
        category: input.category ?? null,
        tags: input.tags ?? [],
        customer:
          store.customers.find((customer) => customer.id === input.customerId) ??
          store.customers.find((customer) => customer.email === input.customerEmail) ??
          null,
        assignedUserId: input.assignedUserId ?? null,
        aiHandled: false,
        aiConfidence: null,
        firstResponseAt: null,
        slaDueAt: new Date(Date.now() + SLA_MINUTES[priority] * 60_000).toISOString(),
        slaBreached: false,
        resolvedAt: null,
        satisfaction: null,
        createdAt: nowIso(),
        updatedAt: nowIso(),
      };
      store.tickets.unshift(ticket);
      return delay(clone(ticket));
    },
    async updateTicket(id, patch) {
      const ticket = store.tickets.find((item) => item.id === id);
      if (!ticket) throw new ApiError('Ticket not found', 404);
      Object.assign(ticket, patch, { updatedAt: nowIso() });
      if (patch.status === 'solved' || patch.status === 'closed') {
        ticket.resolvedAt ??= nowIso();
      } else if (patch.status) {
        ticket.resolvedAt = null;
      }
      return delay(clone(ticket));
    },

    async listCustomers(search) {
      let rows = [...store.customers];
      if (search) {
        const needle = search.toLowerCase();
        rows = rows.filter((row) =>
          [row.name, row.email, row.company].some((field) =>
            (field ?? '').toLowerCase().includes(needle),
          ),
        );
      }
      return delay(clone(rows));
    },
    async customerTickets(id) {
      return delay(clone(store.tickets.filter((ticket) => ticket.customer?.id === id)));
    },

    async listArticles() {
      return delay(clone(store.articles));
    },
    async createArticle(input) {
      const article: Article = {
        id: newId(),
        title: input.title,
        body: input.body ?? '',
        summary: input.summary ?? null,
        category: input.category ?? 'General',
        tags: input.tags ?? [],
        status: input.status ?? 'draft',
        visibility: input.visibility ?? 'public',
        version: 1,
        authorName: store.currentUser.name,
        createdAt: nowIso(),
        updatedAt: nowIso(),
      };
      store.articles.unshift(article);
      return delay(clone(article));
    },
    async updateArticle(id, patch) {
      const article = store.articles.find((item) => item.id === id);
      if (!article) throw new ApiError('Article not found', 404);
      const contentChanged = ['title', 'body', 'summary'].some((key) => key in patch);
      Object.assign(article, patch, { updatedAt: nowIso() });
      if (contentChanged) article.version += 1;
      return delay(clone(article));
    },
    async deleteArticle(id) {
      const index = store.articles.findIndex((item) => item.id === id);
      if (index >= 0) store.articles.splice(index, 1);
      return delay(undefined);
    },
    async searchKnowledge(query) {
      const hits = searchArticles(store.articles, query, { limit: 8 });
      return delay(
        hits.map((hit) => ({
          articleId: hit.article.id,
          title: hit.article.title,
          excerpt: excerpt(hit.article, query),
          category: hit.article.category,
          score: hit.score,
        })),
      );
    },

    async analytics(rangeDays) {
      return delay(computeAnalytics(rangeDays), 140);
    },
    async workload(): Promise<Workload> {
      const active = store.conversations.filter((row) => row.status !== 'resolved');
      const counts = new Map<string, number>();
      for (const row of active) counts.set(row.channel, (counts.get(row.channel) ?? 0) + 1);
      return delay({
        openConversations: store.conversations.filter((row) => row.status === 'open').length,
        escalated: store.conversations.filter((row) => row.status === 'escalated').length,
        unassigned: active.filter((row) => !row.assignedUserId).length,
        byChannel: [...counts.entries()]
          .sort((a, b) => b[1] - a[1])
          .map(([label, value]) => ({ label, value })),
      });
    },

    async getWorkspace() {
      return delay(clone(store.workspace));
    },
    async updateWorkspace(patch) {
      if (patch.name) store.workspace.name = patch.name;
      if (patch.settings) {
        store.workspace.settings = { ...store.workspace.settings, ...patch.settings };
      }
      return delay(clone(store.workspace));
    },
    async uploadAttachment(): Promise<never> {
      throw new ApiError(
        'Demo mode runs entirely in your browser, so there is nowhere to keep a file. Start the backend to send attachments.',
        400,
      );
    },
    async portalUpload(): Promise<never> {
      throw new ApiError(
        'Demo mode runs entirely in your browser, so there is nowhere to keep a file.',
        400,
      );
    },
    async getAiConfig() {
      return delay({
        provider: 'none' as const,
        model: '',
        defaultModel: '',
        baseUrl: '',
        embeddingModel: '',
        hasKey: false,
        managedByEnv: false,
        encryptionAvailable: false,
        active: false,
      });
    },
    async saveAiConfig() {
      throw new ApiError(
        'Demo mode runs entirely in your browser, so there is nowhere safe to keep a key. Start the backend to connect a model.',
        400,
      );
    },
    async testAiConfig() {
      return delay({ ok: false, detail: 'Demo mode has no backend to call a provider from.' });
    },
    async getAutopilot() {
      return delay({
        enabled: false,
        hours: [] as number[],
        runningNow: false,
        confidenceThreshold: 0.4,
        modelConnected: false,
        maxPerRun: 25,
      });
    },
    async runAutopilot(): Promise<never> {
      throw new ApiError('Demo mode has no backend to work a queue with.', 400);
    },
    async resetWorkspace(): Promise<never> {
      throw new ApiError('Demo mode keeps nothing, so there is nothing to clear.', 400);
    },
    async listDatasets() {
      return delay({ datasets: [] as { name: string; url: string; description: string }[] });
    },
    datasetUrl() {
      return '';
    },
    async getBackupStatus() {
      return delay({
        supported: false,
        directory: '',
        intervalHours: 0,
        keep: 0,
        snapshots: [],
      });
    },
    async createBackup(): Promise<{ name: string; snapshots: never[] }> {
      throw new ApiError('Demo mode keeps nothing, so there is nothing to snapshot.', 400);
    },
    async restoreAttachmentArchive(): Promise<never> {
      throw new ApiError('Demo mode keeps nothing, so there is nothing to put back.', 400);
    },
    exportWorkspaceUrl() {
      return '';
    },
    async listTeam() {
      return delay(clone(store.users));
    },
    async addTeamMember(input) {
      const member: User = {
        id: `user_${store.users.length + 1}`,
        name: input.name,
        email: input.email,
        role: input.role,
        isActive: true,
      };
      store.users.push(member);
      return delay(clone(member));
    },
    async updateTeamMember(id, patch) {
      const member = store.users.find((item) => item.id === id);
      if (!member) throw new Error('Team member not found');
      Object.assign(member, patch);
      return delay(clone(member));
    },
    async listMacros() {
      return delay(clone(store.macros));
    },
    async saveMacro(input) {
      if (input.id) {
        const macro = store.macros.find((item) => item.id === input.id);
        if (!macro) throw new ApiError('Macro not found', 404);
        Object.assign(macro, input, { updatedAt: nowIso() });
        return delay(clone(macro));
      }
      const macro: Macro = {
        id: newId(),
        name: input.name,
        body: input.body,
        tags: input.tags ?? [],
        updatedAt: nowIso(),
      };
      store.macros.unshift(macro);
      return delay(clone(macro));
    },
    async deleteMacro(id) {
      const index = store.macros.findIndex((item) => item.id === id);
      if (index >= 0) store.macros.splice(index, 1);
      return delay(undefined);
    },
    async listSlaPolicies() {
      return delay(clone(store.slaPolicies));
    },
    async listRoutingRules() {
      return delay(clone(store.routingRules));
    },
    async listChannels() {
      return delay(clone(connections));
    },
    async channelCatalog() {
      return delay(clone(CHANNEL_CATALOG));
    },
    async saveChannel(channel, input) {
      const connection = connections.find((item) => item.channel === channel);
      if (!connection) throw new ApiError('Unknown channel', 404);
      const config = input.config ?? {};
      const provided = Object.entries(config)
        .filter(([, value]) => value)
        .map(([key]) => key);
      connection.configuredKeys = [...new Set([...connection.configuredKeys, ...provided])];
      const required =
        CHANNEL_CATALOG.find((entry) => entry.channel === channel)?.requiredKeys ?? [];
      connection.missingKeys = required.filter((key) => !connection.configuredKeys.includes(key));
      if (input.isActive && connection.missingKeys.length) {
        throw new ApiError(
          `Cannot activate ${channel}: missing ${connection.missingKeys.join(', ')}`,
          422,
        );
      }
      connection.isActive = input.isActive;
      if (input.displayName) connection.displayName = input.displayName;
      return delay(clone(connection));
    },

    async listTapSessions() {
      return delay(clone(store.tapSessions));
    },
    async startTapSession(customerLabel) {
      const tapSession: TapSession = {
        id: newId(),
        status: 'live',
        customerLabel,
        conversationId: null,
        transcript: [],
        suggestions: [],
        summary: null,
        createdAt: nowIso(),
        endedAt: null,
      };
      store.tapSessions.unshift(tapSession);
      return delay(clone(tapSession));
    },
    async addUtterance(sessionId, input) {
      const tapSession = store.tapSessions.find((item) => item.id === sessionId);
      if (!tapSession) throw new ApiError('Session not found', 404);

      tapSession.transcript.push({
        id: newId(),
        speaker: input.speaker,
        text: input.text,
        at: nowIso(),
      });

      // Only customer turns of real substance are worth interrupting for.
      if (input.speaker === 'customer' && input.text.trim().length >= 12) {
        const window = tapSession.transcript
          .slice(-4)
          .map((line) => line.text)
          .join(' ');
        const hits = searchArticles(
          store.articles,
          `${input.text} ${input.text} ${window}`,
          { limit: 3 },
        );
        const confidence = Number(Math.min(0.3 + (hits[0]?.coverage ?? 0) * 0.6, 0.95).toFixed(2));
        const suggestions: TapSuggestion[] = hits.slice(0, 2).map((hit) => ({
          id: newId(),
          kind: 'answer',
          text: `${hit.article.title}. ${excerpt(hit.article, input.text, 180)}`,
          confidence,
          citations: citationsFor(input.text, [hit]),
          engine: 'grounded-fallback',
          at: nowIso(),
        }));

        const lowered = input.text.toLowerCase();
        if (ESCALATION_PHRASES.some((phrase) => lowered.includes(phrase))) {
          suggestions.unshift({
            id: newId(),
            kind: 'warning',
            text: 'The caller is asking to escalate, so offer a supervisor callback.',
            confidence: 0.8,
            citations: [],
            engine: 'grounded-fallback',
            at: nowIso(),
          });
        }
        tapSession.suggestions.push(...suggestions);
      }
      return delay(clone(tapSession), 260);
    },
    async endTapSession(sessionId) {
      const tapSession = store.tapSessions.find((item) => item.id === sessionId);
      if (!tapSession) throw new ApiError('Session not found', 404);
      tapSession.status = 'ended';
      tapSession.endedAt = nowIso();
      const opening = tapSession.transcript.find((line) => line.speaker === 'customer');
      tapSession.summary =
        tapSession.summary ??
        (opening
          ? `Call summary unavailable (no AI provider). Opening request: ${opening.text.slice(0, 280)}`
          : null);
      return delay(clone(tapSession));
    },

    async portalConfig(): Promise<PortalConfig> {
      return delay({
        publicKey: store.workspace.publicKey,
        workspaceName: store.workspace.name,
        accentColor: store.workspace.accentColor,
        greeting: store.workspace.settings.greeting,
        logoUrl: store.workspace.logoUrl ?? null,
        aiEnabled: false,
      });
    },
    async portalSend(input) {
      const sessionId = input.sessionId ?? `web_${newId()}`;
      const { conversation, reply } = ingestCustomerMessage(
        sessionId,
        input.body,
        input.name,
        input.email,
      );
      return delay(
        {
          sessionId,
          conversationId: conversation.id,
          reply: reply ? clone(reply) : null,
          escalated: conversation.status === 'escalated',
        },
        420,
      );
    },
    async portalHistory(_publicKey, sessionId) {
      const conversation = store.conversations.find((item) => item.id === `con_web_${sessionId}`);
      return delay(clone(conversation?.messages.filter((message) => !message.isPrivate) ?? []));
    },
  };
}

function deriveSubject(body: string, limit = 80): string {
  const flat = body.split(/\s+/).join(' ');
  if (!flat) return 'New conversation';
  for (const terminator of ['. ', '? ', '! ']) {
    const index = flat.indexOf(terminator);
    if (index > 0 && index <= limit) return flat.slice(0, index + 1).trim();
  }
  return flat.length > limit ? `${flat.slice(0, limit)}...` : flat;
}

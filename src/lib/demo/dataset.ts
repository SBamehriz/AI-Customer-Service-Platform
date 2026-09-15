/** Builds the demo dataset in memory from fixtures/demo.json. */

import fixture from '../../../fixtures/demo.json';
import type {
  Article,
  Conversation,
  Customer,
  Macro,
  Message,
  Priority,
  RoutingRule,
  SlaPolicy,
  TapSession,
  Ticket,
  User,
  Workspace,
  WorkspaceSettings,
  Channel,
  ConversationStatus,
  TicketStatus,
} from '../types';

/** The same seeded generator the backend uses, so the demo data is identical every load. */
class Rng {
  private state: number;

  constructor(seed = 20240917) {
    this.state = seed;
  }

  next(): number {
    this.state = (this.state * 1103515245 + 12345) % 2147483648;
    return this.state / 2147483648;
  }

  below(upper: number): number {
    return Math.floor(this.next() * upper);
  }

  between(low: number, high: number): number {
    return low + this.below(high - low + 1);
  }

  pick<T>(items: T[]): T {
    return items[this.below(items.length)];
  }

  weighted<T>(items: T[], weights: number[]): T {
    const total = weights.reduce((sum, value) => sum + value, 0);
    let target = this.next() * total;
    for (let index = 0; index < items.length; index += 1) {
      target -= weights[index];
      if (target <= 0) return items[index];
    }
    return items[items.length - 1];
  }
}

let counter = 0;
export const newId = (): string => {
  counter += 1;
  return `d${counter.toString(36).padStart(6, '0')}${Math.floor(Math.random() * 1e6).toString(36)}`;
};

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

const iso = (time: number): string => new Date(time).toISOString();

const SLA_MINUTES: Record<Priority, number> = {
  urgent: 15,
  high: 60,
  medium: 240,
  low: 240,
};

/** The fixture's shape. */
interface FixtureMessage {
  author: 'customer' | 'agent' | 'ai' | 'system';
  hoursAgo: number;
  body: string;
  name?: string;
  private?: boolean;
  confidence?: number;
  cites?: string[];
}

interface FixtureConversation {
  customer: string;
  channel: string;
  subject: string;
  status: string;
  assignee: string | null;
  priority?: string;
  category?: string;
  tags?: string[];
  startedHoursAgo: number;
  messages: FixtureMessage[];
}

interface Fixture {
  workspace: {
    name: string;
    slug: string;
    accentColor: string;
    settings: WorkspaceSettings;
  };
  users: { key: string; name: string; email: string; role: string; password: string }[];
  customers: {
    key: string;
    name: string;
    email: string;
    phone: string;
    company: string;
    channelIds: Record<string, string>;
  }[];
  articles: {
    key: string;
    title: string;
    category: string;
    status: string;
    visibility?: string;
    summary: string;
    tags: string[];
    body: string;
  }[];
  macros: { name: string; tags: string[]; body: string }[];
  slaPolicies: {
    name: string;
    priorities: string[];
    firstResponseMinutes: number;
    resolutionMinutes: number;
    isActive: boolean;
  }[];
  routingRules: {
    name: string;
    orderIndex: number;
    isActive: boolean;
    conditions: Record<string, unknown>;
    actions: Record<string, unknown>;
  }[];
  conversations: FixtureConversation[];
  tapSessions: {
    customerLabel: string;
    status: string;
    startedHoursAgo: number;
    durationMinutes: number;
    summary: string;
    transcript: { speaker: string; text: string }[];
    suggestions: { kind: string; text: string; confidence: number; cites: string[] }[];
  }[];
  historicalTickets: {
    days: number;
    perDayMin: number;
    perDayMax: number;
    resolveRate: number;
    aiHandledRate: number;
    ratedRate: number;
    subjects: string[];
    categories: string[];
    channels: string[];
    channelWeights: number[];
    priorities: string[];
    priorityWeights: number[];
  };
}

export interface DemoStore {
  workspace: Workspace;
  users: User[];
  currentUser: User;
  customers: Customer[];
  articles: Article[];
  macros: Macro[];
  slaPolicies: SlaPolicy[];
  routingRules: RoutingRule[];
  conversations: Conversation[];
  tickets: Ticket[];
  tapSessions: TapSession[];
  /** Passwords are in the fixture so the demo login form can be exercised. */
  credentials: Record<string, string>;
}

export function buildDemoStore(): DemoStore {
  const data = fixture as unknown as Fixture;
  const rng = new Rng();
  const now = Date.now();

  const workspace: Workspace = {
    id: 'ws_demo',
    name: data.workspace.name,
    slug: data.workspace.slug,
    accentColor: data.workspace.accentColor,
    logoUrl: null,
    publicKey: 'pk_demo',
    settings: { ...data.workspace.settings },
  };

  const users: User[] = data.users.map((entry, index) => ({
    id: `usr_${index + 1}`,
    name: entry.name,
    email: entry.email,
    role: entry.role as User['role'],
    isActive: true,
  }));
  const userByKey = new Map(data.users.map((entry, index) => [entry.key, users[index]]));
  const credentials = Object.fromEntries(
    data.users.map((entry) => [entry.email.toLowerCase(), entry.password]),
  );

  const customers: Customer[] = data.customers.map((entry, index) => ({
    id: `cus_${index + 1}`,
    name: entry.name,
    email: entry.email,
    phone: entry.phone,
    company: entry.company || null,
    notes: null,
    channelIds: entry.channelIds,
    createdAt: iso(now - rng.between(30, 400) * DAY),
    lastSeenAt: iso(now - rng.between(1, 96) * HOUR),
    totalTickets: 0,
    openTickets: 0,
  }));
  const customerByKey = new Map(data.customers.map((entry, index) => [entry.key, customers[index]]));

  const articles: Article[] = data.articles.map((entry, index) => ({
    id: `art_${index + 1}`,
    title: entry.title,
    body: entry.body,
    summary: entry.summary,
    category: entry.category,
    tags: entry.tags,
    status: entry.status as Article['status'],
    visibility: (entry.visibility ?? 'public') as Article['visibility'],
    version: 1,
    authorName: 'Priya Raman',
    createdAt: iso(now - rng.between(30, 200) * DAY),
    updatedAt: iso(now - rng.between(1, 29) * DAY),
  }));
  const articleByKey = new Map(data.articles.map((entry, index) => [entry.key, articles[index]]));

  const macros: Macro[] = data.macros.map((entry, index) => ({
    id: `mac_${index + 1}`,
    name: entry.name,
    body: entry.body,
    tags: entry.tags,
    updatedAt: iso(now - rng.between(2, 60) * DAY),
  }));

  const slaPolicies: SlaPolicy[] = data.slaPolicies.map((entry, index) => ({
    id: `sla_${index + 1}`,
    name: entry.name,
    priorities: entry.priorities as Priority[],
    firstResponseMinutes: entry.firstResponseMinutes,
    resolutionMinutes: entry.resolutionMinutes,
    isActive: entry.isActive,
  }));

  const routingRules: RoutingRule[] = data.routingRules.map((entry, index) => ({
    id: `rule_${index + 1}`,
    name: entry.name,
    orderIndex: entry.orderIndex,
    isActive: entry.isActive,
    conditions: entry.conditions as Record<string, unknown>,
    actions: entry.actions as Record<string, unknown>,
  }));

  // --- Handwritten threads, each with the ticket it opened -----------------

  const conversations: Conversation[] = [];
  const tickets: Ticket[] = [];
  let ticketNumber = 1;

  for (const entry of data.conversations) {
    const customer = customerByKey.get(entry.customer) ?? null;
    const assignee = entry.assignee ? (userByKey.get(entry.assignee) ?? null) : null;
    const startedAt = now - entry.startedHoursAgo * HOUR;
    const conversationId = `con_${ticketNumber}`;
    const ticketId = `tkt_${ticketNumber}`;

    let aiTurns = 0;
    let firstResponseAt: number | null = null;
    let lastMessageAt = startedAt;

    const messages: Message[] = entry.messages.map((raw, index) => {
      const at = now - raw.hoursAgo * HOUR;
      lastMessageAt = Math.max(lastMessageAt, at);
      if (raw.author === 'ai') aiTurns += 1;
      if ((raw.author === 'ai' || raw.author === 'agent') && !raw.private && firstResponseAt === null) {
        firstResponseAt = at;
      }
      return {
        id: `${conversationId}_m${index}`,
        conversationId,
        authorType: raw.author,
        authorName: raw.name ?? defaultAuthorName(raw.author, customer),
        body: raw.body,
        isPrivate: Boolean(raw.private),
        meta: {
          channel: entry.channel,
          ...(raw.confidence !== undefined
            ? { confidence: raw.confidence, engine: 'demo' }
            : {}),
          ...(raw.cites
            ? {
                citations: raw.cites
                  .map((key) => articleByKey.get(key))
                  .filter((article): article is Article => Boolean(article))
                  .map((article) => ({
                    articleId: article.id,
                    title: article.title,
                    excerpt: (article.summary ?? article.body).slice(0, 200),
                  })),
              }
            : {}),
        },
        createdAt: iso(at),
      };
    });

    const resolved = entry.status === 'resolved';
    conversations.push({
      id: conversationId,
      channel: entry.channel as Channel,
      subject: entry.subject,
      status: entry.status as ConversationStatus,
      customer,
      assignedUserId: assignee?.id ?? null,
      ticketId,
      aiHandled: aiTurns > 0,
      aiTurns,
      lastMessageAt: iso(lastMessageAt),
      createdAt: iso(startedAt),
      messages,
    });

    const priority = (entry.priority ?? 'medium') as Priority;
    const lastConfidence = [...entry.messages]
      .reverse()
      .find((message) => message.confidence !== undefined);

    tickets.push({
      id: ticketId,
      number: ticketNumber,
      subject: entry.subject,
      description: entry.messages.find((message) => message.author === 'customer')?.body ?? '',
      status: resolved ? 'solved' : entry.status === 'pending' ? 'pending' : 'open',
      priority,
      channel: entry.channel as Channel,
      category: entry.category ?? null,
      tags: entry.tags ?? [],
      customer,
      assignedUserId: assignee?.id ?? null,
      aiHandled: aiTurns > 0,
      aiConfidence: lastConfidence?.confidence ?? null,
      firstResponseAt: firstResponseAt ? iso(firstResponseAt) : null,
      slaDueAt: iso(startedAt + SLA_MINUTES[priority] * 60_000),
      slaBreached: false,
      resolvedAt: resolved ? iso(lastMessageAt) : null,
      satisfaction: resolved ? rng.between(4, 5) : null,
      createdAt: iso(startedAt),
      updatedAt: iso(lastMessageAt),
    });
    ticketNumber += 1;
  }

  // --- Backfilled history so the analytics have 90 real days ---------------

  const spec = data.historicalTickets;
  const agents = users.filter((user) => user.role !== 'owner');

  for (let dayOffset = spec.days; dayOffset > 0; dayOffset -= 1) {
    const day = now - dayOffset * DAY;
    const weekday = new Date(day).getDay();
    let volume = rng.between(spec.perDayMin, spec.perDayMax);
    if (weekday === 0 || weekday === 6) volume = Math.max(1, Math.floor(volume / 2));

    for (let index = 0; index < volume; index += 1) {
      const createdAt = day + rng.between(7, 19) * HOUR + rng.below(60) * 60_000;
      const priority = rng.weighted(spec.priorities, spec.priorityWeights) as Priority;
      const channel = rng.weighted(spec.channels, spec.channelWeights) as Channel;
      const agent = agents.length ? rng.pick(agents) : null;
      const aiHandled = rng.next() < spec.aiHandledRate;
      const awaiting = dayOffset <= 7 && rng.next() < 0.22;
      const resolved = awaiting ? false : rng.next() < spec.resolveRate;

      const slaMinutes = SLA_MINUTES[priority];
      const firstResponseAt = awaiting ? null : createdAt + rng.between(2, 180) * 60_000;
      const resolvedAt =
        resolved && firstResponseAt ? firstResponseAt + rng.between(20, 2400) * 60_000 : null;
      const customer = customers.length ? rng.pick(customers) : null;

      const status: TicketStatus = resolved
        ? 'solved'
        : awaiting
          ? 'new'
          : rng.pick<TicketStatus>(['open', 'pending']);

      tickets.push({
        id: `tkt_h${ticketNumber}`,
        number: ticketNumber,
        subject: rng.pick(spec.subjects),
        description: '',
        status,
        priority,
        channel,
        category: rng.pick(spec.categories),
        tags: [],
        customer,
        assignedUserId: agent?.id ?? null,
        aiHandled,
        aiConfidence: aiHandled ? Number((0.5 + rng.next() * 0.45).toFixed(2)) : null,
        firstResponseAt: firstResponseAt ? iso(firstResponseAt) : null,
        slaDueAt: iso(createdAt + slaMinutes * 60_000),
        slaBreached: Boolean(
          firstResponseAt && (firstResponseAt - createdAt) / 60_000 > slaMinutes,
        ),
        resolvedAt: resolvedAt ? iso(resolvedAt) : null,
        satisfaction: resolved && rng.next() < spec.ratedRate ? rng.between(3, 5) : null,
        createdAt: iso(createdAt),
        updatedAt: iso(resolvedAt ?? firstResponseAt ?? createdAt),
      });
      ticketNumber += 1;
    }
  }

  // --- Ticket counts per customer -----------------------------------------

  for (const customer of customers) {
    const owned = tickets.filter((ticket) => ticket.customer?.id === customer.id);
    customer.totalTickets = owned.length;
    customer.openTickets = owned.filter(
      (ticket) => ticket.status !== 'solved' && ticket.status !== 'closed',
    ).length;
  }

  // --- Tap AI sessions -----------------------------------------------------

  const tapSessions: TapSession[] = data.tapSessions.map((entry, sessionIndex) => {
    const startedAt = now - entry.startedHoursAgo * HOUR;
    const step = 45_000;
    return {
      id: `tap_${sessionIndex + 1}`,
      status: entry.status as TapSession['status'],
      customerLabel: entry.customerLabel,
      conversationId: null,
      transcript: entry.transcript.map((line, index) => ({
        id: `tap_${sessionIndex + 1}_t${index}`,
        speaker: line.speaker as 'customer' | 'agent',
        text: line.text,
        at: iso(startedAt + index * step),
      })),
      suggestions: entry.suggestions.map((item, index) => ({
        id: `tap_${sessionIndex + 1}_s${index}`,
        kind: item.kind as TapSession['suggestions'][number]['kind'],
        text: item.text,
        confidence: item.confidence,
        engine: 'demo',
        citations: item.cites
          .map((key) => articleByKey.get(key))
          .filter((article): article is Article => Boolean(article))
          .map((article) => ({
            articleId: article.id,
            title: article.title,
            excerpt: (article.summary ?? article.body).slice(0, 200),
          })),
        at: iso(startedAt + (index + 1) * step),
      })),
      summary: entry.summary,
      createdAt: iso(startedAt),
      endedAt: iso(startedAt + entry.durationMinutes * 60_000),
    };
  });

  conversations.sort(
    (a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime(),
  );
  tickets.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  return {
    workspace,
    users,
    currentUser: users[0],
    customers,
    articles,
    macros,
    slaPolicies,
    routingRules,
    conversations,
    tickets,
    tapSessions,
    credentials,
  };
}

function defaultAuthorName(authorType: string, customer: Customer | null): string {
  if (authorType === 'customer') return customer?.name ?? 'Customer';
  if (authorType === 'ai') return 'AI Assistant';
  if (authorType === 'system') return 'System';
  return 'Agent';
}

export { SLA_MINUTES };

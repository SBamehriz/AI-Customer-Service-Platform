/** The API surface, and its two implementations. */

import type {
  AiConfig,
  AiTestResult,
  AnalyticsSummary,
  Article,
  Attachment,
  AutopilotRun,
  AutopilotStatus,
  BackupSnapshot,
  BackupStatus,
  ArticleStatus,
  ChannelCatalogEntry,
  ChannelConnection,
  Conversation,
  ConversationFilters,
  ConversationStatus,
  Customer,
  Draft,
  HealthReport,
  InboxStats,
  Macro,
  Message,
  PortalConfig,
  Priority,
  Role,
  RoutingRule,
  SearchHit,
  Session,
  SlaPolicy,
  TapSession,
  Ticket,
  TicketFilters,
  TicketStatus,
  User,
  WidgetAttachment,
  Workload,
  Workspace,
  WorkspaceSettings,
} from './types';

export type ApiMode = 'demo' | 'live';

export interface NewTicket {
  subject: string;
  description?: string;
  priority?: Priority;
  channel?: Conversation['channel'];
  category?: string | null;
  tags?: string[];
  customerId?: string | null;
  customerEmail?: string | null;
  customerName?: string | null;
  assignedUserId?: string | null;
}

export interface ApiClient {
  readonly mode: ApiMode;

  // Auth
  login(email: string, password: string): Promise<Session>;
  register(input: {
    workspaceName: string;
    name: string;
    email: string;
    password: string;
  }): Promise<Session>;
  restore(token: string): Promise<Session>;
  rotateApiKey(): Promise<string>;

  // Inbox
  listConversations(filters?: ConversationFilters): Promise<Conversation[]>;
  getConversation(id: string): Promise<Conversation>;
  updateConversation(
    id: string,
    patch: { status?: ConversationStatus; assignedUserId?: string | null },
  ): Promise<Conversation>;
  sendMessage(
    conversationId: string,
    input: { body: string; isPrivate?: boolean; attachmentIds?: string[] },
  ): Promise<Message>;
  /** Upload a file as an agent, before sending the message that carries it. */
  uploadAttachment(file: File): Promise<Attachment>;
  draftReply(conversationId: string): Promise<Draft>;
  askAssistant(question: string): Promise<Draft>;
  inboxStats(): Promise<InboxStats>;

  // Tickets
  listTickets(filters?: TicketFilters): Promise<Ticket[]>;
  createTicket(input: NewTicket): Promise<Ticket>;
  updateTicket(
    id: string,
    patch: Partial<Pick<Ticket, 'status' | 'priority' | 'category' | 'tags' | 'subject'>> & {
      assignedUserId?: string | null;
    },
  ): Promise<Ticket>;

  // Customers
  listCustomers(search?: string): Promise<Customer[]>;
  customerTickets(id: string): Promise<Ticket[]>;

  // Knowledge
  listArticles(): Promise<Article[]>;
  createArticle(input: Partial<Article> & { title: string }): Promise<Article>;
  updateArticle(id: string, patch: Partial<Article>): Promise<Article>;
  deleteArticle(id: string): Promise<void>;
  searchKnowledge(query: string): Promise<SearchHit[]>;

  // Analytics
  analytics(rangeDays: number): Promise<AnalyticsSummary>;
  workload(): Promise<Workload>;

  // Workspace
  getWorkspace(): Promise<Workspace>;
  updateWorkspace(patch: {
    name?: string;
    settings?: Partial<WorkspaceSettings>;
  }): Promise<Workspace>;
  getAiConfig(): Promise<AiConfig>;
  saveAiConfig(input: {
    provider: AiConfig['provider'];
    model?: string;
    baseUrl?: string;
    embeddingModel?: string;
    apiKey?: string;
  }): Promise<AiConfig>;
  testAiConfig(): Promise<AiTestResult>;
  getAutopilot(): Promise<AutopilotStatus>;
  runAutopilot(): Promise<AutopilotRun>;
  resetWorkspace(input: { confirm: string; keepTeam?: boolean }): Promise<{ ok: boolean }>;
  listDatasets(): Promise<{ datasets: { name: string; url: string; description: string }[] }>;
  datasetUrl(name: string): string;
  getBackupStatus(): Promise<BackupStatus>;
  createBackup(): Promise<{ name: string; snapshots: BackupSnapshot[] }>;
  /** Put the files from a reset archive back on disk. */
  restoreAttachmentArchive(name: string): Promise<{ name: string; restored: number }>;
  exportWorkspaceUrl(): string;
  listTeam(): Promise<User[]>;
  addTeamMember(input: {
    name: string;
    email: string;
    password: string;
    role: Role;
  }): Promise<User>;
  updateTeamMember(
    id: string,
    patch: { name?: string; role?: Role; isActive?: boolean },
  ): Promise<User>;
  listMacros(): Promise<Macro[]>;
  saveMacro(input: { id?: string; name: string; body: string; tags?: string[] }): Promise<Macro>;
  deleteMacro(id: string): Promise<void>;
  listSlaPolicies(): Promise<SlaPolicy[]>;
  listRoutingRules(): Promise<RoutingRule[]>;
  listChannels(): Promise<ChannelConnection[]>;
  channelCatalog(): Promise<ChannelCatalogEntry[]>;
  saveChannel(
    channel: string,
    input: { displayName?: string; isActive: boolean; config?: Record<string, string> },
  ): Promise<ChannelConnection>;

  // Tap AI
  listTapSessions(): Promise<TapSession[]>;
  startTapSession(customerLabel: string): Promise<TapSession>;
  addUtterance(
    sessionId: string,
    input: { speaker: 'customer' | 'agent'; text: string },
  ): Promise<TapSession>;
  endTapSession(sessionId: string): Promise<TapSession>;

  portalConfig(publicKey?: string): Promise<PortalConfig>;
  portalSend(input: {
    publicKey: string;
    sessionId?: string;
    body: string;
    name?: string;
    email?: string;
    attachmentIds?: string[];
  }): Promise<{ sessionId: string; conversationId: string; reply: Message | null; escalated: boolean }>;
  portalHistory(publicKey: string, sessionId: string): Promise<Message[]>;
  /** Upload a file as a customer, from the hosted portal or the widget. */
  portalUpload(publicKey: string, file: File, sessionId?: string): Promise<WidgetAttachment>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Base URL of the backend. Empty string means the same origin. */
export const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? '';

/** Probe `/health` to decide whether a backend is reachable. */
export async function probeBackend(timeoutMs = 1500): Promise<HealthReport | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
    if (!response.ok) return null;
    return (await response.json()) as HealthReport;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}


type QueryValue = string | number | boolean | string[] | undefined | null;

function toQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) value.forEach((item) => search.append(key, item));
    else search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

export function createHttpClient(getToken: () => string | null): ApiClient {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = getToken();
    const headers = new Headers(init.headers);
    if (init.body) headers.set('Content-Type', 'application/json');
    if (token) headers.set('Authorization', `Bearer ${token}`);

    const response = await fetch(`${API_BASE_URL}/api/v1${path}`, { ...init, headers });
    if (response.status === 204) return undefined as T;

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = (payload as { detail?: unknown })?.detail;
      throw new ApiError(
        typeof detail === 'string' ? detail : `Request failed (${response.status})`,
        response.status,
        detail,
      );
    }
    return payload as T;
  }

  /** Send one file as multipart form data. */
  async function upload<T>(path: string, file: File, fields?: Record<string, string>): Promise<T> {
    const form = new FormData();
    form.append('file', file);
    for (const [name, value] of Object.entries(fields ?? {})) form.append(name, value);
    const token = getToken();
    const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      method: 'POST',
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = (payload as { detail?: unknown })?.detail;
      throw new ApiError(
        typeof detail === 'string' ? detail : 'That file could not be uploaded',
        response.status,
      );
    }
    return payload as T;
  }

  const post = <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
  const patch = <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });

  return {
    mode: 'live',

    login: (email, password) => post<Session>('/auth/login', { email, password }),
    register: (input) => post<Session>('/auth/register', input),
    async restore(token) {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new ApiError('Session expired', response.status);
      return (await response.json()) as Session;
    },
    async rotateApiKey() {
      const { apiKey } = await post<{ apiKey: string }>('/auth/api-key');
      return apiKey;
    },

    listConversations: (filters = {}) =>
      request(`/conversations${toQuery({ ...filters })}`),
    getConversation: (id) => request(`/conversations/${id}`),
    updateConversation: (id, body) => patch(`/conversations/${id}`, body),
    sendMessage: (conversationId, input) =>
      post(`/conversations/${conversationId}/messages`, input),
    uploadAttachment: (file) => upload<Attachment>('/attachments', file),
    portalUpload: (publicKey, file, sessionId) =>
      upload<WidgetAttachment>(
        `/widget/${publicKey}/attachments`,
        file,
        sessionId ? { sessionId } : undefined,
      ),
    draftReply: (conversationId) => post(`/conversations/${conversationId}/draft`),
    askAssistant: (question) => post('/conversations/draft', { question }),
    inboxStats: () => request('/conversations/stats/overview'),

    listTickets: (filters = {}) => request(`/tickets${toQuery({ ...filters })}`),
    createTicket: (input) => post('/tickets', input),
    updateTicket: (id, body) => patch(`/tickets/${id}`, body),

    listCustomers: (search) => request(`/customers${toQuery({ search })}`),
    customerTickets: (id) => request(`/customers/${id}/tickets`),

    listArticles: () => request('/knowledge'),
    createArticle: (input) => post('/knowledge', input),
    updateArticle: (id, body) => patch(`/knowledge/${id}`, body),
    deleteArticle: (id) => request(`/knowledge/${id}`, { method: 'DELETE' }),
    searchKnowledge: (query) => request(`/knowledge/search${toQuery({ q: query })}`),

    analytics: (rangeDays) => request(`/analytics/summary${toQuery({ rangeDays })}`),
    workload: () => request('/analytics/workload'),

    getWorkspace: () => request('/workspace'),
    updateWorkspace: (body) => patch('/workspace', body),
    getAiConfig: () => request<AiConfig>('/workspace/ai'),
    saveAiConfig: (input) =>
      request<AiConfig>('/workspace/ai', { method: 'PUT', body: JSON.stringify(input) }),
    testAiConfig: () => post<AiTestResult>('/workspace/ai/test'),
    getAutopilot: () => request<AutopilotStatus>('/workspace/autopilot'),
    runAutopilot: () => post<AutopilotRun>('/workspace/autopilot/run'),
    resetWorkspace: (input) => post('/workspace/reset', input),
    listDatasets: () => request('/workspace/datasets'),
    datasetUrl: (name) => `${API_BASE_URL}/api/v1/workspace/datasets/${name}.csv`,
    getBackupStatus: () => request<BackupStatus>('/workspace/backups'),
    createBackup: () => post('/workspace/backups'),
    restoreAttachmentArchive: (name) =>
      post(`/workspace/backups/attachments/${encodeURIComponent(name)}/restore`),
    exportWorkspaceUrl: () => `${API_BASE_URL}/api/v1/workspace/export`,
    listTeam: () => request('/workspace/team'),
    addTeamMember: (input) => post<User>('/workspace/team', input),
    updateTeamMember: (id, body) => patch<User>(`/workspace/team/${id}`, body),
    listMacros: () => request('/workspace/macros'),
    saveMacro: ({ id, ...body }) =>
      id ? patch(`/workspace/macros/${id}`, body) : post('/workspace/macros', body),
    deleteMacro: (id) => request(`/workspace/macros/${id}`, { method: 'DELETE' }),
    listSlaPolicies: () => request('/workspace/sla'),
    listRoutingRules: () => request('/workspace/routing'),
    listChannels: () => request('/workspace/channels'),
    channelCatalog: () => request('/workspace/channels/catalog'),
    saveChannel: (channel, body) =>
      request(`/workspace/channels/${channel}`, { method: 'PUT', body: JSON.stringify(body) }),

    listTapSessions: () => request('/tap/sessions'),
    startTapSession: (customerLabel) => post('/tap/sessions', { customerLabel }),
    addUtterance: (sessionId, input) => post(`/tap/sessions/${sessionId}/utterances`, input),
    endTapSession: (sessionId) => post(`/tap/sessions/${sessionId}/end`),

    async portalConfig(publicKey = 'default') {
      const response = await fetch(`${API_BASE_URL}/api/v1/widget/${publicKey}/config`);
      if (!response.ok) throw new ApiError('No workspace found for this portal', response.status);
      return response.json();
    },
    async portalSend({ publicKey, ...body }) {
      const response = await fetch(`${API_BASE_URL}/api/v1/widget/${publicKey}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new ApiError('Could not send message', response.status);
      return response.json();
    },
    async portalHistory(publicKey, sessionId) {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/widget/${publicKey}/sessions/${sessionId}`,
      );
      if (!response.ok) return [];
      return response.json();
    },
  };
}

export type { ArticleStatus, TicketStatus };

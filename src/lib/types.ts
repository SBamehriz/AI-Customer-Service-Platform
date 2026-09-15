/** API types. */

export type Channel = 'web' | 'email' | 'whatsapp' | 'instagram' | 'sms' | 'voice' | 'api';
export type TicketStatus = 'new' | 'open' | 'pending' | 'on_hold' | 'solved' | 'closed';
export type Priority = 'low' | 'medium' | 'high' | 'urgent';
export type Role = 'owner' | 'supervisor' | 'agent';
export type AuthorType = 'customer' | 'agent' | 'ai' | 'system';
export type ConversationStatus = 'open' | 'pending' | 'resolved' | 'escalated';
export type ArticleStatus = 'draft' | 'published' | 'archived';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  avatarUrl?: string | null;
  isActive: boolean;
}

export interface WorkspaceSettings {
  greeting: string;
  brandVoice: string;
  fallbackMessage: string;
  instructions: string;
  aiAutoreply: boolean;
  aiSuggestThreshold: number;
  aiAutoresolveThreshold: number;
  escalateAfterAiTurns: number;
  businessHours: string;
  [key: string]: unknown;
  autopilotEnabled?: boolean;
  /** Hours of the day in UTC, such as "22-6" or "9,13,17". */
  autopilotHours?: string;
  recordCalls?: boolean;
  recordingNotice?: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  accentColor: string;
  logoUrl?: string | null;
  publicKey: string;
  settings: WorkspaceSettings;
}

export interface Session {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  user: User;
  workspace: Workspace;
}

export interface Customer {
  id: string;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  notes?: string | null;
  channelIds: Record<string, string>;
  createdAt: string;
  lastSeenAt: string;
  totalTickets: number;
  openTickets: number;
}

export interface Citation {
  articleId: string;
  title: string;
  excerpt: string;
}

export interface MessageMeta {
  channel?: string;
  confidence?: number;
  engine?: string;
  citations?: Citation[];
  delivered?: boolean;
  reason?: string;
  [key: string]: unknown;
}

export interface Message {
  id: string;
  conversationId: string;
  authorType: AuthorType;
  authorName?: string | null;
  body: string;
  isPrivate: boolean;
  meta: MessageMeta;
  createdAt: string;
  attachments?: Attachment[];
}

export interface Conversation {
  id: string;
  channel: Channel;
  subject?: string | null;
  status: ConversationStatus;
  customer?: Customer | null;
  assignedUserId?: string | null;
  ticketId?: string | null;
  aiHandled: boolean;
  aiTurns: number;
  lastMessageAt: string;
  createdAt: string;
  messages: Message[];
}

export interface Ticket {
  id: string;
  number: number;
  subject: string;
  description: string;
  status: TicketStatus;
  priority: Priority;
  channel: Channel;
  category?: string | null;
  tags: string[];
  customer?: Customer | null;
  assignedUserId?: string | null;
  aiHandled: boolean;
  aiConfidence?: number | null;
  firstResponseAt?: string | null;
  slaDueAt?: string | null;
  slaBreached: boolean;
  resolvedAt?: string | null;
  satisfaction?: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface Article {
  id: string;
  title: string;
  body: string;
  summary?: string | null;
  category: string;
  tags: string[];
  status: ArticleStatus;
  visibility: 'internal' | 'public';
  version: number;
  authorName?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SearchHit {
  articleId: string;
  title: string;
  excerpt: string;
  category: string;
  score: number;
}

export interface Macro {
  id: string;
  name: string;
  body: string;
  tags: string[];
  updatedAt: string;
}

export interface SlaPolicy {
  id: string;
  name: string;
  priorities: Priority[];
  firstResponseMinutes: number;
  resolutionMinutes: number;
  isActive: boolean;
}

export interface RoutingRule {
  id: string;
  name: string;
  orderIndex: number;
  isActive: boolean;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
}

export interface ChannelConnection {
  id: string;
  channel: Channel;
  displayName: string;
  isActive: boolean;
  configuredKeys: string[];
  missingKeys: string[];
  webhookUrl?: string | null;
  lastEventAt?: string | null;
}

export interface ChannelCatalogEntry {
  channel: Channel;
  label: string;
  requiredKeys: string[];
  hasWebhook: boolean;
  canSend: boolean;
}

export interface Draft {
  text: string;
  confidence: number;
  citations: Citation[];
  engine: string;
  shouldEscalate: boolean;
}

export interface TapSuggestion {
  id: string;
  kind: 'answer' | 'action' | 'warning' | 'question';
  text: string;
  confidence: number;
  citations?: Citation[];
  engine?: string;
  at: string;
}

export interface TapTranscriptLine {
  id: string;
  speaker: 'customer' | 'agent';
  text: string;
  at: string;
}

export interface TapSession {
  id: string;
  status: 'live' | 'ended';
  customerLabel: string;
  conversationId?: string | null;
  transcript: TapTranscriptLine[];
  suggestions: TapSuggestion[];
  summary?: string | null;
  createdAt: string;
  endedAt?: string | null;
}

export interface MetricPoint {
  date: string;
  created: number;
  resolved: number;
}

export interface MixEntry {
  label: string;
  value: number;
  share: number;
}

export interface LeaderboardRow {
  userId: string;
  name: string;
  solved: number;
  medianFirstResponseMinutes: number | null;
  csat: number | null;
}

export interface AnalyticsSummary {
  rangeDays: number;
  openTickets: number;
  openDelta: number;
  slaAtRisk: number;
  aiDeflection: number;
  aiDeflectionDelta: number;
  csat: number;
  csatDelta: number;
  medianFirstResponseMinutes: number | null;
  series: MetricPoint[];
  channelMix: MixEntry[];
  priorityMix: MixEntry[];
  openPriorityMix: MixEntry[];
  topCategories: MixEntry[];
  agentLeaderboard: LeaderboardRow[];
}

export interface InboxStats {
  open: number;
  escalated: number;
  pending: number;
  mine: number;
  unassigned: number;
}

export interface Workload {
  openConversations: number;
  escalated: number;
  unassigned: number;
  byChannel: { label: string; value: number }[];
}

export interface PortalConfig {
  publicKey: string;
  workspaceName: string;
  accentColor: string;
  greeting: string;
  logoUrl?: string | null;
  aiEnabled: boolean;
}

export interface HealthReport {
  status: string;
  version: string;
  database: string;
  /** False when the backend is running but could not read its database. */
  databaseReady?: boolean;
  ai: { enabled: boolean; provider: string; model: string | null };
  channels: string[];
  /** True when the sample workspace is loaded, so the demo sign ins work. */
  demoData?: boolean;
  /** True once this install has a workspace in it. */
  configured?: boolean;
}

/** Filters accepted by the conversation and ticket list endpoints. */
export interface ConversationFilters {
  status?: ConversationStatus;
  channel?: Channel;
  assigned?: string;
  search?: string;
}

export interface TicketFilters {
  status?: TicketStatus[];
  priority?: Priority[];
  channel?: Channel;
  assigned?: string;
  search?: string;
}

/** What model this workspace uses. The key itself never reaches the browser. */
export interface AiConfig {
  provider: 'none' | 'openai' | 'anthropic' | 'gemini';
  model: string;
  /** Used when `model` is empty, so a key on its own is enough to start. */
  defaultModel: string;
  baseUrl: string;
  embeddingModel: string;
  hasKey: boolean;
  /** True when environment variables decide this, which makes it read only. */
  managedByEnv: boolean;
  /** False when the server cannot encrypt, so it would store keys as they are. */
  encryptionAvailable: boolean;
  active: boolean;
}

export interface AiTestResult {
  ok: boolean;
  detail: string;
}

export interface BackupSnapshot {
  name: string;
  bytes: number;
  takenAt: string;
}

export interface BackupStatus {
  supported: boolean;
  directory: string;
  intervalHours: number;
  keep: number;
  snapshots: BackupSnapshot[];
  /** Files a reset archived before deleting them. */
  attachmentArchives?: BackupSnapshot[];
}

/** A file on a message. `url` is where to fetch it from. */
export interface Attachment {
  id: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  kind: 'image' | 'audio' | 'video' | 'file';
  url: string;
  createdAt: string;
}

/** A file a visitor uploaded, plus the session it belongs to. */
export interface WidgetAttachment extends Attachment {
  sessionId: string;
}

/** Whether the queue is being worked automatically, and when. */
export interface AutopilotStatus {
  enabled: boolean;
  /** Hours of the day, UTC, when it runs by itself. */
  hours: number[];
  runningNow: boolean;
  confidenceThreshold: number;
  modelConnected: boolean;
  maxPerRun: number;
}

/** What one pass over the queue actually did. */
export interface AutopilotRun {
  lookedAt: number;
  answered: number;
  escalated: number;
  skipped: number;
  trigger: string;
  ranAt: string;
}

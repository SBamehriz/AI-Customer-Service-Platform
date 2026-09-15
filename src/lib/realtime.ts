/** Workspace event stream. */

import { API_BASE_URL } from './api';

export type RealtimeEvent =
  | 'connected'
  | 'conversation.created'
  | 'conversation.updated'
  | 'message.created'
  | 'ticket.created'
  | 'ticket.updated'
  | 'tap.transcript'
  | 'tap.suggestion';

export interface RealtimeMessage {
  event: RealtimeEvent;
  data: Record<string, unknown> | null;
}

type Listener = (message: RealtimeMessage) => void;

/** Backoff schedule in milliseconds. The last value repeats. */
const RETRY_DELAYS = [500, 1000, 2000, 5000, 10_000];

export function connectRealtime(token: string | null, onMessage: Listener): () => void {
  if (!token) return () => {};

  let socket: WebSocket | null = null;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const url = () => {
    const base = API_BASE_URL || window.location.origin;
    const wsUrl = new URL('/ws', base);
    wsUrl.protocol = wsUrl.protocol.replace('http', 'ws');
    wsUrl.searchParams.set('token', token);
    return wsUrl.toString();
  };

  const open = () => {
    if (closed) return;
    try {
      socket = new WebSocket(url());
    } catch {
      schedule();
      return;
    }

    socket.onopen = () => {
      attempt = 0;
    };
    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data) as RealtimeMessage);
      } catch {
        // A malformed frame is not worth tearing the connection down for.
      }
    };
    socket.onclose = () => {
      socket = null;
      schedule();
    };
    socket.onerror = () => socket?.close();
  };

  const schedule = () => {
    if (closed) return;
    const wait = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
    attempt += 1;
    timer = setTimeout(open, wait);
  };

  open();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    socket?.close();
    socket = null;
  };
}

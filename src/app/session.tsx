/** Session context. Who is signed in, which API client to use, and the live event stream. */

import * as React from 'react';
import { createHttpClient, probeBackend, type ApiClient, type ApiMode } from '@/lib/api';
import { connectRealtime, type RealtimeMessage } from '@/lib/realtime';
import type { Session, User, Workspace } from '@/lib/types';

const TOKEN_KEY = 'ucsp.token';
const MODE_KEY = 'ucsp.mode';

interface SessionState {
  status: 'loading' | 'anonymous' | 'authenticated';
  mode: ApiMode;
  api: ApiClient;
  user: User | null;
  workspace: Workspace | null;
  /** True when the backend reports an LLM provider is configured. */
  aiEnabled: boolean;
  /** True when the sample workspace is loaded, so demo sign ins will work. */
  demoData: boolean;
  /** True once this install has a workspace in it. */
  configured: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (input: {
    workspaceName: string;
    name: string;
    email: string;
    password: string;
  }) => Promise<void>;
  signInDemo: (role: 'owner' | 'supervisor' | 'agent') => Promise<void>;
  signOut: () => void;
  /** Subscribe to workspace events. Returns a function that unsubscribes. */
  subscribe: (listener: (message: RealtimeMessage) => void) => () => void;
  refreshWorkspace: (workspace: Workspace) => void;
}

const SessionContext = React.createContext<SessionState | null>(null);

const readToken = (): string | null => {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

const writeToken = (token: string | null) => {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Sign in still works for this tab, it just will not survive a reload.
  }
};

/** Demo accounts, in fixture order. Owner, supervisor, then agents. */
const DEMO_EMAILS: Record<'owner' | 'supervisor' | 'agent', string> = {
  owner: 'dana@meridian.example',
  supervisor: 'priya@meridian.example',
  agent: 'marcus@meridian.example',
};

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const tokenRef = React.useRef<string | null>(readToken());
  const [status, setStatus] = React.useState<SessionState['status']>('loading');
  const [mode, setMode] = React.useState<ApiMode>('demo');
  const [aiEnabled, setAiEnabled] = React.useState(false);
  const [demoData, setDemoData] = React.useState(false);
  const [configured, setConfigured] = React.useState(true);
  const [user, setUser] = React.useState<User | null>(null);
  const [workspace, setWorkspace] = React.useState<Workspace | null>(null);

  const httpClient = React.useMemo(() => createHttpClient(() => tokenRef.current), []);
  const [demoClient, setDemoClient] = React.useState<ApiClient | null>(null);
  const api = mode === 'live' ? httpClient : (demoClient ?? httpClient);
  const apiRef = React.useRef(api);
  apiRef.current = api;

  const listeners = React.useRef(new Set<(message: RealtimeMessage) => void>());

  const applySession = React.useCallback((session: Session, nextMode: ApiMode) => {
    tokenRef.current = session.accessToken;
    if (nextMode === 'live') writeToken(session.accessToken);
    setUser(session.user);
    setWorkspace(session.workspace);
    setStatus('authenticated');
  }, []);

  // Decide demo vs live once, then try to restore an existing session.
  React.useEffect(() => {
    let cancelled = false;

    (async () => {
      const health = await probeBackend();
      if (cancelled) return;

      const nextMode: ApiMode = health ? 'live' : 'demo';
      setAiEnabled(Boolean(health?.ai.enabled));
      setDemoData(health ? Boolean(health.demoData) : true);
      setConfigured(health ? health.configured !== false : true);
      try {
        window.localStorage.setItem(MODE_KEY, nextMode);
      } catch {
        // Diagnostic only.
      }

      if (nextMode === 'demo') {
        const { createDemoClient } = await import('@/lib/demo/client');
        if (cancelled) return;
        const client = createDemoClient();
        setDemoClient(client);
        apiRef.current = client;
        setMode('demo');
        setStatus('anonymous');
        return;
      }
      setMode('live');

      const token = tokenRef.current;
      if (token) {
        try {
          const session = await httpClient.restore(token);
          if (!cancelled) applySession(session, 'live');
          return;
        } catch {
          writeToken(null);
          tokenRef.current = null;
        }
      }
      if (!cancelled) setStatus('anonymous');
    })();

    return () => {
      cancelled = true;
    };
  }, [httpClient, applySession]);

  // One socket per session, fanned out to every subscriber.
  React.useEffect(() => {
    if (status !== 'authenticated' || mode !== 'live') return;
    return connectRealtime(tokenRef.current, (message) => {
      listeners.current.forEach((listener) => listener(message));
    });
  }, [status, mode]);

  const value = React.useMemo<SessionState>(
    () => ({
      status,
      mode,
      api,
      user,
      workspace,
      aiEnabled,
      demoData,
      configured,
      async signIn(email, password) {
        applySession(await apiRef.current.login(email, password), mode);
      },
      async signUp(input) {
        applySession(await apiRef.current.register(input), mode);
      },
      async signInDemo(role) {
        applySession(await apiRef.current.login(DEMO_EMAILS[role], 'demo1234'), mode);
      },
      signOut() {
        writeToken(null);
        tokenRef.current = null;
        setUser(null);
        setWorkspace(null);
        setStatus('anonymous');
      },
      subscribe(listener) {
        listeners.current.add(listener);
        return () => listeners.current.delete(listener);
      },
      refreshWorkspace: setWorkspace,
    }),
    [status, mode, api, user, workspace, aiEnabled, demoData, configured, applySession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = React.useContext(SessionContext);
  if (!context) throw new Error('useSession must be used inside <SessionProvider>');
  return context;
}

/** Convenience for the many places that only need the client. */
export function useApi(): ApiClient {
  return useSession().api;
}

/** Whether the signed in person may change what the workspace tells customers. */
export function useCanManage(): boolean {
  const { user } = useSession();
  return user?.role === 'owner' || user?.role === 'supervisor';
}

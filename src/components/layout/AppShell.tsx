import * as React from 'react';
import { Outlet } from 'react-router-dom';
import { X } from '@/components/icons';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { CommandPalette } from './CommandPalette';
import { Button } from '@/components/ui';
import { useHotkey, useLocalStorage, useMediaQuery } from '@/hooks';
import { useSession } from '@/app/session';
import type { InboxStats } from '@/lib/types';

/** The authenticated frame. A persistent sidebar, a sticky top bar and the routed content. */
export function AppShell() {
  const [collapsed, setCollapsed] = useLocalStorage('ucsp.sidebar-collapsed', false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [counts, setCounts] = React.useState<Partial<Record<string, number>>>({});
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const { api, subscribe } = useSession();

  useHotkey('mod+k', () => setPaletteOpen((open) => !open), { allowInInput: true });

  // Inbox badge counts, refreshed whenever the workspace reports a change.
  React.useEffect(() => {
    let active = true;
    const load = () => {
      api
        .inboxStats()
        .then((stats: InboxStats) => {
          if (active) setCounts({ '/app/inbox': stats.open + stats.escalated });
        })
        .catch(() => {
          /* A missing badge is not worth surfacing an error for. */
        });
    };
    load();
    const unsubscribe = subscribe((message) => {
      if (message.event.startsWith('conversation.') || message.event === 'message.created') load();
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [api, subscribe]);

  return (
    <div className="flex h-dvh overflow-hidden bg-bg">
      {isDesktop ? (
        <div className="shrink-0">
          <Sidebar collapsed={collapsed} counts={counts} />
        </div>
      ) : null}

      {!isDesktop && mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="animate-fade-up absolute inset-y-0 left-0 flex">
            <Sidebar collapsed={false} counts={counts} onNavigate={() => setMobileOpen(false)} />
            <Button
              variant="ghost"
              size="icon"
              className="absolute -right-11 top-3 text-white"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          onToggleSidebar={() => setCollapsed(!collapsed)}
          onOpenMobileNav={() => setMobileOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        <main className="scroll-slim min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

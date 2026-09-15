import { LogOut, Menu, PanelLeft, Search } from '@/components/icons';
import { Avatar, Badge, Button, Tooltip } from '@/components/ui';
import { useSession } from '@/app/session';
import { ThemeToggle } from './ThemeToggle';
import { cn } from '@/lib/utils';

export interface TopBarProps {
  onToggleSidebar: () => void;
  onOpenMobileNav: () => void;
  onOpenPalette: () => void;
}

export function TopBar({ onToggleSidebar, onOpenMobileNav, onOpenPalette }: TopBarProps) {
  const { user, mode, aiEnabled, signOut } = useSession();

  return (
    <header className="veil sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line px-3 sm:px-4">
      <Button
        variant="ghost"
        size="icon"
        onClick={onOpenMobileNav}
        className="lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        className="hidden lg:inline-flex"
        aria-label="Toggle sidebar"
      >
        <PanelLeft className="h-4 w-4" />
      </Button>

      <button
        type="button"
        onClick={onOpenPalette}
        className={cn(
          'flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md border border-line bg-surface px-3',
          'text-left text-base text-ink-muted transition-colors hover:border-line-strong',
          'sm:max-w-sm',
        )}
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">Search or jump to</span>
        <kbd className="hidden shrink-0 rounded border border-line bg-sunken px-1.5 py-0.5 text-2xs font-medium text-ink-muted sm:inline">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1.5">
        {mode === 'demo' ? (
          <Tooltip label="Sample data, no backend connected" side="bottom">
            <Badge tone="warning" dot>
              Demo
            </Badge>
          </Tooltip>
        ) : (
          <Tooltip
            label={aiEnabled ? 'Connected · AI provider configured' : 'Connected · retrieval only AI'}
            side="bottom"
          >
            <Badge tone={aiEnabled ? 'success' : 'neutral'} dot>
              Live
            </Badge>
          </Tooltip>
        )}

        <ThemeToggle />

        <div className="hidden items-center gap-2 pl-1 sm:flex">
          <Avatar name={user?.name} size="sm" />
        </div>
        <Tooltip label="Sign out" side="bottom">
          <Button variant="ghost" size="icon" onClick={signOut} aria-label="Sign out">
            <LogOut className="h-4 w-4" />
          </Button>
        </Tooltip>
      </div>
    </header>
  );
}


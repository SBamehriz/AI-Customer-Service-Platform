import * as React from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart,
  BookOpen,
  Inbox,
  LayoutDashboard,
  PhoneCall,
  Settings,
  Ticket,
  Users,
} from '@/components/icons';
import { Wordmark } from '@/components/brand/Logo';
import { useSession } from '@/app/session';
import { cn } from '@/lib/utils';
import type { Role } from '@/lib/types';

export interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Roles allowed to see the item. Absent means everyone. */
  roles?: Role[];
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/app', label: 'Home', icon: LayoutDashboard, end: true },
  { to: '/app/inbox', label: 'Inbox', icon: Inbox },
  { to: '/app/tickets', label: 'Tickets', icon: Ticket },
  { to: '/app/customers', label: 'Customers', icon: Users },
  { to: '/app/tap', label: 'Tap AI', icon: PhoneCall },
  { to: '/app/knowledge', label: 'Knowledge', icon: BookOpen },
  { to: '/app/analytics', label: 'Analytics', icon: BarChart, roles: ['owner', 'supervisor'] },
  { to: '/app/settings', label: 'Settings', icon: Settings, roles: ['owner', 'supervisor'] },
];

export function visibleNavItems(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || (role ? item.roles.includes(role) : false));
}

export interface SidebarProps {
  collapsed: boolean;
  onNavigate?: () => void;
  counts?: Partial<Record<string, number>>;
}

export function Sidebar({ collapsed, onNavigate, counts }: SidebarProps) {
  const { user, workspace } = useSession();
  const items = visibleNavItems(user?.role);

  return (
    <nav
      className={cn(
        'flex h-full flex-col border-r border-line bg-surface',
        collapsed ? 'w-[64px]' : 'w-[228px]',
        'transition-[width] duration-200 ease-[cubic-bezier(0.32,0.72,0,1)]',
      )}
      aria-label="Main"
    >
      <div className={cn('flex h-14 items-center border-b border-line-subtle', collapsed ? 'justify-center px-2' : 'px-4')}>
        <Wordmark compact={collapsed} />
      </div>

      <ul className="scroll-slim flex-1 space-y-0.5 overflow-y-auto p-2">
        {items.map((item) => {
          const Icon = item.icon;
          const count = counts?.[item.to];
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                onClick={onNavigate}
                title={collapsed ? item.label : undefined}
                className={({ isActive }) =>
                  cn(
                    'group flex h-9 items-center gap-2.5 rounded-md px-2.5 text-base font-medium',
                    'transition-colors duration-150',
                    collapsed && 'justify-center px-0',
                    isActive
                      ? 'bg-accent-soft text-accent-text'
                      : 'text-ink-secondary hover:bg-hover hover:text-ink',
                  )
                }
              >
                <Icon className="h-[17px] w-[17px] shrink-0" />
                {!collapsed ? (
                  <>
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {count ? (
                      <span className="numeric rounded-full bg-sunken px-1.5 text-2xs font-semibold text-ink-secondary">
                        {count > 99 ? '99+' : count}
                      </span>
                    ) : null}
                  </>
                ) : null}
              </NavLink>
            </li>
          );
        })}
      </ul>

      {!collapsed && workspace ? (
        <div className="border-t border-line-subtle p-3">
          <p className="truncate text-xs font-medium text-ink">{workspace.name}</p>
          <p className="truncate text-2xs text-ink-muted">
            {user?.name} · {user?.role}
          </p>
        </div>
      ) : null}
    </nav>
  );
}

import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CornerDownLeft, Search, Sparkles } from '@/components/icons';
import { useSession } from '@/app/session';
import { useDebounced } from '@/hooks';
import { visibleNavItems } from './Sidebar';
import { Spinner } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { SearchHit, Ticket } from '@/lib/types';

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
}

/** The command palette. Navigation, ticket lookup and knowledge search in one input. */
export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { api, user } = useSession();
  const [query, setQuery] = React.useState('');
  const [cursor, setCursor] = React.useState(0);
  const [tickets, setTickets] = React.useState<Ticket[]>([]);
  const [articles, setArticles] = React.useState<SearchHit[]>([]);
  const [searching, setSearching] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const debounced = useDebounced(query, 220);

  React.useEffect(() => {
    if (!open) return;
    setQuery('');
    setCursor(0);
    setTickets([]);
    setArticles([]);
    // Focus after paint so the browser does not scroll the page behind it.
    const timer = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(timer);
  }, [open]);

  React.useEffect(() => {
    if (!open || debounced.trim().length < 2) {
      setTickets([]);
      setArticles([]);
      return;
    }
    let active = true;
    setSearching(true);
    Promise.all([
      api.listTickets({ search: debounced }).catch(() => []),
      api.searchKnowledge(debounced).catch(() => []),
    ])
      .then(([ticketResults, articleResults]) => {
        if (!active) return;
        setTickets(ticketResults.slice(0, 4));
        setArticles(articleResults.slice(0, 4));
      })
      .finally(() => {
        if (active) setSearching(false);
      });
    return () => {
      active = false;
    };
  }, [debounced, open, api]);

  const go = React.useCallback(
    (to: string) => {
      navigate(to);
      onClose();
    },
    [navigate, onClose],
  );

  const commands = React.useMemo<Command[]>(() => {
    const needle = query.trim().toLowerCase();
    const navigation: Command[] = visibleNavItems(user?.role)
      .filter((item) => !needle || item.label.toLowerCase().includes(needle))
      .map((item) => ({
        id: `nav:${item.to}`,
        label: item.label,
        group: 'Go to',
        run: () => go(item.to),
      }));

    const ticketCommands: Command[] = tickets.map((ticket) => ({
      id: `ticket:${ticket.id}`,
      label: ticket.subject,
      hint: `#${ticket.number} · ${ticket.status}`,
      group: 'Tickets',
      run: () => go(`/app/tickets?ticket=${ticket.id}`),
    }));

    const articleCommands: Command[] = articles.map((hit) => ({
      id: `article:${hit.articleId}`,
      label: hit.title,
      hint: hit.category,
      group: 'Knowledge',
      run: () => go(`/app/knowledge?article=${hit.articleId}`),
    }));

    const assistant: Command[] = needle.length > 3
      ? [
          {
            id: 'ask',
            label: `Ask the assistant about ${query.trim()}`,
            group: 'Assistant',
            run: () => go(`/app/knowledge?ask=${encodeURIComponent(query.trim())}`),
          },
        ]
      : [];

    return [...navigation, ...ticketCommands, ...articleCommands, ...assistant];
  }, [query, tickets, articles, user?.role, go]);

  React.useEffect(() => {
    setCursor((current) => Math.min(current, Math.max(0, commands.length - 1)));
  }, [commands.length]);

  if (!open) return null;

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      onClose();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCursor((current) => (current + 1) % Math.max(1, commands.length));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor((current) => (current - 1 + commands.length) % Math.max(1, commands.length));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      commands[cursor]?.run();
    }
  };

  let lastGroup = '';

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]">
      <div className="absolute inset-0 bg-black/25 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={onKeyDown}
        className="animate-fade-up relative w-full max-w-lg overflow-hidden rounded-xl border border-line bg-surface shadow-xl"
      >
        <div className="flex items-center gap-2.5 border-b border-line-subtle px-4">
          <Search className="h-4 w-4 shrink-0 text-ink-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search tickets and articles, or jump to a page"
            className="h-12 min-w-0 flex-1 bg-transparent text-md text-ink outline-none placeholder:text-ink-muted"
          />
          {searching ? <Spinner /> : null}
        </div>

        <ul className="scroll-slim max-h-80 overflow-y-auto p-1.5">
          {commands.length === 0 ? (
            <li className="px-3 py-8 text-center text-sm text-ink-muted">No matches</li>
          ) : (
            commands.map((command, index) => {
              const showGroup = command.group !== lastGroup;
              lastGroup = command.group;
              return (
                <React.Fragment key={command.id}>
                  {showGroup ? (
                    <li className="px-2.5 pb-1 pt-2.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
                      {command.group}
                    </li>
                  ) : null}
                  <li>
                    <button
                      type="button"
                      onMouseEnter={() => setCursor(index)}
                      onClick={command.run}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-base',
                        index === cursor ? 'bg-accent-soft text-accent-text' : 'text-ink',
                      )}
                    >
                      {command.group === 'Assistant' ? (
                        <Sparkles className="h-4 w-4 shrink-0 opacity-70" />
                      ) : (
                        <ArrowRight className="h-4 w-4 shrink-0 opacity-40" />
                      )}
                      <span className="min-w-0 flex-1 truncate">{command.label}</span>
                      {command.hint ? (
                        <span className="shrink-0 text-xs text-ink-muted">{command.hint}</span>
                      ) : null}
                      {index === cursor ? (
                        <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-50" />
                      ) : null}
                    </button>
                  </li>
                </React.Fragment>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}

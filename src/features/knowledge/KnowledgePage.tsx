import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, Lock, Pencil, Plus, Search, Sparkles, Trash2 } from '@/components/icons';
import { Page, PageHeader } from '@/components/layout';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  SkeletonRows,
  Tooltip,
  useToast,
} from '@/components/ui';
import { ArticleEditor } from './ArticleEditor';
import { AssistantPanel } from './AssistantPanel';
import { useApi, useCanManage } from '@/app/session';
import { useAsync, useDebounced } from '@/hooks';
import { formatDate, relativeTime } from '@/lib/format';
import { cn, groupBy } from '@/lib/utils';
import type { Article } from '@/lib/types';

/** The knowledge base, plus the assistant that reads it. */
export default function KnowledgePage() {
  const api = useApi();
  const canManage = useCanManage();
  const toast = useToast();
  const [params, setParams] = useSearchParams();

  const [search, setSearch] = React.useState('');
  const debounced = useDebounced(search, 250);
  const [editing, setEditing] = React.useState<Article | 'new' | null>(null);

  const articles = useAsync(() => api.listArticles(), [api]);
  const rows = articles.data ?? [];

  const filtered = React.useMemo(() => {
    if (!debounced) return rows;
    const needle = debounced.toLowerCase();
    return rows.filter(
      (article) =>
        article.title.toLowerCase().includes(needle) ||
        article.body.toLowerCase().includes(needle) ||
        article.tags.some((tag) => tag.toLowerCase().includes(needle)),
    );
  }, [rows, debounced]);

  const selectedId = params.get('article');
  const selected = rows.find((article) => article.id === selectedId) ?? filtered[0] ?? null;
  const askQuery = params.get('ask') ?? '';

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('article', id);
    next.delete('ask');
    setParams(next);
  };

  const save = async (draft: Partial<Article> & { title: string }) => {
    try {
      if (editing && editing !== 'new') {
        const updated = await api.updateArticle(editing.id, draft);
        articles.setData((current) =>
          (current ?? []).map((article) => (article.id === updated.id ? updated : article)),
        );
        toast.success('Article updated');
      } else {
        const created = await api.createArticle(draft);
        articles.setData((current) => [created, ...(current ?? [])]);
        select(created.id);
        toast.success('Article created');
      }
      setEditing(null);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not save the article');
    }
  };

  const remove = async (article: Article) => {
    try {
      await api.deleteArticle(article.id);
      articles.setData((current) => (current ?? []).filter((item) => item.id !== article.id));
      toast.success('Article deleted');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not delete the article');
    }
  };

  const byCategory = groupBy(filtered, (article) => article.category);

  return (
    <Page className="space-y-4">
      <PageHeader
        title="Knowledge"
        description="The only source the assistant is allowed to answer from."
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing('new')}>
            New article
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card flush className="overflow-hidden">
            <div className="border-b border-line-subtle p-3">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Filter articles"
                leading={<Search className="h-4 w-4" />}
                aria-label="Filter articles"
              />
            </div>
            {articles.error ? (
              <ErrorState error={articles.error} onRetry={articles.reload} />
            ) : articles.loading ? (
              <SkeletonRows rows={6} className="p-3" />
            ) : filtered.length === 0 ? (
              <EmptyState
                icon={<BookOpen className="h-5 w-5" />}
                title="No articles"
                description="Write the answer once, and every channel can use it."
                action={
                  <Button size="sm" variant="secondary" onClick={() => setEditing('new')}>
                    Write the first one
                  </Button>
                }
              />
            ) : (
              <div className="scroll-slim max-h-[60vh] overflow-y-auto">
                {Object.entries(byCategory).map(([category, items]) => (
                  <section key={category}>
                    <h3 className="sticky top-0 bg-sunken px-3 py-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
                      {category}
                    </h3>
                    <ul className="divide-y divide-line-subtle">
                      {items.map((article) => (
                        <li key={article.id}>
                          <button
                            type="button"
                            onClick={() => select(article.id)}
                            aria-current={article.id === selected?.id}
                            className={cn(
                              'flex w-full items-start gap-2 px-3 py-2.5 text-left transition-colors duration-100',
                              article.id === selected?.id ? 'bg-accent-soft' : 'hover:bg-hover',
                            )}
                          >
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-base text-ink">{article.title}</span>
                              <span className="block text-2xs text-ink-muted">
                                v{article.version} · {relativeTime(article.updatedAt)}
                              </span>
                            </span>
                            {article.status !== 'published' ? (
                              <Badge tone="warning" className="shrink-0 px-1.5 py-0 text-[10px]">
                                {article.status}
                              </Badge>
                            ) : null}
                            {article.visibility === 'internal' ? (
                              <Lock className="mt-0.5 h-3 w-3 shrink-0 text-ink-muted" />
                            ) : null}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </Card>

          <AssistantPanel initialQuestion={askQuery} />
        </div>

        {selected ? (
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line-subtle pb-3">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold text-ink">{selected.title}</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  {selected.category} · v{selected.version} · updated {formatDate(selected.updatedAt)}
                  {selected.authorName ? ` by ${selected.authorName}` : ''}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Badge tone={selected.status === 'published' ? 'success' : 'warning'}>
                  {selected.status}
                </Badge>
                {selected.visibility === 'internal' ? (
                  <Badge tone="neutral" dot>
                    Internal
                  </Badge>
                ) : null}
                {canManage || selected.status !== 'published' ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setEditing(selected)}
                    aria-label="Edit article"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                ) : (
                  <Tooltip label="Published articles are edited by a supervisor">
                    <span className="inline-flex h-8 w-8 items-center justify-center text-ink-muted">
                      <Lock className="h-4 w-4" />
                    </span>
                  </Tooltip>
                )}
                {canManage ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(selected)}
                    aria-label="Delete article"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
            </div>

            {selected.summary ? (
              <p className="mt-3.5 rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-secondary">
                {selected.summary}
              </p>
            ) : null}

            <div className="mt-4 space-y-3.5 text-base leading-relaxed text-ink">
              {selected.body.split(/\n\s*\n/).map((paragraph, index) => (
                <p key={index} className="whitespace-pre-wrap">
                  {paragraph}
                </p>
              ))}
            </div>

            {selected.tags.length ? (
              <div className="mt-5 flex flex-wrap gap-1.5 border-t border-line-subtle pt-3.5">
                {selected.tags.map((tag) => (
                  <Badge key={tag} tone="neutral">
                    {tag}
                  </Badge>
                ))}
              </div>
            ) : null}

            {selected.visibility === 'internal' ? (
              <p className="mt-4 flex items-start gap-2 rounded-lg border border-line px-3 py-2.5 text-xs text-ink-muted">
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Internal articles are used when drafting for agents, but never when answering a
                customer directly.
              </p>
            ) : null}
          </Card>
        ) : null}
      </div>

      <ArticleEditor
        open={editing !== null}
        article={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)}
        onSave={save}
      />
    </Page>
  );
}

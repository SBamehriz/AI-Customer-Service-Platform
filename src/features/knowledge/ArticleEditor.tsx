import * as React from 'react';
import { Button, Field, Input, Modal, Select, Textarea } from '@/components/ui';
import { useCanManage } from '@/app/session';
import type { Article, ArticleStatus } from '@/lib/types';

export interface ArticleEditorProps {
  open: boolean;
  article: Article | null;
  onClose: () => void;
  onSave: (draft: Partial<Article> & { title: string }) => Promise<void>;
}

const EMPTY = {
  title: '',
  summary: '',
  body: '',
  category: 'General',
  tags: '',
  status: 'draft' as ArticleStatus,
  visibility: 'public' as Article['visibility'],
};

export function ArticleEditor({ open, article, onClose, onSave }: ArticleEditorProps) {
  const canManage = useCanManage();
  const [form, setForm] = React.useState(EMPTY);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setForm(
      article
        ? {
            title: article.title,
            summary: article.summary ?? '',
            body: article.body,
            category: article.category,
            tags: article.tags.join(', '),
            status: article.status,
            visibility: article.visibility,
          }
        : EMPTY,
    );
  }, [open, article]);

  const submit = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await onSave({
        title: form.title.trim(),
        summary: form.summary.trim() || null,
        body: form.body,
        category: form.category.trim() || 'General',
        // Tags are typed freely, split on commas, and duplicates dropped.
        tags: [...new Set(form.tags.split(',').map((tag) => tag.trim()).filter(Boolean))],
        status: form.status,
        visibility: form.visibility,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={article ? 'Edit article' : 'New article'}
      description={
        article
          ? `Version ${article.version}. Saving a content change creates version ${article.version + 1}.`
          : 'Write it the way you would say it out loud. The assistant quotes this verbatim.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={saving} disabled={!form.title.trim()}>
            {article ? 'Save changes' : 'Create article'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Title" htmlFor="article-title">
          <Input
            id="article-title"
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            placeholder="Returns and exchanges"
            autoFocus
          />
        </Field>

        <Field
          label="Summary"
          htmlFor="article-summary"
          hint="One line. Shown in search results and citation chips."
        >
          <Input
            id="article-summary"
            value={form.summary}
            onChange={(event) => setForm({ ...form, summary: event.target.value })}
            placeholder="60-day window on unused gear."
          />
        </Field>

        <Field
          label="Body"
          htmlFor="article-body"
          hint="Blank lines separate paragraphs. State the actual numbers, because the assistant will not infer them."
        >
          <Textarea
            id="article-body"
            value={form.body}
            onChange={(event) => setForm({ ...form, body: event.target.value })}
            className="min-h-[220px] font-normal"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category" htmlFor="article-category">
            <Input
              id="article-category"
              value={form.category}
              onChange={(event) => setForm({ ...form, category: event.target.value })}
            />
          </Field>
          <Field label="Tags" htmlFor="article-tags" hint="Comma separated.">
            <Input
              id="article-tags"
              value={form.tags}
              onChange={(event) => setForm({ ...form, tags: event.target.value })}
              placeholder="returns, refund"
            />
          </Field>
          <Field
            label="Status"
            htmlFor="article-status"
            hint={
              canManage
                ? 'Only published articles are retrievable.'
                : 'Only published articles are retrievable, and a supervisor publishes them.'
            }
          >
            <Select
              id="article-status"
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value as ArticleStatus })}
            >
              <option value="draft">Draft</option>
              {/* Publishing puts the text in front of customers, so it is a
                  supervisor call. The server refuses it either way. */}
              {canManage ? <option value="published">Published</option> : null}
              <option value="archived">Archived</option>
            </Select>
          </Field>
          <Field
            label="Visibility"
            htmlFor="article-visibility"
            hint="Internal articles never reach a customer."
          >
            <Select
              id="article-visibility"
              value={form.visibility}
              onChange={(event) =>
                setForm({ ...form, visibility: event.target.value as Article['visibility'] })
              }
            >
              <option value="public">Public</option>
              <option value="internal">Internal only</option>
            </Select>
          </Field>
        </div>
      </div>
    </Modal>
  );
}

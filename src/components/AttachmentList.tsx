import { Download, Paperclip } from '@/components/icons';
import { cn } from '@/lib/utils';
import type { Attachment } from '@/lib/types';

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** The files on a message. */
export function AttachmentList({
  attachments,
  className,
  resolveUrl,
}: {
  attachments: Attachment[];
  className?: string;
  /** Where to actually fetch each file from. */
  resolveUrl?: (file: Attachment) => string;
}) {
  if (attachments.length === 0) return null;
  const urlFor = (file: Attachment) => resolveUrl?.(file) ?? file.url;

  return (
    <div className={cn('mt-2 space-y-2', className)}>
      {attachments.map((file) =>
        file.kind === 'image' ? (
          <a
            key={file.id}
            href={urlFor(file)}
            target="_blank"
            rel="noreferrer noopener"
            className="block w-fit overflow-hidden rounded-lg border border-line transition-opacity hover:opacity-90"
          >
            <img
              src={urlFor(file)}
              alt={file.filename}
              loading="lazy"
              className="max-h-64 max-w-full object-contain"
            />
          </a>
        ) : file.kind === 'audio' ? (
          <div key={file.id} className="w-fit max-w-full">
            <audio controls preload="none" src={urlFor(file)} className="h-9 max-w-full">
              <a href={urlFor(file)}>{file.filename}</a>
            </audio>
            <p className="mt-0.5 text-2xs text-ink-muted">
              {file.filename} · {fileSize(file.sizeBytes)}
            </p>
          </div>
        ) : (
          <a
            key={file.id}
            href={urlFor(file)}
            target="_blank"
            rel="noreferrer noopener"
            className="flex w-fit max-w-full items-center gap-2.5 rounded-lg border border-line bg-surface px-3 py-2 transition-colors hover:border-accent-border hover:bg-accent-soft/40"
          >
            <Paperclip className="h-4 w-4 shrink-0 text-ink-muted" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-ink">{file.filename}</span>
              <span className="block text-2xs text-ink-muted">{fileSize(file.sizeBytes)}</span>
            </span>
            <Download className="h-4 w-4 shrink-0 text-ink-muted" />
          </a>
        ),
      )}
    </div>
  );
}

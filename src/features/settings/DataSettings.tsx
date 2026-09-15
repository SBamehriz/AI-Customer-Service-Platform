import * as React from 'react';
import { Download, RefreshCw, ShieldCheck } from '@/components/icons';
import {
  Button,
  Card,
  CardHeader,
  ErrorState,
  Skeleton,
  useToast,
} from '@/components/ui';
import { useApi, useSession } from '@/app/session';
import { useAsync } from '@/hooks';
import { formatDate, plural } from '@/lib/format';

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Where the data lives and how to get it out. */
export function DataSettings() {
  const api = useApi();
  const toast = useToast();
  const { mode } = useSession();
  const status = useAsync(() => api.getBackupStatus(), [api]);
  const [snapshotting, setSnapshotting] = React.useState(false);
  const [restoring, setRestoring] = React.useState<string | null>(null);

  const snapshot = async () => {
    setSnapshotting(true);
    try {
      const result = await api.createBackup();
      status.setData((current) =>
        current ? { ...current, snapshots: result.snapshots } : (current as never),
      );
      toast.success(`Snapshot taken, ${result.name}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not take a snapshot');
    } finally {
      setSnapshotting(false);
    }
  };

  const restoreFiles = async (name: string) => {
    setRestoring(name);
    try {
      const result = await api.restoreAttachmentArchive(name);
      toast.success(`Put ${plural(result.restored, 'file')} back`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Could not restore those files');
    } finally {
      setRestoring(null);
    }
  };

  if (status.error) return <ErrorState error={status.error} onRetry={status.reload} />;
  if (status.loading || !status.data) return <Skeleton className="h-96" />;

  const data = status.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Take your data with you"
          description="One file, plain JSON, readable without this platform. Every customer, conversation, ticket and article."
          action={<Download className="h-4 w-4 text-ink-muted" />}
        />
        <p className="mb-3.5 text-sm text-ink-secondary">
          This is the one that matters if you ever move to something else. It carries no
          passwords and no API keys, so it is safe to copy around.
        </p>
        {mode === 'demo' ? (
          <p className="rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-secondary">
            Demo mode keeps nothing, so there is nothing to export. Start the backend to use this.
          </p>
        ) : (
          <a href={api.exportWorkspaceUrl()} download>
            <Button variant="primary" icon={<Download className="h-4 w-4" />}>
              Download the workspace
            </Button>
          </a>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Snapshots"
          description="A copy of the whole database, taken on a timer and kept on disk."
          action={
            data.supported ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={snapshot}
                disabled={snapshotting}
                icon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                {snapshotting ? 'Taking' : 'Take one now'}
              </Button>
            ) : null
          }
        />

        {!data.supported ? (
          <p className="rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-secondary">
            Snapshots are built in for the SQLite database. This install uses something else, so
            back it up with your own database tooling.
          </p>
        ) : (
          <>
            <dl className="mb-3.5 space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-muted">Every</dt>
                <dd className="text-ink">
                  {data.intervalHours > 0 ? plural(data.intervalHours, 'hour') : 'Turned off'}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-muted">Keeping</dt>
                <dd className="text-ink">the newest {data.keep}</dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="shrink-0 text-ink-muted">Folder</dt>
                <dd className="scroll-slim overflow-x-auto whitespace-nowrap font-mono text-xs text-ink">
                  {data.directory}
                </dd>
              </div>
            </dl>

            {data.snapshots.length === 0 ? (
              <p className="rounded-lg bg-sunken px-3 py-2.5 text-sm text-ink-secondary">
                None yet. The first one is taken once the server has been up for a full interval,
                or take one now.
              </p>
            ) : (
              <ul className="divide-y divide-line-subtle text-sm">
                {data.snapshots.map((entry) => (
                  <li key={entry.name} className="flex items-center justify-between gap-3 py-2">
                    <span className="truncate font-mono text-xs text-ink">{entry.name}</span>
                    <span className="shrink-0 text-2xs text-ink-muted">
                      {formatDate(entry.takenAt)} · {fileSize(entry.bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <p className="mt-3.5 text-xs leading-relaxed text-ink-secondary">
              Each snapshot is a complete database taken through SQLite's own backup interface, so
              it is consistent even if the server was busy. Restoring is stopping the server,
              putting the file back where the live one was, and starting again. Copy the folder
              somewhere else as well, because a backup on the same disk only survives the smaller
              kinds of accident.
            </p>

            {(data.attachmentArchives ?? []).length > 0 && (
              <div className="mt-4 border-t border-line-subtle pt-3.5">
                <h4 className="mb-2 text-sm font-medium text-ink">Files from a reset</h4>
                <ul className="divide-y divide-line-subtle text-sm">
                  {(data.attachmentArchives ?? []).map((entry) => (
                    <li key={entry.name} className="flex items-center justify-between gap-3 py-2">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-xs text-ink">
                          {entry.name}
                        </span>
                        <span className="text-2xs text-ink-muted">
                          {formatDate(entry.takenAt)} · {fileSize(entry.bytes)}
                        </span>
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => restoreFiles(entry.name)}
                        disabled={restoring !== null}
                      >
                        {restoring === entry.name ? 'Putting back' : 'Put files back'}
                      </Button>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs leading-relaxed text-ink-secondary">
                  The bytes of a file live on disk rather than in the database, so a reset archives
                  them here before deleting them. Restoring a snapshot brings the conversations
                  back, and this brings back the files they carry.
                </p>
              </div>
            )}
          </>
        )}
      </Card>

      <Card>
        <CardHeader
          title="How the data is held"
          description="Worth knowing before you trust it with anything."
          action={<ShieldCheck className="h-4 w-4 text-ink-muted" />}
        />
        <dl className="space-y-2.5 text-sm">
          {[
            ['Almost one file', 'Everything is in a single SQLite database, except the bytes of uploaded files, which sit beside it on disk.'],
            ['Credentials', 'API keys and channel secrets are encrypted before they are written, so a copy of the file does not hand them over.'],
            ['Passwords', 'Hashed with scrypt, never stored or recoverable.'],
            ['Portable', 'Point DATABASE_URL at PostgreSQL and the same schema works, no migration script.'],
            ['Yours', 'No account, no service, no phoning home. Delete the folder and it is gone.'],
          ].map(([term, detail]) => (
            <div key={term} className="flex flex-wrap gap-x-3 gap-y-0.5">
              <dt className="w-28 shrink-0 font-medium text-ink">{term}</dt>
              <dd className="flex-1 text-ink-secondary">{detail}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

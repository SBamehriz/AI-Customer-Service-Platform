# Your data

Almost everything the platform knows lives in one SQLite file. That single fact
is what makes backing up, moving and leaving simple, so it is worth saying
plainly what happens to your data and how to get it back out.

Files are the exception. The bytes of an attachment live on disk beside the
database rather than inside it, and only the record of each one is a row. That
keeps the database small and a photo a photo, and it means a backup that covers
your data covers two directories rather than one file.

## Where it is

```
backend/data/ucsp.db          the database, everything except the files
backend/data/attachments/     the files themselves, by workspace and month
backend/data/backups/         timed snapshots, newest kept, and reset archives
```

Nothing is sent anywhere. There is no account, no telemetry and no service
behind this. Delete the directory and the data is gone, which is the other half
of the same promise.

## Snapshots

The server copies the database on a timer, every `BACKUP_INTERVAL_HOURS`, and
keeps the newest fourteen. Settings, Data shows them and has a button to take
one immediately.

Copies are taken through SQLite's own backup interface rather than by copying
bytes, so a snapshot taken while the server is busy is still a valid database
rather than a half written one.

A snapshot holds the database, which is everything except the files. The
attachments directory is not copied on the timer, because copying every file
every few hours is a different kind of job. Copy it with the database, or it is
the half of the backup you find out about later.

Restoring is three steps.

1. Stop the server.
2. Copy the snapshot over `backend/data/ucsp.db`.
3. Start the server.

A snapshot sitting next to the database only survives the smaller kinds of
accident. Copy `backend/data/backups/` and `backend/data/attachments/`
somewhere else as well, on a schedule you trust, and the disk failing stops
being a disaster.

Running on PostgreSQL instead, the database half does not apply. Back it up
with your database tooling, `pg_dump` or whatever your host provides. The
attachments directory is still a directory of files either way.

## Starting fresh

Settings, Data, Reset clears the traffic out of a workspace and keeps the
workspace itself. It takes a snapshot first, so it is undoable, and it archives
the files it is about to delete into `backend/data/backups/` as a zip beside
that snapshot. The response names the archive, and Settings, Data lists it.

Putting a reset back is therefore two halves, because the files were never in
the database.

1. Restore the snapshot, as above.
2. Restore the archive, either from Settings, Data or with the API below.

```bash
curl -X POST -H "Authorization: Bearer sk_your_secret_key" \
  https://your-domain.example/api/v1/workspace/backups/attachments/NAME/restore
```

Without the second half the conversations come back and their attachments
answer 410, because the rows point at files that are no longer on disk.

## Export

Settings, Data, Download the workspace gives you the whole thing as plain
JSON. Customers, conversations, messages, tickets, articles, macros, SLA
policies, routing rules and Tap AI sessions.

Attachments are in there as records rather than as bytes. Each one carries its
filename, type, size, the message it belongs to and its path under the
attachments directory, and each message lists the files it carries, so the
export plus that directory is a complete copy.

This is the one that matters if you ever move to something else. It is
readable without this project, without SQLite and without any of this code. It
is also the same shape the seed loader accepts, so it can be loaded back in.

```bash
curl -H "Authorization: Bearer sk_your_secret_key" \
  https://your-domain.example/api/v1/workspace/export > backup.json
```

Passwords and credentials are deliberately left out. An export is meant to be
copied around and read, so shipping decrypted keys inside it would undo the
point of encrypting them.

## Credentials

API keys and channel secrets have to be readable by the server, so they cannot
be hashed the way a password is. They are encrypted before they are written,
with a key derived from `SECRET_KEY`. A copy of the database on its own does
not hand them over.

Two consequences follow.

Rotating `SECRET_KEY` makes stored credentials unreadable. That is deliberate.
The platform says so clearly and asks for them again rather than pretending
nothing happened, and everything else in the database is unaffected.

`SECRET_KEY` is worth backing up separately from the database, somewhere the
database backup is not. Together they are equivalent to the plaintext keys.
Apart, neither is enough.

Passwords are different again. They are hashed with scrypt and are not
recoverable by anyone, including you.

## Moving to PostgreSQL

The schema is deliberately portable, so there is no migration script and no
special build.

```bash
pip install asyncpg   # already in the Docker image
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/ucsp
```

Start it once against the empty database and the tables are created. To carry
existing data across, export the workspace first and load it back in, or copy
the rows with whatever you normally use.

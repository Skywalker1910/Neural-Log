"""Verify the migration ledger is sound.

Run by CI on every pull request, and worth running by hand before adding a
migration.

R6 moved the daily checklist - the one feature used every day - out of JSON files
and into SQL. That kind of change is only safe if the migration mechanism itself
is trustworthy, and "it worked on my machine, which has already run every earlier
migration" is not evidence that it works on a fresh database.

So this checks three things a passing test suite does not:

  1. Every migration applies to an EMPTY database, in order, with no earlier
     state to lean on.
  2. Applying them twice is a no-op. init_db() runs at import time, which means
     on every gunicorn worker start - a migration that is not idempotent would
     corrupt data on the second boot rather than on the first.
  3. The ledger matches the directory. A file added without being applied, or a
     row recorded for a file that no longer exists, both mean the next deploy
     does something nobody predicted.
"""
import os
import sys
import sqlite3
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / 'migrations'


def _fail(message):
    print(f'FAIL  {message}')
    return 1


def main():
    migration_files = sorted(p.name for p in MIGRATIONS_DIR.glob('*.sql'))
    if not migration_files:
        return _fail('no migration files found - is migrations/ missing?')

    problems = 0
    original_cwd = os.getcwd()

    # ignore_cleanup_errors because the app opens SQLite handles that Windows
    # may still hold briefly; a stray temp directory is not worth failing over.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / 'check.db'
        os.environ['DATABASE'] = str(db_path)
        os.environ['SECRET_KEY'] = 'migration-check'
        os.environ['FLASK_DEBUG'] = '0'

        # The app writes artifacts/ relative to the cwd; keep that in the temp
        # directory so a CI run never touches the real one.
        os.chdir(tmp)
        sys.path.insert(0, str(PROJECT_ROOT))

        # Importing app runs init_db() for the first time.
        import app  # noqa: E402

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        applied = [row['version'] for row in
                   conn.execute('SELECT version FROM schema_migrations ORDER BY version')]

        expected = [name[:-4] for name in migration_files]
        if applied != expected:
            problems += _fail(
                f'ledger does not match migrations/\n'
                f'        on disk: {expected}\n'
                f'        applied: {applied}'
            )
        else:
            print(f'ok    {len(applied)} migrations applied to an empty database')

        # 2. Idempotency. init_db() runs on every worker start.
        before = dict(_table_counts(conn))
        conn.close()

        app.init_db()
        app.init_db()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        after = dict(_table_counts(conn))

        reapplied = [row['version'] for row in
                     conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
        if reapplied != applied:
            problems += _fail(
                f'running init_db() again changed the ledger: {applied} -> {reapplied}')
        else:
            print('ok    init_db() is idempotent across repeated calls')

        grew = {name: (before.get(name, 0), count)
                for name, count in after.items()
                if count != before.get(name, 0)}
        if grew:
            problems += _fail(
                'repeated init_db() changed row counts, so a migration or a '
                f'startup sync is not idempotent: {grew}')
        else:
            print(f'ok    row counts stable across {len(after)} tables')

        conn.close()
        # Step back out before the directory is removed: on Windows a directory
        # cannot be deleted while it is any process's working directory.
        os.chdir(original_cwd)

    return problems


def _table_counts(conn):
    """Row count per table, so a non-idempotent seed shows up as growth."""
    tables = [
        row['name'] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'")
    ]
    for name in sorted(tables):
        count = conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()['n']
        yield name, count


if __name__ == '__main__':
    failures = main()
    if failures:
        print(f'\n{failures} migration problem(s)')
        sys.exit(1)
    print('\nmigrations look sound')

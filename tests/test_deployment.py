"""The things that only start being true once more than one process is serving.

Everything here is invisible on a laptop. The dev server is one process with one
connection, behind nothing, reachable only by you - so a missing WAL pragma, a
health check nobody can call and a rate limiter that cannot tell clients apart
all look exactly like a working app.

They stop looking like one under gunicorn behind a reverse proxy, which is the
configuration nothing else in this suite exercises.
"""
import json
import pathlib
from datetime import datetime, timedelta, timezone

import security
from conftest import register


# --- health ------------------------------------------------------------------

def test_the_health_check_needs_no_session(raw_client):
    """A check that needs a session is a check that cannot run.

    Docker calls this from inside the container with no cookies at all, and an
    unhealthy verdict there takes the container out of rotation.
    """
    response = raw_client.get('/healthz')

    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'


def test_the_health_check_reads_the_database(app_module, monkeypatch):
    """Booted is not the same as working.

    A container whose Python started but whose database is missing, unreadable or
    on a volume that failed to mount is not healthy, and a check that only proves
    the process is alive would keep sending it traffic.
    """
    monkeypatch.setattr(app_module, 'DATABASE', '/nonexistent/path/neural_log.db')

    response = app_module.app.test_client().get('/healthz')

    assert response.status_code == 503
    assert response.get_json()['status'] == 'unhealthy'


def test_the_health_path_is_not_swallowed_by_the_spa(client):
    """The catch-all route serves index.html for anything it does not recognise.

    Without /healthz in SERVER_PREFIXES an unauthenticated probe would be
    redirected to the sign-in page, and Docker would read a 302 as a failure -
    so a perfectly healthy container would restart forever.
    """
    register(client)

    assert client.get('/healthz').content_type.startswith('application/json')


# --- concurrency --------------------------------------------------------------

def test_the_database_is_in_wal_mode(app_module):
    """Two workers, one SQLite file.

    In the default journal mode a single write locks the whole database, so one
    person saving a workout blocks everyone else's dashboard until it finishes.
    """
    conn = app_module.get_db_connection()
    try:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
    finally:
        conn.close()


def test_a_locked_database_waits_rather_than_failing(app_module):
    """`busy_timeout` is the difference between a pause and a 500.

    Without it, a connection that finds the database locked gives up instantly
    with "database is locked" - which surfaces to the user as a save that
    failed, for a lock that would have cleared in milliseconds.
    """
    conn = app_module.get_db_connection()
    try:
        assert conn.execute('PRAGMA busy_timeout').fetchone()[0] == 5000
    finally:
        conn.close()


# --- being behind a proxy ------------------------------------------------------

def test_the_client_address_comes_from_the_proxy_header(app_module):
    """Otherwise every request in production arrives from the same address.

    Caddy forwards to gunicorn over the container network, so `remote_addr` is
    Caddy. The per-IP rate limit would then count the entire internet as one
    client - locking everybody out after thirty failures between them.
    """
    with app_module.app.test_request_context(
        '/login', headers={'X-Forwarded-For': '203.0.113.7'}
    ):
        assert security.client_ip() == '203.0.113.7'


def test_only_the_last_hop_of_the_forwarded_chain_is_believed(app_module):
    """`X-Forwarded-For` is client-supplied, and the left of it is a free-text field.

    Anyone can send `X-Forwarded-For: 1.2.3.4`; the proxy appends the address it
    actually saw. Reading the leftmost entry - which is the obvious thing to do,
    and what most examples show - lets a caller pick a new identity per request
    and walk straight past the rate limiter.
    """
    with app_module.app.test_request_context(
        '/login', headers={'X-Forwarded-For': 'evil-spoof, 198.51.100.9'}
    ):
        assert security.client_ip() == '198.51.100.9'


def test_without_a_proxy_header_the_socket_address_is_used(app_module):
    """Local development, where there is no proxy and nothing to forward."""
    with app_module.app.test_request_context(
        '/login', environ_base={'REMOTE_ADDR': '192.0.2.44'}
    ):
        assert security.client_ip() == '192.0.2.44'


def test_a_request_with_no_address_at_all_still_counts(app_module):
    """The limiter must never key on a None.

    A WSGI environ is not obliged to carry REMOTE_ADDR, and the failure without a
    fallback is not a crash - it is `None` becoming a perfectly serviceable
    dictionary key, so every address-less request quietly shares one bucket.
    Which is the right behaviour, spelled out rather than stumbled into.
    """
    with app_module.app.test_request_context('/login'):
        assert security.client_ip() == 'unknown'


def test_the_proxy_is_only_trusted_in_production(app_module, monkeypatch):
    """ProxyFix rewrites `remote_addr` from a header anyone can set.

    On a laptop there is no proxy, so anything claiming to be one is lying. This
    is the one control that would be *less* safe if it were on everywhere.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    monkeypatch.setattr(security, 'IS_PRODUCTION', False)
    assert not isinstance(app_module.app.wsgi_app, ProxyFix)


# --- knowing whether the backups are happening --------------------------------
#
# The nightly timer is only reassuring if somebody would notice it stopping, and
# nobody runs `systemctl status` on a Tuesday. scripts/backup.sh writes its
# outcome beside the database and the admin page reads it back, which is the
# whole mechanism - so what matters here is that the app is careful about a file
# it does not write and cannot trust.

def write_status(app_module, **fields):
    payload = {
        'finished_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'ok': True,
        'message': 'backed up 2 users and 4 logged days',
        'offsite': True,
        'destination': 's3://bucket/db/2026/09/neural_log.db.gz',
        'bytes': 87400,
        'users': 2,
        'logged_days': 4,
        'local_copies': 14,
    }
    payload.update(fields)

    path = pathlib.Path(app_module.DATABASE).resolve().parent / 'backup-status.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_no_status_file_is_unknown_rather_than_broken(app_module):
    """A fresh instance has never run a backup, and that is not a failure.

    Reporting "FAILED" at somebody on their first afternoon teaches them to
    ignore the indicator, which costs more than saying nothing would.
    """
    status = app_module.read_backup_status()

    assert status['known'] is False
    assert 'reason' in status


def test_a_recent_successful_backup_reads_as_healthy(app_module):
    write_status(app_module)

    status = app_module.read_backup_status()

    assert status['known'] is True
    assert status['ok'] is True
    assert status['offsite'] is True
    assert status['stale'] is False
    assert status['age_hours'] < 1


def test_a_failed_run_is_reported_as_failed(app_module):
    """The script writes a status on failure too, which is the point of it.

    A script that only reports success is a script whose silence means nothing -
    you cannot tell "it worked" from "it never ran".
    """
    write_status(app_module, ok=False, message='no database at ./data/neural_log.db')

    status = app_module.read_backup_status()

    assert status['known'] is True
    assert status['ok'] is False
    assert 'no database' in status['message']


def test_an_old_backup_is_stale_even_though_it_succeeded(app_module):
    """The dangerous failure is the timer that quietly stopped firing.

    Nothing reports an error, the last run says `ok`, and it is three weeks old.
    """
    long_ago = datetime.now(timezone.utc) - timedelta(hours=72)
    write_status(app_module, finished_at=long_ago.strftime('%Y-%m-%dT%H:%M:%SZ'))

    status = app_module.read_backup_status()

    assert status['ok'] is True
    assert status['stale'] is True
    assert status['age_hours'] > 70


def test_local_only_backups_are_reported_as_not_offsite(app_module):
    """Succeeded and safe are different claims.

    A snapshot written next to the database protects against deleting the wrong
    thing and not at all against losing the instance, so `ok` alone would be a
    misleading green light.
    """
    write_status(app_module, offsite=False, destination='local-only')

    status = app_module.read_backup_status()

    assert status['ok'] is True
    assert status['offsite'] is False


def test_an_unreadable_status_file_does_not_take_the_page_down(app_module):
    """Written by a shell script this app does not run, so it may be anything.

    A half-written file caught mid-rename, a disk that filled at the wrong
    moment - none of that should turn the admin page into a 500.
    """
    path = pathlib.Path(app_module.DATABASE).resolve().parent / 'backup-status.json'
    path.write_text('{"finished_at": "2026-09-2', encoding='utf-8')

    status = app_module.read_backup_status()

    assert status['known'] is False


def test_a_status_file_with_a_nonsense_timestamp_still_reads(app_module):
    """Age becomes unknown; everything else is still worth showing."""
    write_status(app_module, finished_at='last Tuesday')

    status = app_module.read_backup_status()

    assert status['known'] is True
    assert status['age_hours'] is None
    assert status['stale'] is False


def test_the_admin_overview_carries_the_backup_status(client, app_module):
    """Folded into the existing call rather than a new one - the admin page
    already fetches this, and a second round trip buys nothing."""
    register(client)
    write_status(app_module)

    payload = client.get('/api/admin/stats').get_json()

    assert payload['backup']['ok'] is True
    assert payload['backup']['offsite'] is True


def test_a_non_admin_cannot_read_the_backup_status(client):
    register(client, username='owner')
    client.post('/logout')
    register(client, username='friend')

    assert client.get('/api/admin/stats').status_code == 403


# --- knowing what is running ---------------------------------------------------

def test_the_health_check_reports_the_version(raw_client, app_module):
    """The deploy ships images tagged by commit SHA.

    Without this there is no way to ask a running instance what release it is,
    which is the first question when production looks wrong.
    """
    payload = raw_client.get('/healthz').get_json()

    assert payload['version'] == app_module.__version__
    assert payload['version'] != 'unknown'


def test_the_two_version_markers_agree(app_module):
    """VERSION and frontend/package.json drift the moment nothing checks."""
    root = pathlib.Path(app_module.__file__).resolve().parent
    declared = (root / 'VERSION').read_text(encoding='utf-8').strip()
    package = json.loads((root / 'frontend' / 'package.json').read_text(encoding='utf-8'))

    assert package['version'] == declared


def test_a_missing_version_file_does_not_stop_the_app(app_module, monkeypatch):
    """An honest 'unknown' beats refusing to boot over a label."""
    monkeypatch.setattr(app_module, 'PROJECT_ROOT', pathlib.Path('/nonexistent'))

    assert app_module._read_version() == 'unknown'


def test_the_health_check_reports_the_commit(raw_client, app_module):
    """Which build is running, not just which release.

    The version only moves when somebody cuts one, so between releases it cannot
    distinguish two very different images - and CI compares this against the
    commit it just built, which is what turns a silent rollback into a red X.
    """
    payload = raw_client.get('/healthz').get_json()

    assert 'commit' in payload
    assert payload['commit'] == app_module.__commit__


def test_a_checkout_reports_an_unknown_commit(app_module):
    """CI bakes it in at build time; a working tree is not any one commit, and
    saying 'unknown' is more honest than inventing one."""
    assert app_module.__commit__ == 'unknown'

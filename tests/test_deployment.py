"""The things that only start being true once more than one process is serving.

Everything here is invisible on a laptop. The dev server is one process with one
connection, behind nothing, reachable only by you - so a missing WAL pragma, a
health check nobody can call and a rate limiter that cannot tell clients apart
all look exactly like a working app.

They stop looking like one under gunicorn behind a reverse proxy, which is the
configuration nothing else in this suite exercises.
"""
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
    assert response.get_json() == {'status': 'ok'}


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

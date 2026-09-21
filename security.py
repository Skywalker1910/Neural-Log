"""What has to be true before this app is reachable from the open internet.

Neural Log has only ever run on localhost, and localhost forgives a lot: a secret
key committed to a public repo, registration open to whoever finds the page, a
login form you can guess at forever. None of that is a bug on a laptop. All of it
is a bug the moment the app has a domain.

The list lives in one module rather than as seven patches scattered through
app.py, because the list is the point - it is the thing to re-read before a
deploy, and a checklist you have to reassemble by grepping is not a checklist.

## One switch, and which way it defaults

Everything keys off `NEURAL_LOG_ENV`. Development is the default and production
is opt-in, which looks like the unsafe way round and is not: the development path
has to work with no setup at all, so if production were the default then getting
the app to run locally would mean relaxing something, and a relaxation set once
in a shell is a relaxation nobody remembers. Opting *in* to strict means the
strictness is written down in the deploy config, where it can be read.

## What the tests actually exercise

CSRF, login rate limiting and the structured error responses are on in every
environment, so the suite hits them several hundred times a run instead of
production discovering them. Only the three that genuinely cannot work offline
differ, and each differs for a concrete reason:

| Control | Development | Production |
|---|---|---|
| `SECRET_KEY` | fixed dev literal | required; boot fails without it |
| Cookie `Secure` flag | off - there is no TLS on localhost | on |
| Registration | open | invite code required |

The dev secret is a fixed string rather than a random one per boot, which is the
less obvious choice. A random key is strictly safer, and it also logs you out of
your own app every time the reloader restarts - which is most of a minute, many
times an hour, for a threat model of "someone has a shell on my laptop".
"""
import os
import secrets

from flask import g, jsonify, make_response, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

# --- environment -------------------------------------------------------------

ENV = (os.environ.get('NEURAL_LOG_ENV') or 'development').strip().lower()
IS_PRODUCTION = ENV == 'production'

#: The literal that used to be the `SECRET_KEY` fallback in every environment.
#: It is still here, still published in a public repo, and now unreachable in
#: production - which is the whole of the change.
DEV_SECRET_KEY = 'dev-only-insecure-secret-key'


class ConfigurationError(RuntimeError):
    """A production setting is missing, and the app must not start without it.

    Raised at import time rather than on first request. A boot that fails loudly
    is recoverable in thirty seconds; a boot that succeeds with a guessable
    session key is a problem nobody notices until it matters.
    """


def _required(name, hint):
    value = (os.environ.get(name) or '').strip()
    if not value:
        raise ConfigurationError(
            f'{name} must be set when NEURAL_LOG_ENV=production. {hint}'
        )
    return value


def resolve_secret_key():
    """The session signing key, or a refusal to boot.

    Flask signs the session cookie with this. Anyone who knows it can mint a
    cookie for any user id, so a published constant is not a weak key - it is no
    key at all.
    """
    explicit = (os.environ.get('SECRET_KEY') or '').strip()
    if explicit:
        return explicit
    if IS_PRODUCTION:
        raise ConfigurationError(
            'SECRET_KEY must be set when NEURAL_LOG_ENV=production. '
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return DEV_SECRET_KEY


# --- registration ------------------------------------------------------------

OPEN, INVITE, CLOSED = 'open', 'invite', 'closed'
REGISTRATION_MODES = (OPEN, INVITE, CLOSED)


def registration_mode():
    """How new accounts are created: open, invite, or closed.

    Production defaults to invite rather than closed. Closed is safer and means
    every new friend is a shell session and a manual INSERT, which in practice
    means the app has no new users - the friction lands on the owner, not on an
    attacker, because an attacker was never going to register anyway.
    """
    raw = (os.environ.get('REGISTRATION_MODE') or '').strip().lower()
    if raw in REGISTRATION_MODES:
        return raw
    return INVITE if IS_PRODUCTION else OPEN


def registration_code():
    """The shared invite code, when one is required."""
    if registration_mode() != INVITE:
        return (os.environ.get('REGISTRATION_CODE') or '').strip()
    if IS_PRODUCTION:
        return _required(
            'REGISTRATION_CODE',
            'Set it to a phrase you can send a friend, or set REGISTRATION_MODE=closed.',
        )
    return (os.environ.get('REGISTRATION_CODE') or '').strip()


def check_registration(payload):
    """`(ok, message, status)` for an attempt to create an account.

    Returns rather than raises because the caller has a database connection open
    and one shape of error response to build.
    """
    mode = registration_mode()

    if mode == CLOSED:
        return False, 'Registration is closed. Ask the owner for an account.', 403

    if mode == INVITE:
        expected = registration_code()
        supplied = (payload.get('invite_code') or '').strip()
        if not supplied:
            return False, 'An invite code is required.', 403
        # compare_digest rather than ==, so the failure takes the same time
        # whether the first character is wrong or the last one is.
        if not expected or not secrets.compare_digest(supplied, expected):
            return False, 'That invite code is not valid.', 403

    return True, None, None


def grants_admin(username, existing_user_count):
    """Whether this registration should create an administrator.

    The old rule was "whoever registers first", which is fine on a laptop and
    means that on a fresh production database the first stranger through the door
    owns the app. `ADMIN_USERNAME` names the account instead, so the race is not
    a race. Without it the old rule stands, because locally there is no race.
    """
    named = (os.environ.get('ADMIN_USERNAME') or '').strip()
    if named:
        return username == named
    return existing_user_count == 0


# --- session cookies ---------------------------------------------------------

def session_config():
    """Cookie flags, and why each one is set.

    `HttpOnly` keeps the session cookie out of `document.cookie`, so an injected
    script cannot read it. `SameSite=Lax` means the browser will not attach it to
    a cross-site POST at all, which is most of CSRF handled before the token
    below is even checked. `Secure` says never send it over plain HTTP - true in
    production, impossible on localhost, which is the one flag that has to vary.
    """
    return {
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_COOKIE_SECURE': IS_PRODUCTION,
        # Sessions are permanent so a friend checking in every few days is not
        # logged out between visits; 30 days is the balance against a forgotten
        # session on a shared machine.
        'PERMANENT_SESSION_LIFETIME': 60 * 60 * 24 * 30,
        # A ceiling on request bodies, which until now there was not one of.
        #
        # Every other endpoint here posts a small JSON object, so this was
        # theoretical: an unbounded body is a way to make a 1 GB instance run out
        # of memory, but nobody had a reason to send one. Label scanning gives
        # them a reason - it posts a photograph - so the limit goes in alongside
        # it rather than after the first time somebody uploads a video.
        #
        # 8 MB is generous for a resized photo (the client sends about 300 KB)
        # and small enough that a handful of concurrent uploads cannot exhaust
        # the box. Werkzeug rejects anything larger before reading the body.
        'MAX_CONTENT_LENGTH': 8 * 1024 * 1024,
    }


# --- CSRF --------------------------------------------------------------------

CSRF_COOKIE = 'csrf_token'
CSRF_HEADER = 'X-CSRF-Token'
CSRF_FORM_FIELD = 'csrf_token'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})


def _issue_csrf_token():
    """This request's token, generated once and reused if asked for twice."""
    token = getattr(g, '_csrf_token', None)
    if token is None:
        token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        g._csrf_token = token
    return token


def _submitted_csrf_token():
    header = request.headers.get(CSRF_HEADER)
    if header:
        return header
    # The classic Jinja app posts JSON through hand-rolled fetch calls, but its
    # forms are ordinary forms, and a form cannot set a header.
    return request.form.get(CSRF_FORM_FIELD)


def init_csrf(app):
    """Double-submit CSRF: the token rides in a cookie and must come back in a header.

    The double-submit pattern works because of the same-origin policy, not
    because the token is secret. A page on another origin can *cause* your
    browser to send a request carrying your cookies, but it cannot read those
    cookies to copy one into a header - so a request that echoes the cookie back
    must have been made by a page on this origin.

    That is also why the cookie is deliberately not HttpOnly. It is the one
    cookie the app's own JavaScript has to read, and it is not a credential:
    knowing it grants nothing, since the session cookie is what authenticates and
    that one stays unreadable.

    `SameSite=Lax` on the session cookie already blocks the cross-site POST this
    defends against, in every browser released in years. This is the second lock:
    SameSite is one header away from being wrong, and browsers have carved
    exceptions into it before.
    """

    @app.before_request
    def _verify_csrf():
        if request.method in SAFE_METHODS:
            return None

        cookie = request.cookies.get(CSRF_COOKIE)
        submitted = _submitted_csrf_token()

        if not cookie or not submitted or not secrets.compare_digest(cookie, submitted):
            return jsonify({
                'success': False,
                'error': 'csrf_failed',
                'message': 'Your session token was missing or stale. Reload the page and try again.',
            }), 403

        return None

    @app.after_request
    def _set_csrf_cookie(response):
        token = _issue_csrf_token()
        if request.cookies.get(CSRF_COOKIE) != token:
            response.set_cookie(
                CSRF_COOKIE,
                token,
                # Readable by JavaScript on purpose - see above.
                httponly=False,
                samesite='Lax',
                secure=IS_PRODUCTION,
                max_age=60 * 60 * 24 * 30,
                path='/',
            )
        return response

    @app.context_processor
    def _csrf_in_templates():
        """`{{ csrf_token() }}` for the Jinja app's forms."""
        return {'csrf_token': _issue_csrf_token}


# --- login rate limiting -----------------------------------------------------

#: Failures are counted inside a sliding window this many seconds wide.
LOCKOUT_WINDOW_SECONDS = 15 * 60

#: Per username. Ten is generous for someone who genuinely forgot, and useless
#: for a dictionary: at ten guesses per quarter hour a four-word passphrase
#: outlasts the sun.
MAX_FAILURES_PER_USERNAME = 10

#: Per source address, across every username it tried. This is the one that stops
#: credential spraying - a hundred accounts guessed once each never trips the
#: per-username limit.
MAX_FAILURES_PER_IP = 30


def client_ip():
    """The caller's address, trusting exactly one proxy hop.

    Behind a load balancer every request arrives from the balancer, so the real
    address is in `X-Forwarded-For` - and that header is client-supplied, so the
    leftmost entry is whatever an attacker felt like writing. The rightmost is
    the one the proxy itself appended, and is the only one worth reading.
    """
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[-1].strip()
    return request.remote_addr or 'unknown'


def _cutoff_iso(conn):
    """The window boundary, in the format SQLite wrote the timestamps in."""
    row = conn.execute(
        "SELECT datetime('now', ?) AS cutoff", (f'-{LOCKOUT_WINDOW_SECONDS} seconds',)
    ).fetchone()
    return row['cutoff']


def login_retry_after(conn, username, ip):
    """Seconds the caller must wait, or 0 if they may try now."""
    cutoff = _cutoff_iso(conn)

    for column, value, limit in (
        ('username', username, MAX_FAILURES_PER_USERNAME),
        ('ip', ip, MAX_FAILURES_PER_IP),
    ):
        row = conn.execute(
            f'SELECT COUNT(*) AS failures, MIN(attempted_at) AS oldest '
            f'FROM login_attempts WHERE {column} = ? AND attempted_at > ?',
            (value, cutoff),
        ).fetchone()

        if row and row['failures'] >= limit:
            # The lock lifts when the oldest failure falls out of the window, so
            # the wait shrinks as it ages rather than resetting on every try.
            aged = conn.execute(
                "SELECT CAST(strftime('%s', ?, ?) - strftime('%s', 'now') AS INTEGER) AS wait",
                (row['oldest'], f'+{LOCKOUT_WINDOW_SECONDS} seconds'),
            ).fetchone()
            return max(1, aged['wait'] if aged and aged['wait'] is not None else 60)

    return 0


def record_login_failure(conn, username, ip):
    conn.execute(
        'INSERT INTO login_attempts (username, ip) VALUES (?, ?)', (username, ip)
    )
    # Housekeeping on write, so the table stays the size of the window rather
    # than the size of history. No cron, no growth.
    conn.execute('DELETE FROM login_attempts WHERE attempted_at <= ?', (_cutoff_iso(conn),))
    conn.commit()


def clear_login_failures(conn, username, ip):
    """A correct password means the run of failures is over."""
    conn.execute(
        'DELETE FROM login_attempts WHERE username = ? OR ip = ?', (username, ip)
    )
    conn.commit()


def rate_limit_response(retry_after):
    response = make_response(jsonify({
        'success': False,
        'error': 'rate_limited',
        'message': (
            f'Too many failed sign-ins. Try again in about '
            f'{max(1, round(retry_after / 60))} minute(s).'
        ),
    }), 429)
    response.headers['Retry-After'] = str(retry_after)
    return response


# --- error responses ---------------------------------------------------------

def _wants_json():
    if request.path.startswith('/api/'):
        return True
    return request.accept_mimetypes.best == 'application/json'


def init_error_handlers(app):
    """Errors that say what happened without saying how the app is built.

    Flask's default 500 page in debug mode is an interactive console; with debug
    off it is a bare HTML page. Neither is useful to a fetch() call, and the
    first is a remote shell. Every unhandled exception becomes the same JSON
    shape the client already knows how to read, and the detail goes to the log.
    """

    @app.errorhandler(HTTPException)
    def _http_error(error):
        if not _wants_json():
            return error
        return jsonify({
            'success': False,
            'error': error.name.lower().replace(' ', '_'),
            'message': error.description,
        }), error.code

    @app.errorhandler(Exception)
    def _unhandled(error):
        # Under the test runner and the local reloader, let it fly. A catch-all
        # that turns every bug into a tidy 500 is exactly what you do not want
        # while writing the bug: pytest would report `assert 500 == 200` where it
        # used to report the traceback and the line number.
        if app.testing or app.debug:
            raise error

        # exc_info so the traceback reaches the log, which is where it belongs -
        # the response says only that something broke.
        app.logger.exception('Unhandled exception on %s %s', request.method, request.path)
        if not _wants_json():
            raise error
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'Something went wrong on our side. The failure has been logged.',
        }), 500


# --- wiring ------------------------------------------------------------------

def init_security(app):
    """Apply every control above. Called once, from app.py, at import time."""
    app.config['SECRET_KEY'] = resolve_secret_key()
    app.config.update(session_config())

    if IS_PRODUCTION:
        # In production a reverse proxy terminates TLS and forwards to gunicorn
        # over plain HTTP on localhost. Without this, Flask believes every
        # request arrived unencrypted from the proxy's own address - so
        # `url_for(_external=True)` builds http:// links that a Secure cookie
        # will not be sent to, and the rate limiter counts the whole internet as
        # one client.
        #
        # Exactly one hop is trusted, because exactly one is deployed. These
        # headers are client-supplied; trusting two proxies when one exists lets
        # a caller forge the entry the app then reads as the real address.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Touched at startup so a missing REGISTRATION_CODE in production fails the
    # boot rather than the first friend who tries to sign up.
    registration_code()

    init_csrf(app)
    init_error_handlers(app)

    @app.before_request
    def _keep_session_alive():
        session.permanent = True

    return app

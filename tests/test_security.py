"""The controls that only matter once the app has a domain.

Every other test file asks whether a feature works. This one asks whether the
app survives contact with people who are not the owner - which is a different
question, and the one that has never been asked before because until now the app
only ran on localhost.

Note what is *not* here: a test that CSRF is enforced on each of the seventy-odd
write endpoints. That is not missing, it is the rest of the suite. The guard is a
`before_request` hook, so every one of the four hundred other tests goes through
it, and `conftest.CsrfClient` is what makes them pass - delete the hook and they
keep passing, delete the token from the client and several hundred fail.
"""
import pytest

import security
from conftest import login, register


# --- CSRF --------------------------------------------------------------------

def test_a_write_without_a_token_is_refused(raw_client):
    """The whole point, stated once."""
    response = raw_client.post('/register', json={'username': 'mallory', 'password': 'password123'})

    assert response.status_code == 403
    assert response.get_json()['error'] == 'csrf_failed'


def test_a_write_with_somebody_elses_token_is_refused(raw_client):
    """Having *a* token is not the test; echoing back *your* cookie is.

    This is the attack the double-submit pattern actually defends against: a
    third-party page can make your browser send a request with your cookies
    attached, but it cannot read those cookies, so it can only guess at the
    header - and a guess is what this is.
    """
    raw_client.get('/login')  # issues a real cookie

    response = raw_client.post(
        '/register',
        json={'username': 'mallory', 'password': 'password123'},
        headers={'X-CSRF-Token': 'not-the-one-in-your-cookie'},
    )

    assert response.status_code == 403
    assert response.get_json()['error'] == 'csrf_failed'


def test_reading_needs_no_token_and_hands_one_out(raw_client):
    """A GET is safe, so it is never blocked - and it is how you get a token."""
    response = raw_client.get('/login')

    assert response.status_code == 200
    assert raw_client.get_cookie('csrf_token') is not None


def test_the_token_cookie_is_readable_by_javascript(raw_client):
    """Deliberately not HttpOnly, which looks wrong and is not.

    The client has to read this one to put it in a header. It is safe to expose
    because it authenticates nothing - the session cookie does that, and it stays
    unreadable. Locking this one down would break the mechanism it exists for.
    """
    raw_client.get('/login')

    assert raw_client.get_cookie('csrf_token').http_only is False


def test_the_session_cookie_is_not_readable_by_javascript(client):
    register(client)

    assert client.get_cookie('session').http_only is True
    assert client.get_cookie('session').same_site == 'Lax'


# --- login rate limiting -----------------------------------------------------

def guess(client, times, username='alice'):
    last = None
    for _ in range(times):
        last = client.post('/login', json={'username': username, 'password': 'wrong'})
    return last


def test_guessing_is_allowed_up_to_the_limit(client):
    register(client)
    client.post('/logout')

    assert guess(client, security.MAX_FAILURES_PER_USERNAME - 1).status_code == 401


def test_past_the_limit_the_door_closes(client):
    register(client)
    client.post('/logout')

    response = guess(client, security.MAX_FAILURES_PER_USERNAME + 1)

    assert response.status_code == 429
    assert response.get_json()['error'] == 'rate_limited'
    assert int(response.headers['Retry-After']) > 0


def test_the_right_password_is_refused_too_while_locked_out(client):
    """The lock is on the attempt, not on the guess.

    Checking the password first and only then the limit would leak the answer:
    whoever is guessing learns they got it right, and learns it from a response
    that was supposed to tell them nothing.
    """
    register(client)
    client.post('/logout')
    guess(client, security.MAX_FAILURES_PER_USERNAME + 1)

    assert login(client).status_code == 429


def test_getting_in_clears_the_record(client):
    register(client)
    client.post('/logout')

    guess(client, security.MAX_FAILURES_PER_USERNAME - 1)
    assert login(client).status_code == 200

    client.post('/logout')
    # A fresh allowance, because the run of failures ended.
    assert guess(client, security.MAX_FAILURES_PER_USERNAME - 1).status_code == 401


def test_spraying_many_usernames_from_one_address_is_caught(client):
    """The per-username limit alone misses the attack that matters.

    Guessing one password against a hundred accounts never trips a per-account
    counter. At 2-5 users the usernames are the easy half of the guess, so the
    per-address limit is the one doing the work.
    """
    register(client)
    client.post('/logout')

    last = None
    for index in range(security.MAX_FAILURES_PER_IP + 1):
        last = client.post(
            '/login', json={'username': f'stranger{index}', 'password': 'hunter2'}
        )

    assert last.status_code == 429


def test_a_failure_is_not_a_username_oracle(client):
    """Same message, same status, whether or not the account exists."""
    register(client)
    client.post('/logout')

    real = client.post('/login', json={'username': 'alice', 'password': 'wrong'})
    fake = client.post('/login', json={'username': 'nobody-here', 'password': 'wrong'})

    assert real.status_code == fake.status_code == 401
    assert real.get_json()['message'] == fake.get_json()['message']


# --- registration ------------------------------------------------------------

def test_registration_is_open_by_default_in_development(client):
    assert register(client).status_code == 201


def test_invite_mode_wants_a_code(client, monkeypatch):
    monkeypatch.setenv('REGISTRATION_MODE', 'invite')
    monkeypatch.setenv('REGISTRATION_CODE', 'open-sesame')

    refused = register(client)

    assert refused.status_code == 403
    assert 'invite code' in refused.get_json()['message'].lower()


def test_invite_mode_wants_the_right_code(client, monkeypatch):
    monkeypatch.setenv('REGISTRATION_MODE', 'invite')
    monkeypatch.setenv('REGISTRATION_CODE', 'open-sesame')

    assert register(client, invite_code='open-barley').status_code == 403
    assert register(client, invite_code='open-sesame').status_code == 201


def test_closed_means_closed(client, monkeypatch):
    monkeypatch.setenv('REGISTRATION_MODE', 'closed')

    refused = register(client, invite_code='anything')

    assert refused.status_code == 403
    assert 'closed' in refused.get_json()['message'].lower()


def test_production_defaults_to_invite_only(monkeypatch):
    """Nobody has to remember to close the door.

    The failure this prevents is the quiet one: deploy, forget the setting, and
    the app is open to whoever finds the URL - with the first stranger through it
    becoming an administrator.
    """
    monkeypatch.delenv('REGISTRATION_MODE', raising=False)
    monkeypatch.setattr(security, 'IS_PRODUCTION', True)

    assert security.registration_mode() == security.INVITE


# --- who gets to be an administrator -----------------------------------------

def test_first_registration_is_admin_when_nobody_is_named(client, monkeypatch):
    monkeypatch.delenv('ADMIN_USERNAME', raising=False)

    assert register(client).get_json()['is_admin'] is True


def test_naming_an_admin_stops_the_land_grab(client, monkeypatch):
    """`ADMIN_USERNAME` turns a race into a decision.

    On a fresh production database, first-past-the-post means the first person to
    find the sign-up form owns the app. Naming the account removes the race, and
    then it does not matter who gets there first.
    """
    monkeypatch.setenv('ADMIN_USERNAME', 'aditya')

    assert register(client, username='opportunist').get_json()['is_admin'] is False
    client.post('/logout')
    assert register(client, username='aditya').get_json()['is_admin'] is True


# --- the secret key ----------------------------------------------------------

def test_production_will_not_boot_without_a_secret_key(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(security, 'IS_PRODUCTION', True)

    with pytest.raises(security.ConfigurationError, match='SECRET_KEY'):
        security.resolve_secret_key()


def test_development_still_boots_with_no_configuration(monkeypatch):
    """The dev fallback is the whole reason this is not simply os.environ[...]."""
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setattr(security, 'IS_PRODUCTION', False)

    assert security.resolve_secret_key() == security.DEV_SECRET_KEY


def test_the_published_fallback_can_never_be_the_production_key(monkeypatch):
    """The literal is in a public repo. Reaching it in production is the bug."""
    monkeypatch.setattr(security, 'IS_PRODUCTION', True)
    monkeypatch.setenv('SECRET_KEY', 'a-real-one')

    assert security.resolve_secret_key() != security.DEV_SECRET_KEY


# --- signing out -------------------------------------------------------------

def test_a_get_to_logout_changes_nothing(client):
    """It used to. Any page could sign you out with an <img> tag."""
    register(client)

    response = client.get('/logout')

    assert response.status_code == 200
    assert client.get('/api/current-user').status_code == 200


def test_a_post_to_logout_signs_you_out(client):
    register(client)

    assert client.post('/logout').status_code in (200, 302)
    assert client.get('/api/current-user').status_code == 302


# --- the leaderboard opt-out -------------------------------------------------

def test_everyone_is_on_the_leaderboard_by_default(client):
    register(client, username='alice')
    client.post('/logout')
    register(client, username='bob')

    names = [row['username'] for row in client.get('/api/leaderboard/overall').get_json()['entries']]

    assert names == ['alice', 'bob']


def test_opting_out_removes_you_for_everyone(client):
    register(client, username='alice')
    client.put('/api/user/privacy', json={'leaderboard_opt_out': True})
    client.post('/logout')

    register(client, username='bob')
    payload = client.get('/api/leaderboard/overall').get_json()

    assert [row['username'] for row in payload['entries']] == ['bob']
    # Bob is not hidden; he is simply looking at a board alice left.
    assert payload['viewer_hidden'] is False


def test_the_board_admits_that_you_are_missing_from_it(client):
    """Otherwise opting out looks like a bug the next time you visit."""
    register(client, username='alice')
    client.put('/api/user/privacy', json={'leaderboard_opt_out': True})

    payload = client.get('/api/leaderboard/overall').get_json()

    assert payload['viewer_hidden'] is True
    assert payload['entries'] == []


def test_opting_back_in_puts_you_back(client):
    register(client, username='alice')

    client.put('/api/user/privacy', json={'leaderboard_opt_out': True})
    client.put('/api/user/privacy', json={'leaderboard_opt_out': False})

    assert client.get('/api/current-user').get_json()['leaderboard_opt_out'] is False
    assert len(client.get('/api/leaderboard/overall').get_json()['entries']) == 1


# --- error responses ---------------------------------------------------------

def test_an_unknown_api_path_answers_in_json(client):
    """A fetch() call cannot read an HTML 404, and says so as a parse error.

    Which is how a typo'd endpoint used to surface: not as "404", but as
    "unexpected token < in JSON at position 0", three layers away from the cause.
    """
    response = client.get('/api/no-such-thing')

    assert response.status_code == 404
    assert response.content_type.startswith('application/json')
    assert response.get_json()['error'] == 'not_found'


def test_a_rejected_write_answers_in_json_too(raw_client):
    response = raw_client.delete('/api/activities/1')

    assert response.content_type.startswith('application/json')
    assert 'message' in response.get_json()


def test_a_crash_says_nothing_about_how_the_app_is_built(app_module):
    """No traceback, no module names, no SQL - just that it broke, and an id in the log.

    Flask's default 500 with debug off is a bare HTML page, and with debug on it
    is an interactive Python console. The first cannot be read by `fetch`; the
    second is a remote shell.
    """
    @app_module.app.route('/api/definitely-explodes')
    def _explode():
        raise ZeroDivisionError('the connection string was ' + 'hunter2')

    # Testing and debug both let exceptions through on purpose, so the handler
    # only does its job with both off - which is how it runs in production.
    app_module.app.config.update(TESTING=False, DEBUG=False, PROPAGATE_EXCEPTIONS=False)
    response = app_module.app.test_client().get('/api/definitely-explodes')

    assert response.status_code == 500
    assert response.get_json() == {
        'success': False,
        'error': 'internal_error',
        'message': 'Something went wrong on our side. The failure has been logged.',
    }
    assert b'hunter2' not in response.data
    assert b'ZeroDivisionError' not in response.data

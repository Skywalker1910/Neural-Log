# Security

Neural Log has only ever run on localhost, and localhost forgives a lot. A secret
key committed to a public repo is fine when the only person who can reach the app
is the person who wrote it. Registration open to anyone is fine when "anyone"
means you. A login form you can guess at forever is fine when there is nothing on
the other side of the network to guess from.

All of it stops being fine the moment the app has a domain. This is the list of
what changed, and why each item is on it.

Implementation lives in [`security.py`](../security.py); the tests are
[`tests/test_security.py`](../tests/test_security.py).

## One switch

Everything keys off `NEURAL_LOG_ENV`. Development is the default and production
is opt-in, which looks like the wrong way round and is not: the development path
has to work with no setup at all, so with production as the default, getting the
app to run locally would mean *relaxing* something — and a relaxation set once in
a shell is a relaxation nobody remembers. Opting in to strict means the
strictness is written down in the deploy config, where it can be read back.

The three controls that differ between the two, and why each one has to:

| Control | Development | Production |
|---|---|---|
| `SECRET_KEY` | fixed dev literal | required; the app refuses to boot without it |
| Cookie `Secure` flag | off — there is no TLS on localhost | on |
| Registration | open | invite code required |

Everything else — CSRF, rate limiting, the error shape, the leaderboard opt-out —
is identical in both. That is deliberate. A control that is off in development is
a control exercised only by production, and production is the worst place to
discover it was wrong.

## The seven

### 1. No hard-coded secret fallback

Flask signs the session cookie with `SECRET_KEY`. Anyone who knows it can mint a
cookie claiming to be any user id, so a published constant is not a weak key —
it is no key at all, and the constant was in this public repository.

The literal still exists, still published, and is now unreachable in production:
`resolve_secret_key()` raises `ConfigurationError` at import rather than falling
back. A boot that fails loudly is recoverable in thirty seconds; a boot that
succeeds with a guessable session key is a problem nobody notices until it
matters.

### 2. Registration is closed unless you say otherwise

`REGISTRATION_MODE` is `open`, `invite` or `closed`, and defaults to **invite** in
production. Forgetting to configure it therefore shuts the door rather than
opening it.

Invite rather than closed is the default for a practical reason. Closed is safer
and means every new friend is a shell session and a manual `INSERT`, which in
practice means the app never gets new users — the friction lands on the owner,
not on an attacker, because an attacker was never going to register anyway.

The code is compared with `secrets.compare_digest`, so a wrong guess takes the
same time whether the first character is wrong or the last one is.

### 3. Admin is assigned, not raced for

The old rule was "whoever registers first becomes admin". On a laptop that is
you. On a fresh production database it is whoever finds the sign-up form first,
and they then own the app.

`ADMIN_USERNAME` names the account instead, so there is no race to win. Without
it the old rule stands, because locally there is no race.

### 4. Login rate limiting

Ten failures per username and thirty per source address, inside a sliding
fifteen-minute window. Both are needed and they catch different things: the
per-username limit stops a dictionary run against one account, and the per-IP
limit stops credential spraying — one password guessed against a hundred
usernames never trips a per-account counter, and at 2–5 users the usernames are
the easy half of the guess.

Two details that are easy to get wrong:

- **The limit is checked before the password is.** Checking the password first
  would leak the answer — whoever is guessing learns they got it right, from a
  response that was supposed to tell them nothing.
- **The counter is a table, not a variable.** An in-process counter is the
  obvious cheap answer right up until the app runs under gunicorn with four
  workers, at which point there are four counters, each allowing the full quota,
  and the limit is silently four times what it says.

A successful login clears the record, so the table holds "failures since this
last worked" rather than a login history — which is both the number the limiter
wants and less to leak. Rows older than the window are deleted on write, so it
stays the size of the window rather than the size of history.

### 5. CSRF, and `GET /logout`

Two layers, because the outer one is one header away from being wrong.

**`SameSite=Lax` on the session cookie** means the browser will not attach it to
a cross-site POST at all. In every browser released in years, that alone is most
of CSRF handled.

**A double-submit token** is the second lock. The server sets a `csrf_token`
cookie; the client echoes it in an `X-CSRF-Token` header; the two must match.
This works because of the same-origin policy, not because the token is secret: a
page on another origin can *cause* your browser to send a request carrying your
cookies, but it cannot *read* those cookies to copy one into a header. So a
request that echoes the cookie back must have come from a page on this origin.

That is also why this one cookie is deliberately **not** `HttpOnly`. It is the
only cookie the app's own JavaScript has to read, and it is not a credential —
knowing it grants nothing, because the session cookie is what authenticates and
that one stays unreadable.

`GET /logout` used to clear the session, which meant any page anywhere could sign
you out with an invisible `<img src="https://neurallog.../logout">`. A nuisance
rather than a breach, and also the plainest possible example of the rule the rest
of this section enforces: a request the user did not make should not change their
state. `POST` now does the signing out; `GET` renders a confirmation, so old
links and bookmarks still land somewhere sensible.

### 6. Session cookie flags

`HttpOnly` keeps the session cookie out of `document.cookie`, so an injected
script cannot read it. `SameSite=Lax` is described above. `Secure` means never
send it over plain HTTP — true in production, impossible on localhost, and the
one flag that has to vary by environment.

Sessions are permanent with a 30-day lifetime, so a friend checking in every few
days is not signed out between visits.

### 7. Structured error responses

Flask's default 500 with debug off is a bare HTML page; with debug on it is an
interactive Python console. The first cannot be read by `fetch()` — it surfaces
three layers away as `unexpected token < in JSON at position 0` — and the second
is a remote shell.

Every error now returns the same JSON shape the client already knows how to read,
with the traceback going to the log instead of the response. The handler stands
aside under `TESTING` and `DEBUG`, because a catch-all that turns every bug into
a tidy 500 is exactly what you do not want while writing the bug: pytest would
report `assert 500 == 200` where it used to report the line number.

### Plus one: the leaderboard opt-out

Not a security control in the usual sense, which is why it was the easiest to
keep postponing. The leaderboard lists every account's name, XP and current
streak to every other account, and there was no way to decline. Among friends who
all opted into a shared tracker that is the feature — and it is still not
something anyone agreed to. "You can stop using the app" is not consent.

Settings → Privacy hides you. Opting out removes the row rather than anonymising
it: among five people, a blanked-out entry between two named ones is not
anonymous, because everyone can name you by elimination.

The response carries `viewer_hidden` so the page can say *you asked to be hidden*
rather than leaving someone to wonder why they are missing from a board they are
looking at.

## How this is tested

`tests/test_security.py` covers each control directly — 30 tests. But the
important coverage is not there.

CSRF is a `before_request` hook, so **every one of the 440-odd tests in the suite
passes through it**. `conftest.CsrfClient` is what makes them pass: a test client
that behaves like a browser the server has met before, holding the cookie and
echoing it back on writes. Delete the hook and the suite still passes. Delete the
token from the client and several hundred tests fail.

That arrangement is on purpose. A test about recipe servings should be about
recipe servings; the day it also has to thread a security token through by hand
is the day someone disables the token in tests.

## What is still not done

Honest list, in rough order of how much it would matter:

- **No password strength rule** beyond six characters, and no check against known
  breached passwords.
- **No account recovery.** Forgetting your password means asking the owner to
  reset it. Email-based reset needs a mail sender and is its own attack surface.
- **No 2FA.**
- **No audit log** of administrative actions.
- **The admin panel lives in the classic Jinja app**, which is the least-exercised
  part of the codebase.
- **Registration codes are shared, not per-invite**, so one leaked code is one
  environment-variable change away from being fixed, but until then it is a code
  anyone who has it can use repeatedly.

## Related

- [DEPLOYMENT.md](DEPLOYMENT.md) — where the app runs and what it costs
- [ARCHITECTURE.md](ARCHITECTURE.md) — how the app is put together

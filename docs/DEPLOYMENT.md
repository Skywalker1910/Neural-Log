# Deployment

Where Neural Log runs, what it costs, and why. This file has changed its mind
twice, and both reversals are kept below rather than deleted — the reasoning is
the useful part, and a plan whose history is erased looks more certain than it
earned.

**Status:** the security prerequisites are done (see [SECURITY.md](SECURITY.md)).
The Lightsail host is configured with the application, HTTPS certificate, and
nightly local backups. See [AWS-LIGHTSAIL.md](AWS-LIGHTSAIL.md) for the current
deployment, remaining setup, and production configuration.

## The decision, as it stands

**Deploy the Flask app as it is**, to a small always-on AWS host, with SQLite on
a real disk and nightly verified backups. No re-platform, no storage rewrite, no
language change.

| Layer | Choice |
|---|---|
| Compute | Amazon Lightsail instance, 1 GB Linux plan with public IPv4 ($7/month) |
| Data | SQLite on the instance's disk — the current file, unchanged |
| Backup | Nightly snapshot to S3, and Lightsail's own disk snapshots |
| Delivery, TLS | Caddy on the instance, automatic Let's Encrypt |
| DNS | `neurallog.adityamore.dev`, domain already owned |
| Build | Frontend built in CI; the instance pulls a built image |

At $7/month, $94 of eligible, unexpired credits would cover roughly thirteen
months of compute, before backup charges. Confirm credit eligibility and expiry
in the AWS billing console. This estimate uses the current
[Lightsail bundle prices](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html);
the historical comparisons below reflect the earlier estimate.

## Why this, and not the re-platform

Until 2026-09-17 this file specified **Next.js 16 App Router on AWS Amplify SSR
with DynamoDB and S3**, at ~$0/month inside AWS's perpetual Always Free
allowances. That was a sound decision on the facts available, and two of those
facts have since changed.

**The storage rewrite is no longer forced.** The argument for DynamoDB was not
really about DynamoDB. It was that `artifacts/paths/<username>.json` was the only
copy of a user's Paths, not mirrored in the database, and every
ephemeral-filesystem platform would silently delete it — so *whatever* the
destination, the storage had to be rewritten first. Migration 011 moved Paths
into SQL. What is left on disk is a write-only checklist audit log and the
`exports/` scratch directory, neither of which the app ever reads back. The
entire live dataset is one 565 KB SQLite file.

**The cost comparison was between $0 and $87/year.** It is now between $0 and
$60/year *with $94 of credits in hand*, against a re-platform that is, by some
distance, the largest single piece of work in the project: ~8,300 lines of
application Python across 71 endpoints, 35 tables, a scoring engine, an XP ledger
and 441 tests — all of it rewritten in TypeScript, with the relational schema
redesigned as DynamoDB access patterns. The analytics date-range queries and the
leaderboard are exactly the shapes DynamoDB is worst at.

So the $0 was never free. It was priced in weeks, and the bill came due before
anything was live.

**What this gives up**, stated plainly: an always-on instance costs money whether
or not anyone opens the app, and it comes with the ops that serverless deletes —
OS patching, a systemd unit, certificate renewal, backup and restore drills. At
this scale each of those is small. None of them is zero.

**What it keeps open:** the re-platform is now an optional later migration rather
than a wall between the app and its users. If the credits run out and the bill is
not worth it, the options are to port then, move to something cheaper, or take
the app down — and all three are decisions made with a working app in hand.

## Cost

| | Monthly | Year 1 | After credits |
|---|---|---|---|
| Lightsail 1 GB instance with IPv4 | $7.00 | $84 before credits | $84/year |
| S3 backups and Lightsail snapshots | usage-based | additional | additional |
| Data transfer | included (2 TB) | — | included |
| Domain | already owned | $0 | $0 |

Two things to watch on a real bill rather than trust a table about:

- **Amplify Hosting's free tier is 12 months, not perpetual.** Lambda, DynamoDB,
  S3, CloudFront and CloudWatch have perpetual Always Free allowances; Amplify's
  5 GB storage / 15 GB transfer / 1,000 build minutes appear to be a 12-month
  trial. This matters only if the re-platform ever happens, but it is the thing
  the original $0/month estimate leaned on hardest, and it was already flagged as
  unverified in the version of this file that made it.
- **NAT Gateway, $32.85/month.** The classic hobby-project disaster, acquired by
  accepting the VPC wizard's defaults. Lightsail structurally cannot contain one,
  which is a real part of why it is the choice here.

## Why not the other options

### Why not Elastic Beanstalk, App Runner, or Fargate

All three have ephemeral filesystems, so all three mean either a managed database
or losing the data. A managed database means porting SQLite to Postgres: 18
migrations plus raw SQL full of `strftime`, `julianday` and
`INTEGER PRIMARY KEY AUTOINCREMENT`. That is real work for no benefit at 2–5
users and 565 KB.

Elastic Beanstalk is the specific trap: it rebuilds the instance during routine
platform updates, wiping anything on local disk with no error message.

### Why not a VM was the original answer

The first version of this file recommended Lightsail, then withdrew it in favour
of serverless. The arguments against it were: $87/year forever whether anyone
opens the app or not, plus SSH, systemd, OS patching, Caddy, backup scripts,
restore drills and uptime monitoring — pure overhead at this scale.

Those arguments are still true. They are simply no longer decisive, because the
thing they were being compared against turned out to cost weeks rather than
nothing. The ops overhead is accepted deliberately, and the plan keeps it as
small as it can be: a container the instance pulls, so a redeploy is one command
and a rebuild is not done on the box.

## Before it is public

The security list is done — all seven items, plus the leaderboard opt-out.
[SECURITY.md](SECURITY.md) is the full write-up; the summary:

| | Status |
|---|---|
| No hard-coded secret fallback | Done — production refuses to boot without `SECRET_KEY` |
| Registration closed by default | Done — `REGISTRATION_MODE` defaults to invite in production |
| Admin assigned, not raced for | Done — `ADMIN_USERNAME` |
| Login rate limiting | Done — 10/username, 30/IP, 15-minute window |
| CSRF protection | Done — `SameSite=Lax` plus a double-submit token |
| `GET /logout` changed state | Done — POST signs out, GET confirms |
| Session cookie flags | Done — `Secure`, `HttpOnly`, `SameSite` |
| Structured error responses | Done — JSON, no tracebacks |
| Leaderboard opt-out | Done — Settings → Privacy |

Done on the host, and verified against the running instance:

- `NEURAL_LOG_ENV=production`, a generated `SECRET_KEY` and an invite code, in
  `/srv/neurallog/.env` at mode 0600 rather than in the repository.
- `DATABASE` at `/srv/neurallog/data/neural_log.db`, outside the application
  directory, so a redeploy cannot overwrite it.
- `FLASK_DEBUG` unset. The Werkzeug debugger is remote code execution.
- Caddy terminating TLS and proxying to gunicorn over the compose network, with
  HSTS and the rest of the browser-side headers.

Still open, and both about backups rather than the app — see
[BACKUPS.md](BACKUPS.md):

- **Snapshots leave the instance.** Until the S3 setup is done they are written
  beside the database, which protects against deleting the wrong thing and not
  at all against losing the instance. Admin -> System status says which of the
  two is currently true, so this cannot stay forgotten quietly.
- **A restore drill on the live instance.** `scripts/drill.sh` unpacks the
  newest backup, boots a real container against it and tears it down, touching
  nothing live. An untested backup is a belief, not a backup.

## Related

- [BACKUPS.md](BACKUPS.md) — what stands behind one disk on one instance
- [SECURITY.md](SECURITY.md) — what had to be true before the app was reachable
- [ARCHITECTURE.md](ARCHITECTURE.md) — how the app is built
- [DATA-MODEL.md](DATA-MODEL.md) — the entity map
- [ROADMAP.md](ROADMAP.md) — where the deploy sits in the phase order

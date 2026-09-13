# AWS deployment

How Neural Log gets onto the internet for 8-10 people, what it costs, and why each
choice was made. Written for someone who has not used AWS before.

## The recommendation

**Amazon Lightsail, $7/month bundle** — Ubuntu 24.04, 1 GiB RAM, 2 vCPU, 40 GB SSD,
2 TB transfer, static IPv4 included. gunicorn under systemd, behind Caddy for TLS.
SQLite and `artifacts/` on the instance disk, nightly backup tarball to S3.

Lightsail is AWS's simplified VPS: one fixed price that already bundles the VM, the
disk, the static IP and egress. It is a normal Linux box, so it runs the app unmodified.

### Why a plain VM and not containers

Because **this app writes to local disk on almost every request, including reads.**
`load_user_paths()` calls `save_user_paths()` unconditionally, so `GET /api/current-user`,
`GET /api/paths` and `GET /api/checklist-items` are all disk writes. And
`artifacts/paths/<username>.json` is the *only* copy of a user's Paths — that data is
not in the database at all.

Every managed-container option has an ephemeral filesystem that would silently delete
both on each redeploy:

| Option | Why not |
|---|---|
| App Runner | AWS states files cannot persist beyond a single request |
| ECS Fargate | Task storage vanishes when the task stops; EFS is the only persistence, and SQLite over NFS is a documented locking hazard |
| Elastic Beanstalk | The real trap — same price as EC2, but it *rebuilds the instance* on platform updates, immutable deploys and health replacements. Each one wipes `neural_log.db` and `artifacts/` with no error |

### Why Lightsail over EC2

Same machine costs $11.59/month on EC2 ($6.13 instance + $1.60 disk + $3.65 for the
public IPv4 + snapshots) versus $7.21 on Lightsail, because the disk, IP and egress are
inside the bundle. That is **$53/year**.

The structural reason matters more for a beginner: Lightsail has no VPC console to
accidentally create a **NAT Gateway** in — $32.85/month, three times this entire
project, and you get one by accepting the VPC wizard's "VPC and more" defaults that
most tutorials tell you to click.

**The tradeoff, honestly:** Lightsail is a walled garden. CloudFront, SNS (for iOS push
later) and anything VPC-native attach awkwardly, and moving to EC2 later is a rebuild,
not a resize. If you know you want AWS-native services within a year, pay the $53.

### The failure mode, unhedged

One instance, one copy of the live data. If the box dies or you fat-finger `rm`, the app
is down and the data is gone until you restore — losing up to 24 hours, recovery ~30
minutes from the S3 tarball. There is no failover. For 8-10 friends tracking habits that
is the right trade; real high availability costs $50+/month and requires porting off
SQLite first.

You also **cannot run a second copy of this app anywhere** until SQLite becomes Postgres
and `artifacts/` becomes S3. Two instances means two diverging databases.

## Cost

| Line | Config | Year 1 | Steady state |
|---|---|---|---|
| Lightsail bundle | 1 GiB / 2 vCPU / 40 GB / 2 TB egress / static IP | $0 (credits) | $7.00/mo |
| Automatic snapshots | daily, 7 retained | $0 (credits) | $0.20/mo |
| S3 backups | ~5 MB, ~30 PUTs/mo | $0 (credits) | $0.01/mo |
| TLS | Let's Encrypt via Caddy | $0 | $0 |
| Domain (.com) | registrar's free DNS | ~$14 | ~$1.17/mo |
| Route 53 hosted zone | **skip it** — registrar DNS is identical and free | $0 | $0 |
| **Total hosting** | | **~$14** | **$8.38/mo — $101/yr** |
| Apple Developer Program | required for TestFlight; not AWS, not covered by credits | $99 if iOS starts | $99/yr |
| **Total, roadmap as written** | | **~$113** | **$200/yr — $16.63/mo** |

At ten users that is **$1.66 per user per month**.

**Year one is ~$14 out of pocket, not $0.** The $100 sign-up credit is guaranteed and
covers roughly $87 of Lightsail usage, but credits have historically excluded domain
registration and do not cover sales tax. The *second* $100 of credits is optional and
requires activities (like standing up an RDS instance) that cost more than they pay if
you forget to delete them — do not budget on it.

Credits expire 12 months after account creation regardless of use, so the first real
invoice arrives in month 13. Set a reminder for month 11.

### Deliberately not provisioned

Recognise these if a tutorial suggests one:

- **NAT Gateway** — $32.85/mo per AZ, billing whether traffic flows or not
- **Application Load Balancer** — $16.43/mo idle, before a single request. Its main draw
  is a free ACM certificate, but ACM public certs are non-exportable and cannot be
  installed on a VM anyway — on a bare box the free-TLS path is Let's Encrypt
- **RDS** — db.t4g.micro is $11.68 plus a forced 20 GB minimum, $13.98/mo to host 120 KB,
  *on top of* the instance you would still pay for
- **CloudFront** — putting the bundle on another hostname makes the session cookie
  cross-site and forces `SameSite=None` plus CORS-with-credentials

## Before any of this: the security work

The app is not currently safe to expose. In rough priority:

1. **`SECRET_KEY` falls back to a published string.** `os.environ.get('SECRET_KEY', 'dev-only-insecure-secret-key')` — and this repo is public. Anyone who learns the hostname can forge an admin session cookie. Generate the production key *on the server*.
2. **`FLASK_DEBUG` must be explicitly `0`.** The Werkzeug debugger is remote code execution for anyone who can trigger a traceback, and `.env.example` ships `FLASK_DEBUG=1`.
3. **The session cookie has no flags at all.** Set `SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE='Lax'`, and a lifetime.
4. **No CSRF protection of any kind** — and `GET /logout` clears the session on a GET with no token.
5. **No login rate limiting.** Unlimited password guesses against a 6-character minimum.
6. **`ProxyFix` is mandatory** — behind Caddy every request arrives from `127.0.0.1`, so an IP-keyed limiter without it throttles everyone as one client.
7. **Registration is fully open and the first user becomes admin.**
8. **SQLite has no timeout and no WAL**, so `gunicorn -w 2` will produce "database is locked" — made much likelier by read endpoints that write.
9. **`save_user_paths` truncates the only copy of a user's Paths before writing it.** An interrupted write loses that user's templates permanently.
10. **No `@app.errorhandler`**, so 404/500 return Werkzeug HTML and leak internals.

## Setup, in order

1. **Account** — sign up and choose the **paid** plan, not the Free plan. A Free-plan account is capped and *closes* after 6 months or $100.
2. **Guardrails first** — Budgets → two cost budgets ($15 and $30/month) with email alerts, before launching anything. The first two budgets are free.
3. **Identity** — MFA on root, create an IAM admin user, stop using root. `winget install Amazon.AWSCLI`, then `aws configure`.
4. **Region** — `us-east-1`, and leave it. Cheapest, and single-digit ms from South Carolina.
5. **Do the security list above**, on a branch, with tests passing, merged.
6. **Create the instance** — Lightsail → Linux/Unix → OS Only → Ubuntu 24.04 → $7 plan. Attach a **static IP** (free while attached).
7. **Firewall** — allow 80 and 443 from anywhere, restrict 22 to your IP, delete everything else. Never open 5000 or 8000.
8. **DNS** — A record at your existing registrar pointing at the static IP. Create no Route 53 zone.
9. **OS baseline** — `apt update && apt upgrade`, install `python3-venv sqlite3 git rsync unattended-upgrades`, then `dpkg-reconfigure -plow unattended-upgrades`.
10. **App user** — never run as root: `adduser --system --group --home /opt/neural-log neurallog`, clone, make a venv.
11. **Secrets** — generate the key *on the server* so it never touches your laptop or the public repo: `python3 -c "import secrets; print('SECRET_KEY='+secrets.token_hex(32))" | sudo tee /etc/neural-log.env`, then add `FLASK_DEBUG=0` and an absolute `DATABASE=` path.
12. **systemd unit** — `gunicorn --workers 2 --preload --bind 127.0.0.1:8000 app:app`, `EnvironmentFile=/etc/neural-log.env`, `Restart=always`.
13. **Caddy** — a three-line Caddyfile gets a Let's Encrypt certificate in ~30 seconds and renews it automatically, forever, for $0.
14. **Build the frontend on Windows** — `cd frontend; npm ci; npm run build`. `frontend/dist` is gitignored, so `git pull` on the server will never produce it.
15. **Deploy script** — back up *first*, then build, push, pull, rsync `dist/`, restart. Backup-before-restart is not optional: `run_migrations()` fires on import.
16. **S3 bucket** — versioning on, lifecycle expiring noncurrent versions after 90 days. No Glacier transition — those classes bill a 128 KB minimum per object.
17. **Backup script** — use `sqlite3 .backup`, **not** `cp` (copying a live WAL database can restore torn). Tar the `.db` together with `artifacts/`. Ping healthchecks.io so a silently failing backup is noticed.
18. **Test the restore today.** Specifically verify `artifacts/paths/<username>.json` came through — that data exists nowhere else.
19. **Snapshots** — daily, keep 7. A different recovery path from the tarball: restores the whole machine.
20. **Monitoring** — UptimeRobot free tier against `/api/health`. With no load balancer, this is your only notification that the site is down.
21. **Final check** — register your admin account first, confirm registration is then closed, and inspect the session cookie for `Secure; HttpOnly; SameSite=Lax`.

## Related

- [API.md](API.md) — the versioned API and token auth the iOS app needs
- [ARCHITECTURE.md](ARCHITECTURE.md) — why the app is shaped the way it is

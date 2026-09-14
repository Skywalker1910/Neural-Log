# Deployment

Where Neural Log runs, what it costs, and why. Updated after the cost review —
the earlier recommendation in this file (a Lightsail VM) was withdrawn; see
*Why not a VM* below for the reasoning, since it is still worth understanding.

## Target architecture

**Serverless, mirroring the Tech-Portfolio stack already in production:**

| Layer | Service |
|---|---|
| Frontend + backend | Next.js 16 App Router on **AWS Amplify SSR** |
| API | Next.js route handlers (not a separate service) |
| Data | **DynamoDB** — replaces SQLite *and* the `artifacts/` JSON files |
| Blobs / backups | **S3** |
| Delivery, TLS, DNS | CloudFront (Amplify-managed), `neurallog.adityamore.dev` |

This is a deliberate re-platform, not a redeploy. Amplify SSR runs **Next.js**
route handlers as managed serverless compute — it cannot run Flask/gunicorn. So
"host it like the portfolio" necessarily means the backend becomes TypeScript.

**Timing:** after R2 (Home + Today) is finished, so the data model and scoring
have stopped moving. Porting a moving target means doing the DynamoDB key design
twice.

## Cost

At 2–5 users the whole thing sits inside AWS's **Always Free** allowances, which
are perpetual — not a 12-month trial. They apply to every account, old or new,
for as long as it stays open and usage stays under the caps.

| Service | Always-free allowance | Our usage at 2–5 users |
|---|---|---|
| Lambda (behind Amplify SSR) | 1M invocations + 400K GB-s / month | a few thousand invocations |
| DynamoDB | 25 GB storage + provisioned RCU/WCU | ~120 KB |
| S3 | see current free tier | a few MB |
| CloudFront | see current free tier | negligible |
| Domain | already owned (`adityamore.dev`) | $0 |

**Expected: ~$0/month, indefinitely.**

One thing to confirm against a real bill: **Amplify Hosting itself was not in
the Always Free list** (Lambda, DynamoDB, S3, CloudFront and CloudWatch were).
Its 5 GB storage / 15 GB transfer / 1,000 build-minute allowances may be
12-month only. The Tech-Portfolio account is the authoritative source here —
check what it actually bills after year one.

### Why not a VM

The original plan here was Amazon Lightsail at $7/month ($87/year). It was
rejected once two things became clear: the user count dropped to 2–5, and the
owner already operates the serverless stack in production.

Lightsail's advantages were real but situational — it runs the *current* Flask
app unmodified, and it structurally cannot contain a **NAT Gateway** ($32.85/mo,
the classic hobby-project disaster you get by accepting the VPC wizard's
defaults). That second argument only matters for someone new to AWS, which turned
out not to apply.

Against it: $87/year forever whether anyone opens the app or not, plus the real
cost — SSH, systemd, OS patching, Caddy, backup scripts, restore drills and
uptime monitoring, all of which are pure overhead at this scale and all of which
the serverless option deletes.

### Why not Elastic Beanstalk, App Runner, or Fargate

These were rejected for the *current* Flask app and the reasoning is worth
keeping, because it explains why the DynamoDB port is mandatory rather than
optional:

The app as written today writes to local disk on almost every request —
`load_user_paths()` re-saves unconditionally, so even `GET /api/current-user` is
a disk write — and `artifacts/paths/<username>.json` is the **only** copy of a
user's Paths, not mirrored in the database. Every serverless or container
platform has an ephemeral filesystem, so all of them would silently delete it.
Elastic Beanstalk is the worst trap: it rebuilds the instance during routine
platform updates, wiping the database with no error message.

**This is why the port is a storage rewrite, not a lift-and-shift.** Whatever the
destination, SQLite and `artifacts/` have to become DynamoDB first.

## What has to happen before it is public

Most of the security list survives the re-platform, because it is about the
application, not the host. Re-check each against the Next.js implementation:

1. **No hard-coded secret fallback.** The Flask app falls back to a literal
   published in this public repo; do not reproduce that pattern.
2. **Registration is fully open and the first user silently becomes admin.**
3. **No login rate limiting.**
4. **No CSRF protection**, and `GET /logout` changes state on a GET.
5. **Session cookie flags** — `Secure`, `HttpOnly`, `SameSite`.
6. **Structured error responses**, so nothing leaks a stack trace.
7. **Leaderboard exposes every user's name, XP and streak** with no opt-out —
   a product decision, not just a security one.

Items that disappear with the port: SQLite WAL/locking, `save_user_paths`
truncating the only copy of a user's data, the cwd-relative `artifacts/` paths,
the exports/ directory growing unbounded, and `ProxyFix`/reverse-proxy concerns.

## Related

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the app is built today
- [DATA-MODEL.md](DATA-MODEL.md) — the entity map, and what DynamoDB has to absorb
- [ROADMAP.md](ROADMAP.md) — where the port sits in the phase order

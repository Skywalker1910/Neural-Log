# Deploy to AWS Lightsail

This procedure uses one Ubuntu 24.04 LTS x86_64 instance, Docker Compose,
Caddy HTTPS, and SQLite on a persistent host directory. The production example
is `deploy/lightsail.env.example`; the root `.env.example` is for development.

## Current deployment (2026-09-17)

| Setting | Value |
|---|---|
| Domain | `neurallog.adityamore.dev` |
| Static IPv4 | `3.221.56.117` |
| Region and OS | `us-east-1`, Ubuntu 24.04, x86_64 |
| Application directory | `/srv/neurallog` |
| Image | `neural-log:initial-20260917` |
| Initial release source | `44c938b` plus the local deployment changes |
| Persistent database | `/srv/neurallog/data/neural_log.db` |
| Production configuration | `/srv/neurallog/.env`, mode 0600 |
| Backup timer | `neurallog-backup.timer`, daily at 03:00 UTC plus up to 5 minutes |
| Backup retention | 14 local compressed snapshots |

The image was built on the instance for the initial deployment, with 2 GB of
swap configured. Existing accounts and history were imported using SQLite's
backup API. The health and login endpoints work over HTTPS from the instance,
and a backup was decompressed and checked in a separate temporary directory.
Public HTTPS health verification returns HTTP 200, and TCP 80 redirects to it
with a 308. Both 80 and 443 must stay open: 80 for the redirect and for
Let's Encrypt's HTTP-01 challenge at renewal, 443 for everything else.

Backups have their own write-up: **[BACKUPS.md](BACKUPS.md)** covers what runs,
how to send snapshots off the instance to S3 with write-only credentials, and the
restore drill. Read that rather than improvising from here.

The short version of the state to check: **Admin -> System status** shows the age
of the last backup and whether it left the instance. Amber ("on this instance
only") means the S3 setup in BACKUPS.md has not been done, and losing the
instance would lose both the database and every snapshot of it.

Operational commands on the instance:

```bash
cd /srv/neurallog
sudo docker compose ps
sudo docker compose logs --tail 50 app caddy
sudo systemctl list-timers neurallog-backup.timer
sudo journalctl -u neurallog-backup.service --no-pager -n 30
sudo ./scripts/drill.sh          # rehearse a restore; touches nothing live
```

For a restore, stop the app and preserve its current database before replacing
it. The restored database must belong to UID/GID `10001:10001`, with a writable
parent directory, before restarting the app. The initial source snapshot is
preserved at `/srv/neurallog/backups/initial-20260917.db`.

## 1. Prepare the release

The Dockerfile, Compose file, Caddyfile, Gunicorn configuration, and image CI job
must be included in the release. A checkout of an older `main` without these
files cannot use this procedure. Keep a record of the deployed commit.

Once these changes are merged into `main`, the Container image CI job publishes
`ghcr.io/skywalker1910/neural-log:sha-<full-commit-sha>`. Wait for all jobs to pass.
Set the GHCR package visibility to public if anonymous pulls are intended;
repository visibility does not automatically make a new package public.
For a private package, authenticate on the instance using `docker login ghcr.io`
with a token limited to reading the package.

An initial deployment can also transfer a locally built image without publishing
it. From this repository on your workstation, with Docker running:

```powershell
docker build --platform linux/amd64 -t neural-log:initial .
docker save --output "$env:TEMP/neural-log-initial.tar" neural-log:initial
scp -i <ssh-key-path> "$env:TEMP/neural-log-initial.tar" ubuntu@<static-ip>:/tmp/
```

On the instance, run `sudo docker load --input /tmp/neural-log-initial.tar` and
set `NEURAL_LOG_IMAGE=neural-log:initial`. Skip `docker compose pull app` for this
route. This image contains the local working tree, including uncommitted code.

## 2. Create the host and DNS record

In the Lightsail console, select the intended region, Linux/Unix, OS only,
Ubuntu 24.04 LTS, and the **1 GB public IPv4 plan**. The
[published bundle price](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)
is $7/month before snapshots, S3 charges, taxes, or eligible credits.

Name the instance `neural-log`. Attach a
[static IPv4 address](https://docs.aws.amazon.com/lightsail/latest/userguide/lightsail-create-static-ip.html).
Allow inbound TCP 80 and 443 publicly, and SSH 22 only from your own IP or
Lightsail browser SSH. UDP 443 is optional for HTTP/3. Keep port 8000 closed.
Review IPv6 firewall rules separately if IPv6 is enabled.

At your DNS provider, create an A record for `neurallog.adityamore.dev` pointing
to that static address. Use DNS-only mode initially if the provider offers a
proxy. Do not add an AAAA record unless IPv6 routing and firewall rules are ready.

Enable Lightsail automatic snapshots and a billing budget notification. Snapshots
are billed separately and complement the SQLite backups below.

## 3. Install dependencies and copy deployment files

Connect as `ubuntu` using Lightsail browser SSH or your SSH key. Install Docker
Engine and the Compose plugin using
[Docker's official Ubuntu repository instructions](https://docs.docker.com/engine/install/ubuntu/#install-using-the-apt-repository).
Then run:

```bash
sudo apt-get update
sudo apt-get install -y sqlite3 python3 unzip
sudo systemctl enable --now docker
sudo install -d -o ubuntu -g ubuntu -m 0750 /srv/neurallog
sudo install -d -o 10001 -g 10001 -m 0750 /srv/neurallog/data
```

From the repository on your workstation, copy the files from the same release
as the image. Replace the SSH key path and static IP:

```powershell
scp -i <ssh-key-path> docker-compose.yml Caddyfile ubuntu@<static-ip>:/srv/neurallog/
scp -i <ssh-key-path> deploy/lightsail.env.example ubuntu@<static-ip>:/srv/neurallog/.env
scp -i <ssh-key-path> -r scripts ubuntu@<static-ip>:/srv/neurallog/
```

Copy the example `.env` only for the initial setup. Future releases must preserve
the instance's secrets and database. If files came from a Windows checkout,
normalize shell script line endings on the host:

```bash
cd /srv/neurallog
sed -i 's/\r$//' scripts/backup.sh scripts/restore.sh
chmod 600 .env
```

## 4. Configure production

Generate secrets on the instance without printing them:

```bash
cd /srv/neurallog
python3 - <<'PY'
from pathlib import Path
import secrets

config_path = Path('.env')
config_lines = config_path.read_text().splitlines()
for setting in ('SECRET_KEY', 'REGISTRATION_CODE'):
    config_lines = [
        f'{setting}={secrets.token_urlsafe(48)}' if line == f'{setting}=' else line
        for line in config_lines
    ]
config_path.write_text('\n'.join(config_lines) + '\n')
config_path.chmod(0o600)
PY
nano .env
```

Set `ADMIN_USERNAME`, `NEURAL_LOG_ACME_EMAIL`, the domain, and the exact image
tag. Keep `REGISTRATION_MODE=invite`, or use `closed` if importing existing
accounts and no new accounts are needed. `ADMIN_USERNAME` affects new account
registration; it does not promote an existing account. Keep the secret key
stable across redeploys so existing sessions remain valid.

## 5. Bring existing data, or start empty

To preserve local accounts and history, create a consistent snapshot with
SQLite's backup API. Do not copy a database file while it is being written to.
From the repository on Windows:

```powershell
.\.venv\Scripts\python.exe -c "import os, sqlite3, tempfile; source = sqlite3.connect('file:neural_log.db?mode=ro', uri=True); target = sqlite3.connect(os.path.join(tempfile.gettempdir(), 'neural-log-upload.db')); source.backup(target); target.close(); source.close()"
scp -i <ssh-key-path> "$env:TEMP/neural-log-upload.db" ubuntu@<static-ip>:/tmp/
```

On the instance, **before starting the app for the first time**:

```bash
cd /srv/neurallog
test ! -e data/neural_log.db && sudo install -o 10001 -g 10001 -m 0600 /tmp/neural-log-upload.db data/neural_log.db
sudo sqlite3 data/neural_log.db 'PRAGMA integrity_check;'
```

The result must be `ok`. If the database already exists, stop and use a planned
restore instead of overwriting it. For a fresh installation, skip the snapshot
and upload; startup creates and migrates the database automatically.

## 6. Start and verify

```bash
cd /srv/neurallog
sudo docker compose config --quiet
sudo docker compose pull
sudo docker compose up -d --wait --wait-timeout 120
sudo docker compose ps
sudo docker compose logs --tail 50 app caddy
curl --fail https://neurallog.adityamore.dev/healthz
```

For a transferred local image, replace `docker compose pull` with
`docker compose pull caddy`. The health response must be `{"status":"ok"}`.
Check sign-in, saving a log, refreshing to confirm persistence, and signing out.
With a fresh database, register the configured admin username using the invite
code from `.env`. Caddy needs working DNS and inbound ports 80/443 to obtain TLS.

## 7. Backups and subsequent releases

Create a private S3 bucket in the same region, block public access, and apply a
lifecycle rule to expire old backups after your chosen retention period. Install
the AWS CLI using the [official Linux instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
Configure AWS credentials for the account running the backup job. Do not assume
an EC2 instance role is available on Lightsail. Limit backup access to listing
the bucket and reading/writing the `db/` prefix; keep these credentials separate
from the application's `.env`.

Verify access with `aws sts get-caller-identity`, then run from `/srv/neurallog`
as a user that can read the UID 10001 database directory:

```bash
export NEURAL_LOG_BACKUP_BUCKET=your-private-backup-bucket
bash scripts/backup.sh
```

If using root for backups, configure AWS credentials for root and use root's
crontab. Schedule the same tested command nightly, including its working
directory and `NEURAL_LOG_BACKUP_BUCKET`. Check the resulting S3 object and job
logs. Before relying on it, download a backup to a scratch directory, decompress
it, and check `PRAGMA integrity_check` plus the expected account and log counts.

For a manual redeploy, take a backup, change `NEURAL_LOG_IMAGE` to the new
commit tag, and run `sudo docker compose pull app` followed by `sudo docker
compose up -d --wait --wait-timeout 120`. The normal path is the `main`
push-to-deploy job described below. Preserve `data/`, `.env`, and the Caddy
certificate volumes. Image rollback alone may not undo schema changes; retain
the pre-deploy database snapshot.

## Push-to-deploy

The `main` push workflow runs backend tests, frontend checks, migration checks,
and the image build before deploying. The final job connects to Lightsail over
SSH, pulls the exact `sha-<full-commit-sha>` image that passed CI, restarts only
the app container, and verifies `https://neurallog.adityamore.dev/healthz`.

Create a GitHub environment named `production` and add these environment secrets:

| Secret | Value |
|---|---|
| `LIGHTSAIL_HOST` | `3.221.56.117` (or the static IP if it changes) |
| `LIGHTSAIL_USER` | `ubuntu` |
| `LIGHTSAIL_SSH_KEY` | Contents of the Lightsail private key, never committed |
| `LIGHTSAIL_KNOWN_HOSTS` | Output of `ssh-keyscan -H 3.221.56.117` after verifying the fingerprint in Lightsail |

Keep the GHCR package public so the instance can pull without a second
credential. If the package is private, add a separate read-only registry login
step rather than placing a token in the repository or the instance image.
Deployments are serialized, and a failed health check leaves the previous
container available for manual rollback using its prior image tag.

# Backups

The app runs on one Lightsail instance with one SQLite file on its disk. That is
a deliberate, defensible choice at 2–5 users — and it means the instance is a
single point of failure for every day anyone has ever logged.

This is what stands behind it.

## What we are actually defending against

Three different failures, which want three different answers. Conflating them is
how people end up with a backup strategy that covers the case that was never
going to happen.

| Failure | How likely | What saves you |
|---|---|---|
| You delete the wrong thing, or a migration goes wrong | Most likely | Last night's snapshot, on the instance |
| The instance is lost — terminated, disk corrupted, region trouble | Unlikely, total | A copy that is **not** on the instance |
| Someone gets into the instance | Least likely, worst | A copy the instance **cannot delete** |

The third is the one that shapes the design, and it is the reason for the odd
thing below: the credentials on the instance can write backups and cannot read
or delete them.

## What runs

`scripts/backup.sh`, nightly at 03:00 UTC via `neurallog-backup.timer`. Each run:

1. **Snapshots** with `sqlite3 .backup`, which uses SQLite's online backup API.
   Not `cp` — a copy of a live database can catch it mid-transaction and produce
   a file that opens fine and is missing a page. That is the worst kind of broken
   backup, because you find out during a restore.
2. **Verifies** with `PRAGMA integrity_check`, and counts users and logged days.
   An unverified backup is a belief. The count is what catches a backup that
   quietly started copying an empty database.
3. **Compresses** and keeps the last 14 on the instance.
4. **Uploads** to S3, then issues a `HEAD` to confirm the object landed at the
   size that was sent.
5. **Writes a status file** next to the database, whether it succeeded or failed.

## Why the status file exists

Because the way backups fail is silently. The timer stops firing, credentials
expire, a bucket policy changes — and nothing anywhere says so. `systemctl
status` knows. Nobody runs `systemctl status` on a Tuesday.

So every run drops `backup-status.json` into the data directory, which is the one
place the container can already see, and **Admin → System status** reads it back:

- `Backup: 8h ago` — green, and off-instance
- `Backup: 8h ago, on this instance only` — amber; running, not protecting you
  against losing the box
- `Backup overdue — last succeeded 4d ago` — red; the timer has stopped
- `Last backup FAILED — 8h ago` — red; it ran and could not finish

A failed run writes the file too. That is the point: a script that only reports
success is a script whose silence means nothing, because you cannot tell "it
worked" from "it never ran".

## Setting up S3

Console work, in order. Substitute your own bucket name — it must be globally
unique, so something like `neurallog-backups-<4 random digits>`.

### 1. The bucket

**S3 → Create bucket**, in the same region as the instance (`us-east-1`).

| Setting | Value | Why |
|---|---|---|
| Block *all* public access | **On** | Nothing here is ever public |
| Bucket Versioning | **Enable** | An overwrite keeps the old version, so a corrupted upload cannot replace a good backup |
| Default encryption | SSE-S3 | Free, and one less thing to answer for |

Then **Management → Create lifecycle rule**, named `backup-retention-365d`,
applied to the whole bucket:

- Expire current versions after **365 days**
- Permanently delete noncurrent versions after **30 days**
- Delete incomplete multipart uploads after **7 days**

At roughly 90 KB a night this is pennies a year either way; the rule exists so
the bucket does not accumulate forever without anyone deciding that it should.
The name carries the retention because the question you will actually be asking
when you read it is "why is my two-year-old backup gone", and a name can answer
that without opening the rule.

### 2. Write-only credentials

This is the part worth getting right.

**IAM → Policies → Create policy → JSON.** Paste
[`deploy/backup-iam-policy.json`](../deploy/backup-iam-policy.json) and replace
`REPLACE-WITH-BUCKET-NAME`:

```json
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::your-bucket-name/db/*"
}
```

`s3:PutObject` and nothing else. No `GetObject`, no `DeleteObject`, no
`ListBucket`.

**That looks broken, and it is the whole point.** A backup the instance can
delete is not a backup against the instance being compromised — whoever gets in
gets the credentials, and the credentials are the way to destroy the history.
Write-only means the worst they can do is upload junk *alongside* your backups,
and versioning means even an overwrite keeps what was there.

The cost is that restoring does not use these credentials. It uses yours, from
your own machine, deliberately. That is the right shape: a restore is a decision
somebody makes, not something a cron job should be able to trigger.

Name the policy `neurallog-backup-write`.

**IAM → Users → Create user**, named `neurallog-backup`. **No console access.**
Attach the policy directly. Then **Security credentials → Create access key →
Application running outside AWS**, and keep the secret somewhere safe — the
console shows it once.

### 3. Update the scripts on the instance

**Continuous deployment does not do this.** The pipeline pulls the container
image and restarts Compose; it never touches `/srv/neurallog/scripts` or the
systemd unit. Merging a change to `backup.sh` therefore deploys the *app* and
leaves the *instance* running whatever script it already had — which is a
good way to spend an evening debugging a fix that was never installed.

The repository is public, so the instance can fetch its own files. No SSH key
needed, and GitHub serves LF, so the line-ending trap does not arise either:

```bash
cd /srv/neurallog
BASE=https://raw.githubusercontent.com/Skywalker1910/Neural-Log/main

curl -fsSL "$BASE/scripts/backup.sh"  -o scripts/backup.sh
curl -fsSL "$BASE/scripts/restore.sh" -o scripts/restore.sh
curl -fsSL "$BASE/scripts/drill.sh"   -o scripts/drill.sh
chmod +x scripts/*.sh

sudo curl -fsSL "$BASE/deploy/neurallog-backup.service" -o /etc/systemd/system/neurallog-backup.service
```

Check you got what you meant to before going on:

```bash
grep -q write_status scripts/backup.sh && echo "NEW" || echo "still the old one"
file scripts/backup.sh          # must not say CRLF
```

### 4. Point the instance at it

SSH in, then:

```bash
sudo install -m 600 /dev/null /etc/neurallog-backup.env
sudo tee /etc/neurallog-backup.env >/dev/null <<'EOF'
NEURAL_LOG_BACKUP_BUCKET=PUT-YOUR-REAL-BUCKET-NAME-HERE
NEURAL_LOG_BACKUP_LOCAL_ONLY=0
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
EOF
```

Every one of those five values has to be replaced. The bucket name is the one
that gets missed, because a wrong bucket fails as `AccessDenied` — which reads
like a credentials problem and is not.

Mode 0600 and owned by root: the systemd unit reads it as root, and nothing else
needs to.

Install the AWS CLI if it is not already there:

```bash
sudo apt-get install -y unzip
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
unzip -q /tmp/awscli.zip -d /tmp && sudo /tmp/aws/install && rm -rf /tmp/aws /tmp/awscli.zip
```

The unit copied in step 3 carries `EnvironmentFile=-/etc/neurallog-backup.env`
and no local-only default of its own, so the file above is the only thing
deciding where backups go. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl start neurallog-backup.service
sudo journalctl -u neurallog-backup.service --no-pager -n 20
```

You are looking for two lines:

```
uploading 88439 bytes to s3://your-bucket-name/db/2026/09/neural_log-...db.gz
uploaded; cannot confirm size (write-only credentials)
```

**Bytes rather than `88K`** means the new script is the one running — the old one
logged `du -h` output, so that number is the quickest way to tell whether the
step above actually landed.
The second line is success, not a warning: the upload went through and the
`HEAD` that would confirm its size was denied, which is exactly what write-only
credentials should do.

**Confirm the object exists from the console**, once. "Upload accepted" and
"the object is there" are different claims, and the point of these credentials is
that the instance can only ever make the first one.

A placeholder left in `NEURAL_LOG_BACKUP_BUCKET` fails as `AccessDenied` rather
than `NoSuchBucket`, because the IAM policy is scoped to one bucket ARN and
refuses the call before S3 is ever asked whether the other bucket exists. Worth
knowing, because the error names the wrong problem — and because it is the
least-privilege policy doing exactly its job. Bucket names are global, and
something plausible like `your-bucket-name` may well belong to a stranger.

Admin → System status should now read `Backup: just now` in green.

## The drill

```bash
cd /srv/neurallog && sudo ./scripts/drill.sh
```

`scripts/drill.sh` unpacks the newest backup into a scratch directory, starts a
**real container** against it on a loopback port, waits for the health check,
checks the sign-in page renders and that an unauthenticated API call is properly
refused, compares the row counts, and destroys the lot. It touches nothing live —
run it on the production instance in the middle of the afternoon.

**This is the part that is not optional.** `PRAGMA integrity_check` says the file
is a valid SQLite database; it does not say the application can run on it, and
those are different claims. A backup taken before a migration, a file the
container's user cannot write to, an archive truncated on upload so it
decompresses to something shorter but structurally valid — all of them pass an
integrity check and all of them fail a restore.

Run it after any change to the schema, the image, or the backup configuration.
A backup nobody has restored is a belief.

## A real restore

```bash
cd /srv/neurallog && sudo ./scripts/restore.sh
```

Stops the app, moves the current database aside with a timestamp (never deletes
it), puts the backup in place, fixes the ownership to match the data directory,
and starts the app again. It asks before it does any of that, and it verifies the
archive before it moves anything — so a corrupt backup cannot take out a working
database on its way past.

To restore from S3 you need read access, which the instance does not have by
design. Run it with your own credentials, or download the object yourself and
pass the path.

## Known gaps

- **One region.** The bucket and the instance are both in `us-east-1`. Losing the
  region loses both. Cross-region replication is one bucket setting away if that
  ever seems worth it; at this scale it does not.
- **No off-site copy of the `.env`.** The database is backed up; the secret key
  and invite code are not. Losing the instance means regenerating them, which
  signs everybody out but loses no data. Worth a note in a password manager.
- **Nothing pages you.** The status shows on a page an admin has to open. For 2–5
  users that is the honest level of investment; a genuine alert would need
  somewhere to send it.

## Related

- [AWS-LIGHTSAIL.md](AWS-LIGHTSAIL.md) — the deployment runbook
- [DEPLOYMENT.md](DEPLOYMENT.md) — where it runs and what it costs
- [SECURITY.md](SECURITY.md) — what had to be true before the app was public

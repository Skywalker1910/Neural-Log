# CI and branch protection

What runs on every pull request, what is enforced on `main`, and why each piece
is there.

## Motivation

For six phases this project has been verified by hand: run the tests, run the
typechecker, look at a screenshot. That works while one person is building it on
one machine, and stops working the moment either of those changes.

R6 was the argument for automating it. It moved the daily checklist - the one
feature used every single day - out of JSON files and into SQL, and the thing
that made that safe was a test suite someone remembered to run. The next time it
might not be remembered, and a migration that corrupts real logs is not the place
to find that out.

## What runs on a pull request

Three jobs, in `.github/workflows/ci.yml`. They run in parallel and all three
must pass before `main` will accept a merge.

| Job | What it does | What it catches |
|---|---|---|
| **Backend tests** | `pytest` against an isolated temp database | Logic regressions, scoring changes, API contract breaks |
| **Frontend checks** | `npm ci`, typecheck, lint, build | Type errors, lint violations, a build that does not compile |
| **Migration ledger** | `scripts/check_migrations.py` | Migrations that only work on *your* database |

### Why the migration check is separate from the tests

The test suite runs against a database that migrations already built, so it
cannot tell you:

1. Whether a migration applies to an **empty** database, with no earlier state to
   lean on.
2. Whether applying it **twice** is safe. `init_db()` runs at import time, which
   means on every gunicorn worker start - a non-idempotent migration would
   corrupt data on the second boot, not the first.
3. Whether the **ledger matches the directory**. A file added without being
   applied, or a row recorded for a file that no longer exists, both mean the
   next deploy does something nobody predicted.

`python scripts/check_migrations.py` answers all three, and is worth running by
hand before adding a migration.

### Why `push` and `pull_request` both trigger

Not redundant. A pull request is tested against a *merge commit that does not
exist on `main` yet*, so a green PR proves the merge would be green - not that
`main` is. The push run is the only thing that proves `main` itself is healthy
after a merge.

### Other workflow details worth knowing

- **`concurrency` with `cancel-in-progress`** - a second push to a branch makes
  the first run's answer irrelevant, so it is cancelled. Keeps feedback fast.
- **`permissions: contents: read`** - least privilege. Nothing in CI writes to
  the repo, comments, or needs a token beyond checkout. A public repo's workflow
  is worth keeping boring.
- **`npm ci`, not `npm install`** - installs exactly the lockfile and fails if
  `package.json` and the lock have drifted, which is the point of running it on a
  build machine.
- **No secrets are used.** `tests/conftest.py` points every test at a temp
  database and sets its own `SECRET_KEY`, so CI needs nothing configured.

### If the first run does not appear, wait before debugging it

When CI was first added here, the pull request showed no checks at all - not a
failure, not a pending run. `gh run list` was empty and
`gh api .../actions/workflows` reported `total_count: 0` for the whole repository.

That looks exactly like a broken workflow file, and it was not. The YAML was
valid, Actions was enabled, and the file was on the branch. A later push to the
same branch registered the workflow and ran all three jobs with no change to the
workflow itself.

The cause was never established - most likely a delay on GitHub's side in picking
up a repository's first workflow. The lesson is the useful part: **before editing
a workflow that is not running, confirm it is actually broken.** Check that the
YAML parses, that `actions/permissions` reports `enabled: true`, and that the file
is present on the head branch at the path `.github/workflows/`. If all three hold,
push again and give it a few minutes rather than rewriting a file that was
correct.

## What is enforced on `main`

Branch protection, applied via the GitHub API. In plain terms:

| Rule | Effect |
|---|---|
| Require a pull request | No pushing straight to `main`, ever |
| ~~Require 1 approving review~~ | **Removed.** See below |
| Dismiss stale approvals | A new push after approval re-opens the review |
| Require all three CI jobs | Red tests cannot be merged |
| Require branches up to date | Your branch must include the latest `main` before merging |
| Require conversation resolution | Unresolved review comments block the merge |
| Require linear history | Squash or rebase; no merge commits cluttering the log |
| Block force pushes | `main`'s history cannot be rewritten |
| Block deletions | `main` cannot be deleted |

### Why required approvals were removed

They were set to 1, and then dropped to 0 after the first PR hit the friction.

The reasoning that removed them: **required approvals never protected against
outsiders.** Only write access does that - someone forking a public repo cannot
merge their PR regardless of the rule. On a repository with one maintainer the
rule gated nobody but the maintainer, who cannot approve their own PR, so every
PR arrived pre-blocked and needed an administrator bypass.

Everything protective stayed: a pull request is still required, all three checks
must pass, the branch must be up to date, conversations must be resolved, and
force-pushes and deletions are still blocked.

Put the approval requirement back the day a second person gets write access -
that is when it starts doing real work.

### The self-approval problem

**GitHub does not let you approve your own pull request.** On a repository with
one maintainer, "require 1 approval" with no escape hatch means your own PRs
become permanently unmergeable.

So admins are deliberately **not** subject to enforcement (`enforce_admins:
false`). The practical result is exactly what was wanted:

- Anyone else's PR - a friend's, or a stranger's fork of this public repo -
  cannot merge without your review and green CI.
- Your own PRs still require the pull request and still run CI, but you can merge
  them yourself.

This is a deliberate trade, not an oversight. If a second maintainer ever joins,
flip `enforce_admins` to `true` and the strict reading applies to everyone.

## What is NOT set up, and why

**There is no deployment pipeline yet.** Deployment is the Ship phase, after R10,
and it comes with a re-platform from Flask + SQLite to Next.js + DynamoDB. A CD
workflow written today would target infrastructure that does not exist, against
an application architecture that is going to change - and a half-configured
deploy workflow sitting broken for five phases is worse than none, because it
looks like deployment is ready when it is not.

When the Ship phase arrives, CD gets added here.

## Dependency updates - currently off

`.github/dependabot.yml` is configured but **disabled**
(`open-pull-requests-limit: 0`). Set it to 1 per ecosystem to switch it on.

It is off because the first version of that file opened seven pull requests in
two hours. Three mistakes compounded:

- The grouping only covered `minor` and `patch`, and everything that actually
  arrived was a major bump, so each got its own PR.
- `open-pull-requests-limit` is **per ecosystem**, not total - three ecosystems
  at three each is nine.
- `interval: monthly` is how often Dependabot *checks*, not a delay before it
  starts. It ran the moment the file reached `main`.

Two of the three major bumps failed CI, which is the system working - but they
needed deliberate work rather than a merge, and they landed mid-phase as pure
distraction.

The config now groups **everything, majors included**, into one PR per ecosystem
per month. The right time to enable it is the Ship phase: until then the stack
moves under its own steam every phase, and a dependency PR competes with real
work.

Dependabot **security** alerts are a separate repository setting and are
unaffected. Those should stay on - they are rare and worth interrupting for.

### If a Dependabot PR ever has conflicts

Do not resolve it by hand. Comment `@dependabot rebase` on the PR and it rebases
itself.

## Reproducing CI locally

```bash
python -m pytest -q                 # backend
python scripts/check_migrations.py  # migrations
cd frontend && npm ci && npm run typecheck && npm run lint && npm run build
```

If those pass, CI will.

## Changing the protection rules

The rules live in GitHub, not in this repository, so they are recorded here to
stay reviewable. To inspect the current state:

```bash
gh api repos/Skywalker1910/Neural-Log/branches/main/protection
```

If a CI job is ever renamed, its old name stays in the required-checks list and
silently blocks every merge - update the protection rules in the same change that
renames the job.

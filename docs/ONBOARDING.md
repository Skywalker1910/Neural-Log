# Onboarding

The first-run flow, the Profile page, and Settings. For how attributes are
derived, see [SCORING.md](SCORING.md); for where the targets are consumed, see
[NUTRITION.md](NUTRITION.md).

## Motivation

Every phase before this one assumed the numbers it measures against already
existed. They did not.

`user_profile` is created lazily by whichever page first needs it, so an account
could reach R8's Analytics with no height, no birth year and no targets. The
engine would then correctly report almost everything as unobserved — which reads
as *"this app is broken"* rather than *"you have not told it anything yet"*.
Those are very different messages, and only one of them is true.

Onboarding is where the numbers come from.

## The line it must not cross

This is the whole design, so it comes first.

Onboarding sets **targets**. Body metrics produce baselines (BMI, BMR, TDEE),
baselines produce targets, and targets are already denominators the scoring
engine measures behaviour against — `targets_by_date` in
`scoring/producers.py` has consumed them since R4. So answering the questionnaire
genuinely changes what your first logged day scores.

Onboarding does **not** write attribute scores, and a test pins that.

"I train four times a week" is a claim, and the engine has a settled position on
claims: self-reported signal is capped at half the range
(`self_report_ceiling`), and an attribute reports `calibrating` until three days
of real history exist (`min_days_for_score`). Seeding Strength from a signup
checkbox would walk straight past both rules and hand someone a character sheet
they had not earned.

The brief asked for "behavioural scores start conservative and from
questionnaire answers". That is satisfied by the targets. The scores stay
unmeasured until there is something to measure.

## Non-blocking, and permanently dismissible

Nobody is redirected into the flow. New accounts land on Home like everyone else
and see a banner; the flow lives at `/welcome`, outside `AppShell`, because
framing a setup task with the sidebar of an app you have not set up yet is both
noisy and an invitation to wander off mid-question.

`should_prompt` is computed server-side — *not finished and not declined* — so
every client agrees rather than each re-deriving the rule.

**Declining is permanent.** A prompt that reappears after being declined is not a
prompt, it is nagging. The honest escape hatch is that the flow stays reachable
from Profile and Settings, which is where someone who changes their mind goes
looking; `POST /api/onboarding/reopen` clears the dismissal.

The cost of non-blocking is that a skipped profile means estimated targets rather
than chosen ones. That is exactly what `resolve_targets` already reports through
its `sources` map, so the UI keeps saying "2,480 kcal (estimated)" honestly.

## The seven steps

| # | Step | Writes |
|---|---|---|
| 1 | About you | `birth_year`, `sex`, `height_cm` |
| 2 | How active are you? | `activity_level` |
| 3 | What are you working towards? | `goal`, plus a weight measurement |
| 4 | Sleep | `sleep_target_minutes`, `target_bedtime`, `target_wake_time` |
| 5 | Learning | `weekly_study_minutes` |
| 6 | Choose your Path | `users.selected_path` |
| 7 | Your starting point | nothing — it shows what the previous six produced |

The steps are **declared server-side** and rendered by the client, so the API and
the UI cannot disagree about how many there are or what each writes.

Two fields deliberately live outside `user_profile`. Weight is a
`body_measurements` row because it changes weekly and the profile is for things
that do not — and because the Training workspace already reads it from there. The
Path lives on `users` because it predates `user_profile` by the whole project and
three clients read it.

Saving is **partial and per step**, so closing the tab half way through costs the
step you were on and nothing before it. Skipping discards that step's edits
rather than saving a half-answer.

## Validation

Closed sets are rejected, not coerced. `resolve_targets` silently falls back to
`moderate` for an unrecognised `activity_level`, so a typo would quietly become a
1.55 multiplier on someone's calorie target with nothing on screen to say it
happened.

Ranges reject **impossible** input, not implausible input — the point is to stop
a typo becoming a permanent baseline, not to argue with someone about their own
body. A rejected step saves nothing from that step, so one bad field cannot
produce a half-written profile.

Errors come back per field (`{"fields": {"height_cm": "..."}}`) and render under
the control that caused them. `ApiError` gained a `body` for this, because a 400
often carries more than a sentence and throwing it away leaves the UI able to say
"something was wrong" and nothing else.

## Baselines

`bmi()`, `bmr()` and `tdee()` all return `None` rather than guessing when an
input is missing, and the payload carries `missing` naming what is still needed —
so the last step says "add your height and this fills in" instead of showing
three dashes and no reason.

**BMI is returned as a bare number with no category.** It is a ratio of mass to
height squared; it cannot see muscle, and the standard bands would tell a lifter
at 15% body fat that they are overweight. A number someone can interpret against
their own situation is observable. A verdict is not.

## What R9 deliberately did not change

Two things looked like they were in scope and were not, and both were checked
against the code rather than assumed.

**Sleep schedule.** `target_bedtime` and `target_wake_time` are for display and
prefill only. Discipline's schedule-consistency signal measures the *spread* of
your own bedtimes across a window, not adherence to a declared time — and that is
defensible, because consistency and adherence-to-a-plan are different things and a
consistent 01:00 sleeper is being consistent. Changing it is a scoring decision,
not an onboarding one.

**Training volume.** `weekly_strength_volume` is a flat 12,000 kg×reps for
everyone, which is arguably wrong for someone training twice a week — they will
never approach it and will score permanently low on Strength. Scaling it by a
declared training frequency is also a scoring decision, so `training_days_per_week`
is **not collected at all** rather than stored unused.

## Profile and Settings

These close the last of the parity table from the `/` cutover.

**Profile** shows details, the baselines they produce, and the attributes you
have earned — with the boundary stated on the page: *"These come from what you
logged, never from what you told us during setup."*

**Settings** is targets and password. Each target shows whether it is `set` or
`estimated`, which makes the badge load-bearing rather than decoration: a number
typed here becomes `set` and is never overruled by an estimate. Changing one
re-judges history rather than just today, because a new calorie target changes
what every past day was aiming at — and the page says so.

Excel export and the admin screens are linked out to `/classic`, which is still
their only home.

-- R9: onboarding.
--
-- Everything before this phase assumed the numbers it measures against already
-- existed. They did not. `user_profile` is created lazily by whichever page
-- first needs it, so an account could reach R8's Analytics with no height, no
-- birth year and no targets - and the honest-scoring engine would correctly
-- report almost everything as unobserved, which reads as "this app does not
-- work" rather than "you have not told it anything yet".
--
-- Onboarding is where those numbers come from.
--
-- The important decision is what it is *allowed* to set. Body metrics produce
-- baselines - BMI, BMR, TDEE - and baselines produce targets. Targets are
-- already denominators the scoring engine measures behaviour against
-- (`targets_by_date` in scoring/producers.py), so answering the questionnaire
-- genuinely changes what your first logged day scores.
--
-- What it does NOT do is write attribute scores. A questionnaire saying "I train
-- four times a week" is a claim, and the engine already has a considered position
-- on claims: self-reported signal is capped at half the range, and an attribute
-- reports 'calibrating' until three days of real history exist. Seeding Strength
-- from a checkbox at signup would walk straight past both rules and hand someone
-- a character sheet they had not earned. The brief's "scores start conservative
-- and from questionnaire answers" is satisfied by the targets, not by the scores.
--
-- No columns are backfilled, deliberately. Both existing accounts are prompted
-- like anyone else, with whatever they already have pre-filled - a profile that
-- was half-built by the Nutrition page is exactly the case onboarding exists to
-- finish.
--
-- SQLite has no ADD COLUMN IF NOT EXISTS, but the migration ledger guarantees
-- this file runs exactly once, so plain ALTERs are safe here (same as 005).

-- NULL until the last step is confirmed. This is the only flag that means
-- "finished"; onboarding_step alone cannot say it, because step 7 of 7 is a
-- screen you can be looking at without having pressed the button.
ALTER TABLE user_profile ADD COLUMN onboarded_at TIMESTAMP;

-- Resume point, 0-indexed. Saved after each step rather than at the end, so
-- closing the tab half way through costs you the step you were on and no more.
ALTER TABLE user_profile ADD COLUMN onboarding_step INTEGER NOT NULL DEFAULT 0;

-- "Not now" is recorded rather than held in memory, and it is permanent: a
-- prompt that reappears after being declined is not a prompt, it is nagging.
-- The flow stays reachable from Profile, which is where someone who changed
-- their mind will go looking.
ALTER TABLE user_profile ADD COLUMN onboarding_dismissed_at TIMESTAMP;

-- The sleep schedule you are aiming for, HH:MM. sleep_target_minutes (004)
-- already covers duration; these cover *when*.
--
-- To be clear about what they do and do not touch: they are shown on Profile and
-- prefill the sleep logger. They are NOT what the Discipline schedule-consistency
-- signal scores against - that measures the spread of your own bedtimes across a
-- window, deliberately, because consistency and adherence-to-a-plan are different
-- things and a consistent 01:00 sleeper is being consistent. Changing that is a
-- scoring decision, not an onboarding one, so it is left alone here.
ALTER TABLE user_profile ADD COLUMN target_bedtime TEXT;
ALTER TABLE user_profile ADD COLUMN target_wake_time TEXT;

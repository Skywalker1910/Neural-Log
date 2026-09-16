-- Completions are per person, not per question.
--
-- 006 made habit_completions unique on (habit_id, date), which was right when
-- every habit belonged to exactly one account: the pair already implied a
-- person.
--
-- 011 broke that assumption. A core question is a single row shared by everyone,
-- so under the old index the first person to answer "Did you train today?" on a
-- given date would own that slot, and the next person's answer would overwrite
-- theirs through the ON CONFLICT clause in record_completions(). Five accounts,
-- one answer between them.
--
-- The honest key is (user_id, habit_id, date).
--
-- This is a separate file rather than an edit to 011 because 011 has already
-- been applied and recorded in the ledger. Editing an applied migration leaves
-- the database and the file permanently disagreeing about what ran, which is the
-- exact failure the ledger exists to prevent.

DROP INDEX IF EXISTS idx_habit_completions_habit_date;

CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_completions_user_habit_date
    ON habit_completions (user_id, habit_id, date);

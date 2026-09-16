-- Movement patterns, so an exercise can show what it looks like.
--
-- The brief asked for "a motion animation visual of each exercise". The obvious
-- route - the illustrated demonstrations everyone has seen - is a licensing
-- problem: those images belong to the sites that made them, and the third-party
-- exercise GIF libraries are the same picture with the same owner.
--
-- So the animations are drawn here, as SVG stick figures moving between two
-- poses, and they are keyed to the MOVEMENT PATTERN rather than to the exercise.
-- That is not a compromise so much as the accurate unit: a barbell bench press,
-- a dumbbell press and a machine chest press are one movement performed with
-- three pieces of equipment. Seventeen patterns cover the whole library, and a
-- new exercise inherits its animation by naming the pattern it belongs to
-- instead of needing art commissioned for it.
--
-- media_url has existed since 003 and was never populated. It stays empty: it is
-- the right column for a real per-exercise clip if one is ever licensed, and
-- filling it with a pattern name would conflate "a picture of this exercise"
-- with "the shape of this movement".
ALTER TABLE exercises ADD COLUMN movement_pattern TEXT;

CREATE INDEX IF NOT EXISTS idx_exercises_pattern ON exercises (movement_pattern);

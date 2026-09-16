-- Log food the way you actually measured it.
--
-- Everything was entered in grams, because grams are what the per-100g maths
-- needs. That made honest arithmetic out of a dishonest question: you did not
-- weigh the chickpeas, you used a cup of them, and converting in your head
-- before typing is the app making you do its job.
--
-- Two columns, both DISPLAY measures. Storage stays in grams and no scoring
-- changes.
--
-- ## Why a cup needs its own column
--
-- A cup is a volume and grams are a mass, so the conversion depends on what is
-- in the cup. A cup of water is 240 g; a cup of cooked chickpeas is about 164 g;
-- a cup of flour is about 125 g. There is no general factor, which is precisely
-- why offering "cups" everywhere with one hard-coded number would be worse than
-- not offering it at all - it would silently misreport half the library.
--
-- So grams_per_cup is set only where a standard measure genuinely exists, and
-- the UI offers cups only for those foods. Everything else keeps grams and ml,
-- where the conversion is either exact or within a few percent.
ALTER TABLE foods ADD COLUMN grams_per_cup REAL;

-- Countable things - eggs, bananas, a mandarin - get a counter instead of a
-- weight field. serving_grams already holds what one of them weighs and
-- serving_name already names it ("1 egg"), so this only marks which foods that
-- reading is true for: "1 bowl" of porridge is a serving but not a countable
-- piece, and a +/- counter on rice would be nonsense.
ALTER TABLE foods ADD COLUMN is_countable INTEGER NOT NULL DEFAULT 0;

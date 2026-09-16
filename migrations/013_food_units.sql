-- Liquids are measured in millilitres.
--
-- Every food was logged and displayed in grams, because grams are what the
-- nutrition maths needs - kcal_per_100g and the rest are all per 100 g. That is
-- correct arithmetic and a poor question: nobody knows how many grams of coffee
-- they drank. They know it was a mug.
--
-- So `unit` is a DISPLAY unit. Storage stays in grams and none of the scoring
-- changes; the UI shows "240 ml" where the food is a liquid and asks for ml on
-- the way in.
--
-- ## Why this is honest for water-based drinks and not for oil
--
-- The conversion assumes 1 ml weighs 1 g, which holds for water, coffee, tea,
-- juice and milk to within about 3% - well inside the error already present in
-- "one mug". It does NOT hold for oil, which is around 0.92 g/ml, and cooking
-- oil is measured by the spoon anyway. Oils therefore stay in grams rather than
-- being given a unit that would quietly misstate them by 8%.
--
-- Category alone could not decide this: `beverage` is all liquid, but `dairy`
-- holds milk alongside cheese and yoghurt.

ALTER TABLE foods ADD COLUMN unit TEXT NOT NULL DEFAULT 'g';

-- Everything in the beverage aisle.
UPDATE foods SET unit = 'ml' WHERE category = 'beverage';

-- Liquid dairy, picked by name because the category holds solids too.
UPDATE foods SET unit = 'ml'
WHERE category = 'dairy'
  AND (name LIKE 'Milk,%' OR name LIKE '%Cream, single%' OR name LIKE '%Cream, double%');

-- Anything a user added themselves keeps grams until they say otherwise; there
-- is no way to tell from here, and guessing at somebody's own entry is worse
-- than leaving it alone.

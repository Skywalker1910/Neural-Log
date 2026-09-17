-- Recompute what one serving of an already-saved dish weighs.
--
-- 016 fixed the write path: a recipe's `foods.serving_grams` is the cooked
-- weight divided by the servings it makes, rather than the whole dish labelled
-- "1 serving".
--
-- That fix only runs when a recipe is created or edited, so every dish saved
-- before it kept the old value and stayed wrong - a curry cooked for six still
-- logged as six portions per "serving", and incrementing the counter to 2
-- charged twelve. A forward fix that leaves existing rows broken is half a fix,
-- and the half that is broken is the half with real data in it.
--
-- The cooked weight is what the recipe declares, or the raw ingredient total
-- when it was left blank - the same fallback recipe_per_100g() uses, so this
-- agrees with what the builder showed on screen when the dish was saved.
--
-- Logged entries are untouched. food_entries stores grams, not servings, so
-- meals already recorded keep the weight they were logged with. Only what a
-- future "1 serving" means is corrected.

UPDATE foods
SET serving_grams = (
    SELECT ROUND(
        COALESCE(
            r.total_grams,
            (SELECT SUM(ri.grams) FROM recipe_ingredients ri WHERE ri.recipe_id = r.id)
        ) / MAX(COALESCE(r.servings, 1), 1),
        1
    )
    FROM recipes r
    WHERE r.food_id = foods.id
),
serving_name = '1 serving'
WHERE id IN (SELECT food_id FROM recipes WHERE food_id IS NOT NULL)
  AND (
      SELECT COALESCE(
          r.total_grams,
          (SELECT SUM(ri.grams) FROM recipe_ingredients ri WHERE ri.recipe_id = r.id)
      )
      FROM recipes r WHERE r.food_id = foods.id
  ) IS NOT NULL;

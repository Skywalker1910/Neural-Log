-- R4: Nutrition and Lifestyle.
--
-- R3 made training measurable. This does the same for the rest of the day: what
-- you ate, how you slept, how much you moved and drank. Three of those become
-- real attribute signals (see docs/SCORING.md):
--
--   sleep duration      -> Recovery, which was unobserved until now
--   sleep consistency   -> Discipline
--   steps               -> Stamina
--   water + calories    -> Discipline, as adherence to your own targets
--
-- Mood, stress, energy and the journal are recorded here but deliberately never
-- scored. They are self-reported feelings, not behaviour: scoring them would
-- both be dishonest and pay you to report feeling good.

-- The food library. Same shape as `exercises`: rows with user_id IS NULL are the
-- shipped library, rows with a user_id are that person's own foods and recipes.
--
-- Macros are stored per 100g because that is how nutrition data is published and
-- how it composes - a recipe is the weighted sum of its ingredients, which only
-- works if everything shares a basis. Serving sizes are a display convenience on
-- top, never the storage unit.
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                      -- NULL = shipped library food
    slug TEXT NOT NULL,
    name TEXT NOT NULL,

    -- protein | grain | legume | vegetable | fruit | dairy | fat | nut-seed
    -- | beverage | prepared | condiment | sweet
    category TEXT NOT NULL DEFAULT 'prepared',

    -- 'library' | 'custom' | 'recipe'. A recipe is a food: once saved it is
    -- logged exactly like any other, and its ingredient breakdown lives in
    -- `recipes` for later editing.
    source TEXT NOT NULL DEFAULT 'library',

    kcal_per_100g REAL NOT NULL,
    protein_per_100g REAL NOT NULL DEFAULT 0,
    carbs_per_100g REAL NOT NULL DEFAULT 0,
    fat_per_100g REAL NOT NULL DEFAULT 0,
    fibre_per_100g REAL NOT NULL DEFAULT 0,

    -- One typical portion, so the UI can offer "1 medium banana" instead of
    -- demanding you weigh it. Grams remain the stored quantity.
    serving_name TEXT,
    serving_grams REAL,

    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Library slugs are globally unique; a user's own only have to be unique to them.
-- Two partial indexes, for the same reason as `exercises`: SQLite treats NULLs as
-- distinct, so UNIQUE(user_id, slug) would allow duplicate library rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_library_slug
    ON foods (slug) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_user_slug
    ON foods (user_id, slug) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_foods_category ON foods (category);

-- A cooked dish, built from library ingredients.
--
-- The point of this table is reuse: you describe what you cooked once, and from
-- then on it is one entry in the picker. `food_id` is the row in `foods` that
-- this recipe produces - so logging a recipe and logging a plain food are the
-- same operation everywhere downstream.
--
-- total_grams is the cooked weight, which is NOT the sum of the raw ingredients:
-- rice absorbs water and roasting drives it off. Storing it separately is what
-- lets per-100g macros be honest about what actually came out of the pan.
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    food_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    servings REAL NOT NULL DEFAULT 1,
    total_grams REAL,
    notes TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (food_id) REFERENCES foods (id)
);

CREATE INDEX IF NOT EXISTS idx_recipes_user ON recipes (user_id, archived);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_food ON recipes (food_id);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    food_id INTEGER NOT NULL,
    grams REAL NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (recipe_id) REFERENCES recipes (id),
    FOREIGN KEY (food_id) REFERENCES foods (id)
);

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe
    ON recipe_ingredients (recipe_id, position);

-- One thing eaten, at one meal, on one day. The grain of the whole workspace -
-- the same role `exercise_sets` plays for Training.
--
-- Macros are NOT denormalised onto this row. They are always the food's per-100g
-- values times grams, so correcting a food's data corrects every meal that used
-- it, instead of leaving a trail of rows frozen at the wrong numbers.
CREATE TABLE IF NOT EXISTS food_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    meal TEXT NOT NULL DEFAULT 'snack',   -- breakfast | lunch | dinner | snack
    food_id INTEGER NOT NULL,
    grams REAL NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (food_id) REFERENCES foods (id)
);

CREATE INDEX IF NOT EXISTS idx_food_entries_user_date ON food_entries (user_id, date);

-- One night's sleep, keyed to the date you WOKE UP.
--
-- That choice matters and is easy to get wrong: a night is spread across two
-- calendar dates, and keying it to the bedtime date would file a 01:00 bedtime
-- under the previous day and make every late night look like a missing night.
-- Waking is the unambiguous end of the event.
CREATE TABLE IF NOT EXISTS sleep_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,                   -- the wake date
    bedtime TEXT,                         -- HH:MM local
    wake_time TEXT,                       -- HH:MM local
    duration_minutes INTEGER NOT NULL,
    quality INTEGER,                      -- 1-5, self-reported, NOT scored
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- One night per date: unlike workouts, two sleeps ending on the same date is a
-- correction, not a second event.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sleep_user_date ON sleep_entries (user_id, date);

-- Everything else about a day that is a single number or a note.
--
-- One row per user per day rather than a metric-per-row table: these are always
-- read together for a single date, they are always upserted together by one
-- form, and a tall table would turn every dashboard read into a pivot.
CREATE TABLE IF NOT EXISTS lifestyle_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,

    -- Measured behaviour. These feed attributes.
    water_ml INTEGER,
    steps INTEGER,
    sunlight_minutes INTEGER,

    -- Self-reported feelings, 1-5. Recorded and charted, deliberately never
    -- scored - see the header of this file.
    mood INTEGER,
    stress INTEGER,
    energy INTEGER,

    journal TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lifestyle_user_date ON lifestyle_days (user_id, date);

-- The minimum needed to estimate energy expenditure and to know what "hitting
-- your target" means.
--
-- DATA-MODEL.md assigns UserProfile to R9, and R9 still owns the full onboarding
-- flow. But R4 cannot show energy balance without a TDEE, and a TDEE needs age,
-- sex, height and activity level. So the fields R4 actually consumes land here
-- and R9 expands the table rather than creating it.
--
-- Body weight is deliberately absent: `body_measurements` already holds it from
-- R3, and a second copy would drift from the first.
CREATE TABLE IF NOT EXISTS user_profile (
    user_id INTEGER PRIMARY KEY,
    birth_year INTEGER,
    sex TEXT,                             -- male | female | unspecified
    height_cm REAL,

    -- sedentary | light | moderate | active | very-active
    activity_level TEXT NOT NULL DEFAULT 'moderate',
    goal TEXT NOT NULL DEFAULT 'maintain',   -- cut | maintain | bulk

    -- Targets. NULL means "derive it" - calories from TDEE, protein from body
    -- weight - so an untouched profile still produces usable numbers, and an
    -- explicitly set target is distinguishable from a default that happens to
    -- match.
    calorie_target INTEGER,
    protein_target_g INTEGER,
    carb_target_g INTEGER,
    fat_target_g INTEGER,
    fibre_target_g INTEGER DEFAULT 30,
    water_target_ml INTEGER DEFAULT 2500,
    step_target INTEGER DEFAULT 8000,
    sleep_target_minutes INTEGER DEFAULT 480,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
